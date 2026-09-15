#!/usr/bin/env python3
"""Local MCP server for read-only Codex usage attribution and UI preferences."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

from preferences import get_preferences, set_auto_card_interval

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 fallback
    ZoneInfo = None  # type: ignore[assignment]


SERVER_NAME = "codex-usage"
SERVER_VERSION = "0.2.0"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = PLUGIN_ROOT / "assets" / "dashboard.html"
CARD_PATH = PLUGIN_ROOT / "assets" / "status-card.html"
# Active Codex tasks cache the MCP resource catalog. Keep this URI stable across
# plugin reinstalls and use the manifest version cachebuster for UI revisions.
CARD_RESOURCE_URI = "ui://codex-usage/status-card-v7.html"
LEGACY_CARD_RESOURCE_URIS = {
    "ui://codex-usage/status-card-v1.html",
    "ui://codex-usage/status-card-v2.html",
    "ui://codex-usage/status-card-v3.html",
    "ui://codex-usage/status-card-v4.html",
    "ui://codex-usage/status-card-v5.html",
    "ui://codex-usage/status-card-v6.html",
}
CARD_HTML = CARD_PATH.read_text(encoding="utf-8")
_DASHBOARD_SERVER: ThreadingHTTPServer | None = None
_DASHBOARD_LOCK = threading.Lock()
_REPORT_CACHE: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}
_REPORT_CACHE_LOCK = threading.Lock()
_REPORT_CACHE_TTL_SECONDS = 10
_CARD_REPORT_CACHE_TTL_SECONDS = 5 * 60
_LIMIT_CACHE: tuple[float, dict[str, Any] | None] | None = None
_LIMIT_CACHE_LOCK = threading.Lock()
_LIMIT_CACHE_TTL_SECONDS = 10
LIVE_REFRESH_INTERVAL_MS = 3_000
LIVE_REFRESH_SECONDS = 2 * 60


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _local_timezone():
    name = os.environ.get("TZ")
    if name and ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def _connect() -> sqlite3.Connection:
    database = _codex_home() / "state_5.sqlite"
    if not database.exists():
        raise RuntimeError(f"Codex state database was not found at {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _event_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _reverse_lines(path: Path, max_bytes: int = 4 * 1024 * 1024) -> Iterable[str]:
    """Yield recent lines newest-first without loading a large rollout."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        start = max(0, end - max_bytes)
        handle.seek(start)
        data = handle.read()
    if start:
        first_newline = data.find(b"\n")
        data = data[first_newline + 1 :] if first_newline >= 0 else b""
    for line in reversed(data.splitlines()):
        yield line.decode("utf-8", errors="replace")


def _usage_fields(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "inputTokens": int(payload.get("input_tokens") or 0),
        "cachedInputTokens": int(payload.get("cached_input_tokens") or 0),
        "outputTokens": int(payload.get("output_tokens") or 0),
        "reasoningOutputTokens": int(payload.get("reasoning_output_tokens") or 0),
        "totalTokens": int(payload.get("total_tokens") or 0),
    }


def _latest_token_event(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    for line in _reverse_lines(path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = record.get("payload") or {}
        if record.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        info = payload.get("info") or {}
        total = info.get("total_token_usage")
        if isinstance(total, dict):
            last = info.get("last_token_usage")
            return {
                "timestamp": record.get("timestamp"),
                "usage": _usage_fields(total),
                "lastUsage": _usage_fields(last) if isinstance(last, dict) else None,
                "modelContextWindow": int(info.get("model_context_window") or 0),
                "rateLimits": payload.get("rate_limits"),
            }
    return None


def _latest_rate_limit_uncached(connection: sqlite3.Connection) -> dict[str, Any] | None:
    rows = connection.execute(
        "SELECT rollout_path FROM threads ORDER BY updated_at DESC LIMIT 40"
    ).fetchall()
    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        event = _latest_token_event(row["rollout_path"])
        if not event or not event.get("rateLimits"):
            continue
        epoch = _event_epoch(event.get("timestamp"))
        if epoch is not None:
            candidates.append((epoch, event))
    if not candidates:
        return None
    event = max(candidates, key=lambda item: item[0])[1]
    limits = event.get("rateLimits") or {}
    primary = limits.get("primary") or {}
    window_minutes = primary.get("window_minutes") or primary.get("windowDurationMins")
    resets_at = primary.get("resets_at") or primary.get("resetsAt")
    used_percent = primary.get("used_percent")
    if used_percent is None:
        used_percent = primary.get("usedPercent")
    if not window_minutes or not resets_at:
        return None
    start_at = int(resets_at) - int(window_minutes) * 60
    return {
        "usedPercent": float(used_percent) if used_percent is not None else None,
        "windowMinutes": int(window_minutes),
        "startAt": start_at,
        "resetsAt": int(resets_at),
        "planType": limits.get("plan_type") or limits.get("planType"),
        "observedAt": event.get("timestamp"),
    }


def _latest_rate_limit(connection: sqlite3.Connection) -> dict[str, Any] | None:
    global _LIMIT_CACHE
    now = time.monotonic()
    with _LIMIT_CACHE_LOCK:
        cached = _LIMIT_CACHE
    if cached is not None and now - cached[0] < _LIMIT_CACHE_TTL_SECONDS:
        return cached[1]

    limit = _latest_rate_limit_uncached(connection)
    with _LIMIT_CACHE_LOCK:
        _LIMIT_CACHE = (now, limit)
    return limit


def _range_bounds(range_name: str, limit: dict[str, Any] | None) -> tuple[int, int, str]:
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(_local_timezone())
    if range_name == "current_window" and limit:
        return int(limit["startAt"]), int(now.timestamp()), "Current Codex window"
    if range_name == "today":
        start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(start.timestamp()), int(now.timestamp()), "Today"
    days = 30 if range_name == "last_30_days" else 7
    return (
        int((now - timedelta(days=days)).timestamp()),
        int(now.timestamp()),
        f"Last {days} days",
    )


def _usage_pace(limit: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project the aggregate limit from its average pace in the active window."""
    if not limit or limit.get("usedPercent") is None:
        return None

    start_at = int(limit["startAt"])
    resets_at = int(limit["resetsAt"])
    observed_at = _event_epoch(limit.get("observedAt")) or time.time()
    observed_at = min(max(observed_at, start_at), resets_at)
    duration = resets_at - start_at
    elapsed = observed_at - start_at
    used_percent = float(limit["usedPercent"])
    if duration <= 0 or elapsed < 15 * 60 or used_percent <= 0:
        return None

    used_per_second = used_percent / elapsed
    projected_percent = used_per_second * duration
    reaches_limit_at = start_at + (100 / used_per_second)
    likely_exhausts = reaches_limit_at < resets_at
    return {
        "status": "likely_exhausts" if likely_exhausts else "within_limit",
        "projectedPercent": round(projected_percent, 1),
        "paceRatio": round(projected_percent / 100, 2),
        "elapsedPercent": round(elapsed * 100 / duration, 1),
        "reachesLimitAt": int(reaches_limit_at) if likely_exhausts else None,
        "observedAt": int(observed_at),
        "basis": "Average aggregate usage since this limit window began.",
    }


def _resolve_event_epochs(
    raw_epochs: list[float | None],
    span: tuple[int, int] | None,
) -> list[float | None]:
    """Repair rollout files that stamp every token event with one session time.

    Some rollouts (compactions, forks, resumed threads) are written in a single
    pass, so every record carries the session timestamp instead of the moment
    each response happened. Summing those by timestamp drops a whole session
    into one instant and misplaces it across window and day boundaries.

    When a file shows that signature, spread the events evenly across the
    thread's real lifetime so each one lands at the midpoint of its share.
    Files with genuine per-event timestamps are returned untouched.
    """
    if len(raw_epochs) < 2 or span is None:
        return raw_epochs

    distinct = {epoch for epoch in raw_epochs if epoch is not None}
    if len(distinct) != 1:
        return raw_epochs

    started_at, ended_at = span
    if ended_at <= started_at:
        return raw_epochs

    step = (ended_at - started_at) / len(raw_epochs)

    return [started_at + (index + 0.5) * step for index in range(len(raw_epochs))]


def _sum_rollout(
    path_value: str,
    start_at: int,
    end_at: int,
    span: tuple[int, int] | None = None,
) -> dict[str, int]:
    totals = {
        "inputTokens": 0,
        "cachedInputTokens": 0,
        "outputTokens": 0,
        "reasoningOutputTokens": 0,
        "totalTokens": 0,
        "responses": 0,
    }
    path = Path(path_value)
    if not path.is_file():
        return totals

    raw_epochs: list[float | None] = []
    usages: list[dict[str, int]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = record.get("payload") or {}
            if record.get("type") != "event_msg" or payload.get("type") != "token_count":
                continue
            last = (payload.get("info") or {}).get("last_token_usage")
            if not isinstance(last, dict):
                continue
            raw_epochs.append(_event_epoch(record.get("timestamp")))
            usages.append(_usage_fields(last))

    for epoch, values in zip(_resolve_event_epochs(raw_epochs, span), usages):
        if epoch is None or epoch < start_at or epoch > end_at:
            continue
        for key, value in values.items():
            totals[key] += value
        totals["responses"] += 1
    return totals


def _thread_span(row: sqlite3.Row) -> tuple[int, int] | None:
    """Return the thread's (created_at, updated_at) lifetime in epoch seconds."""
    try:
        started_at = int(row["created_at"])
        ended_at = int(row["updated_at"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None

    return (started_at, ended_at) if ended_at > started_at else None


def _task_name(row: sqlite3.Row) -> str:
    name = (row["name"] or "").strip()
    if name:
        return name
    parent_name = (row["parent_name"] or "").strip()
    if row["thread_source"] == "subagent" and parent_name:
        return f"Subagent · {parent_name}"
    first = " ".join((row["first_user_message"] or "").split())
    if first:
        return first[:100] + ("…" if len(first) > 100 else "")
    return f"Untitled {row['thread_source'] or 'task'}"


def _iso_local(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, _local_timezone()).isoformat()


def usage_dashboard(arguments: dict[str, Any]) -> dict[str, Any]:
    range_name = arguments.get("range") or "current_window"
    include_internal = bool(arguments.get("include_internal", False))
    with _connect() as connection:
        limit = _latest_rate_limit(connection)
        start_at, end_at, label = _range_bounds(range_name, limit)
        rows = connection.execute(
            """
            SELECT t.id, t.name, t.first_user_message, t.thread_source, t.model,
                   t.reasoning_effort, t.cwd, t.created_at, t.updated_at,
                   t.rollout_path,
                   edge.parent_thread_id, parent.name AS parent_name
            FROM threads AS t
            LEFT JOIN thread_spawn_edges AS edge ON edge.child_thread_id = t.id
            LEFT JOIN threads AS parent ON parent.id = edge.parent_thread_id
            WHERE t.updated_at >= ?
            ORDER BY t.updated_at DESC
            """,
            (start_at,),
        ).fetchall()

    items: list[dict[str, Any]] = []
    source_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"totalTokens": 0, "responses": 0, "tasks": 0}
    )
    overall = 0
    overall_cached = 0
    for row in rows:
        usage = _sum_rollout(
            row["rollout_path"], start_at, end_at, _thread_span(row)
        )
        if usage["totalTokens"] <= 0:
            continue
        source = row["thread_source"] or "unknown"
        source_totals[source]["totalTokens"] += usage["totalTokens"]
        source_totals[source]["responses"] += usage["responses"]
        source_totals[source]["tasks"] += 1
        overall += usage["totalTokens"]
        overall_cached += usage["cachedInputTokens"]
        if source == "guardian_review" and not include_internal:
            continue
        items.append(
            {
                "id": row["id"],
                "name": _task_name(row),
                "source": source,
                "model": row["model"],
                "reasoningEffort": row["reasoning_effort"],
                "project": Path(row["cwd"]).name if row["cwd"] else None,
                "createdAt": _iso_local(int(row["created_at"])),
                "parentThreadId": row["parent_thread_id"],
                **usage,
            }
        )
    items.sort(key=lambda item: item["totalTokens"], reverse=True)
    visible_total = sum(item["totalTokens"] for item in items)
    for item in items:
        item["sharePercent"] = (
            round(item["totalTokens"] * 100 / visible_total, 2) if visible_total else 0
        )
        input_tokens = item["inputTokens"]
        item["cachedPercent"] = (
            round(item["cachedInputTokens"] * 100 / input_tokens, 2)
            if input_tokens
            else 0
        )
    return {
        "kind": "dashboard",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "range": range_name,
        "rangeLabel": label,
        "startAt": _iso_local(start_at),
        "endAt": _iso_local(end_at),
        "limit": limit,
        "totals": {
            "totalTokens": overall,
            "cachedInputTokens": overall_cached,
            "cachedPercent": round(overall_cached * 100 / overall, 2) if overall else 0,
            "visibleTokens": visible_total,
        },
        "sources": [
            {"source": source, **values}
            for source, values in sorted(
                source_totals.items(),
                key=lambda item: item[1]["totalTokens"],
                reverse=True,
            )
        ],
        "tasks": items[:100],
        "internalIncluded": include_internal,
        "notice": "Raw local token counters are not an authoritative quota ledger.",
    }


def _cached_usage_dashboard(
    range_name: str,
    include_internal: bool,
    ttl_seconds: int = _REPORT_CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    cache_key = (range_name, include_internal)
    now = time.monotonic()
    with _REPORT_CACHE_LOCK:
        cached = _REPORT_CACHE.get(cache_key)
    if cached is not None and now - cached[0] < ttl_seconds:
        return cached[1]

    dashboard = usage_dashboard(
        {"range": range_name, "include_internal": include_internal}
    )
    with _REPORT_CACHE_LOCK:
        _REPORT_CACHE[cache_key] = (now, dashboard)
    return dashboard


def current_conversation_usage(arguments: dict[str, Any]) -> dict[str, Any]:
    thread_id = (
        arguments.get("thread_id")
        or os.environ.get("CODEX_THREAD_ID")
        or os.environ.get("CODEX_SESSION_ID")
    )
    if not thread_id:
        raise RuntimeError("The current Codex thread ID is unavailable; pass thread_id explicitly.")
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, name, first_user_message, thread_source, model, reasoning_effort,
                   cwd, created_at, rollout_path, tokens_used, NULL AS parent_name
            FROM threads WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Codex thread {thread_id} was not found in local state.")
        children = connection.execute(
            """
            SELECT child.id, child.name, child.tokens_used, child.model,
                   child.reasoning_effort, child.thread_source
            FROM thread_spawn_edges AS edge
            JOIN threads AS child ON child.id = edge.child_thread_id
            WHERE edge.parent_thread_id = ?
            ORDER BY child.tokens_used DESC
            """,
            (thread_id,),
        ).fetchall()
        limit = _latest_rate_limit(connection)
    latest = _latest_token_event(row["rollout_path"])
    own = latest["usage"] if latest else {
        "inputTokens": int(row["tokens_used"] or 0),
        "cachedInputTokens": 0,
        "outputTokens": 0,
        "reasoningOutputTokens": 0,
        "totalTokens": int(row["tokens_used"] or 0),
    }
    child_items = [
        {
            "id": child["id"],
            "name": child["name"] or "Subagent",
            "totalTokens": int(child["tokens_used"] or 0),
            "model": child["model"],
            "reasoningEffort": child["reasoning_effort"],
            "source": child["thread_source"],
        }
        for child in children
    ]
    child_total = sum(item["totalTokens"] for item in child_items)
    input_tokens = own["inputTokens"]
    latest_turn = latest.get("lastUsage") if latest else None
    context_window = int(latest.get("modelContextWindow") or 0) if latest else 0
    context_input = int((latest_turn or {}).get("inputTokens") or 0)
    context_percent = (
        round(context_input * 100 / context_window, 2) if context_window else None
    )
    return {
        "kind": "current",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "thread": {
            "id": row["id"],
            "name": _task_name(row),
            "source": row["thread_source"],
            "model": row["model"],
            "reasoningEffort": row["reasoning_effort"],
            "project": Path(row["cwd"]).name if row["cwd"] else None,
            "createdAt": _iso_local(int(row["created_at"])),
        },
        "ownUsage": {
            **own,
            "cachedPercent": (
                round(own["cachedInputTokens"] * 100 / input_tokens, 2)
                if input_tokens
                else 0
            ),
        },
        "latestTurn": latest_turn,
        "context": {
            "inputTokens": context_input,
            "windowTokens": context_window,
            "usedPercent": context_percent,
        },
        "subagents": child_items,
        "subagentTokens": child_total,
        "combinedTokens": own["totalTokens"] + child_total,
        "limit": limit,
        "notice": "Raw local token counters are not an authoritative quota ledger.",
    }


def usage_card(
    arguments: dict[str, Any], *, include_details: bool = True
) -> dict[str, Any]:
    current = current_conversation_usage(arguments)
    dashboard = (
        _cached_usage_dashboard(
            "current_window", False, _CARD_REPORT_CACHE_TTL_SECONDS
        )
        if include_details
        else None
    )
    now = datetime.now(timezone.utc)
    live_requested = bool(arguments.get("live", True))
    requested_deadline = arguments.get("live_until_epoch_ms")
    if isinstance(requested_deadline, (int, float)):
        live_until_epoch_ms = int(requested_deadline)
    else:
        live_until_epoch_ms = int(
            (now + timedelta(seconds=LIVE_REFRESH_SECONDS)).timestamp() * 1000
        )
    live_enabled = live_requested and live_until_epoch_ms > int(now.timestamp() * 1000)
    context_percent = current["context"]["usedPercent"]
    context_level = "normal"
    if context_percent is not None and context_percent >= 90:
        context_level = "notice"
    elif context_percent is not None and context_percent >= 80:
        context_level = "notice"

    latest_output = int((current.get("latestTurn") or {}).get("outputTokens") or 0)
    alerts: list[dict[str, str]] = []
    if context_percent is not None and context_percent >= 90:
        alerts.append(
            {
                "level": "notice",
                "title": "Automatic compaction may happen soon",
                "detail": "Codex normally handles this; use a follow-up task only when you want a cleaner task boundary.",
            }
        )
    if latest_output >= 12000:
        alerts.append(
            {
                "level": "warning",
                "title": "Large latest response",
                "detail": f"The latest response produced {latest_output:,} output tokens.",
            }
        )

    return {
        "kind": "usage_card",
        "generatedAt": now.isoformat(),
        "automatic": bool(arguments.get("automatic", False)),
        "thread": current["thread"],
        "sessionUsage": current["ownUsage"],
        "latestTurn": current["latestTurn"],
        "context": {**current["context"], "level": context_level},
        "subagentCount": len(current["subagents"]),
        "subagentTokens": current["subagentTokens"],
        "combinedTokens": current["combinedTokens"],
        "limit": current["limit"],
        "pace": _usage_pace(current["limit"]),
        "detailsLoaded": include_details,
        "windowUsage": dashboard["totals"] if dashboard else None,
        "topTasks": [
            {
                "id": task["id"],
                "name": task["name"],
                "source": task["source"],
                "model": task["model"],
                "project": task["project"],
                "responses": task["responses"],
                "inputTokens": task["inputTokens"],
                "cachedInputTokens": task["cachedInputTokens"],
                "cachedPercent": task["cachedPercent"],
                "outputTokens": task["outputTokens"],
                "reasoningOutputTokens": task["reasoningOutputTokens"],
                "totalTokens": task["totalTokens"],
                "sharePercent": task["sharePercent"],
            }
            for task in (dashboard["tasks"][:5] if dashboard else [])
        ],
        "alerts": alerts,
        "preferences": get_preferences(),
        "liveRefresh": {
            "enabled": live_enabled,
            "intervalMs": LIVE_REFRESH_INTERVAL_MS,
            "untilEpochMs": live_until_epoch_ms,
        },
        "notice": "Raw local token counters are not an authoritative quota ledger.",
    }


def _dashboard_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    range_name = (query.get("range") or ["current_window"])[0]
    include_internal = (query.get("include_internal") or ["false"])[0].lower() == "true"
    thread_id = (query.get("thread_id") or [""])[0] or None
    dashboard = _cached_usage_dashboard(range_name, include_internal)
    current = None
    current_error = None
    try:
        current = current_conversation_usage(
            {"thread_id": thread_id} if thread_id else {}
        )
    except Exception as exc:
        current_error = str(exc)
    return {
        "current": current,
        "currentError": current_error,
        "dashboard": dashboard,
    }


class _DashboardHandler(BaseHTTPRequestHandler):
    server_version = "CodexUsage/0.2"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", DASHBOARD_PATH.read_bytes())
            return
        if parsed.path == "/card-preview":
            query = parse_qs(parsed.query)
            thread_id = (query.get("thread_id") or [""])[0] or None
            report = usage_card({"thread_id": thread_id} if thread_id else {})
            encoded = json.dumps(report, separators=(",", ":")).replace("<", "\\u003c")
            html = CARD_PATH.read_text(encoding="utf-8").replace(
                "</head>",
                f"<script>window.openai={{toolOutput:{encoded}}};</script></head>",
                1,
            )
            self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
            return
        if parsed.path == "/health":
            self._send(200, "application/json", b'{"ok":true}')
            return
        if parsed.path == "/api/report":
            try:
                payload = _dashboard_payload(parse_qs(parsed.query))
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self._send(200, "application/json", body)
            except Exception as exc:
                body = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send(500, "application/json", body)
            return
        self._send(404, "text/plain; charset=utf-8", b"Not found")

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def _ensure_dashboard_server() -> ThreadingHTTPServer:
    global _DASHBOARD_SERVER
    with _DASHBOARD_LOCK:
        if _DASHBOARD_SERVER is not None:
            return _DASHBOARD_SERVER
        server = ThreadingHTTPServer(("127.0.0.1", 0), _DashboardHandler)
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever,
            name="codex-usage-dashboard",
            daemon=True,
        )
        thread.start()
        _DASHBOARD_SERVER = server
        return server


def open_usage_dashboard(arguments: dict[str, Any]) -> dict[str, Any]:
    thread_id = (
        arguments.get("thread_id")
        or os.environ.get("CODEX_THREAD_ID")
        or os.environ.get("CODEX_SESSION_ID")
        or ""
    )
    query = {
        "range": arguments.get("range") or "current_window",
        "include_internal": "true" if arguments.get("include_internal") else "false",
    }
    if thread_id:
        query["thread_id"] = thread_id
    server = _ensure_dashboard_server()
    host, port = server.server_address[:2]
    return {
        "kind": "panel",
        "dashboardUrl": f"http://{host}:{port}/?{urlencode(query)}",
        "threadId": thread_id or None,
        "range": query["range"],
        "notice": "This localhost dashboard remains available while the Codex task is open.",
    }


def update_auto_card_interval(arguments: dict[str, Any]) -> dict[str, Any]:
    interval_seconds = int(arguments.get("interval_seconds"))
    preferences = set_auto_card_interval(interval_seconds)
    return {
        "kind": "usage_preferences",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        **preferences,
    }


def usage_preferences() -> dict[str, Any]:
    return {
        "kind": "usage_preferences",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        **get_preferences(),
    }


def _tool_descriptor(
    name: str,
    description: str,
    properties: dict[str, Any],
    *,
    meta: dict[str, Any] | None = None,
    required: list[str] | None = None,
    read_only: bool = True,
) -> dict[str, Any]:
    descriptor = {
        "name": name,
        "title": name.replace("_", " ").title(),
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": read_only,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }
    if required:
        descriptor["inputSchema"]["required"] = required
    if meta:
        descriptor["_meta"] = meta
    return descriptor


TOOLS = [
    _tool_descriptor(
        "show_usage_card",
        "Render a compact native usage card for this Codex conversation with expandable cross-task details.",
        {
            "thread_id": {
                "type": "string",
                "description": "The current Codex task/thread ID from the task context.",
            },
            "live": {
                "type": "boolean",
                "default": True,
                "description": "Refresh the card briefly while the current turn is active.",
            },
            "automatic": {
                "type": "boolean",
                "default": False,
                "description": "Marks a card requested by the plugin's rate-limited prompt hook.",
            },
        },
        meta={
            "ui": {"resourceUri": CARD_RESOURCE_URI},
            "openai/outputTemplate": CARD_RESOURCE_URI,
            "openai/toolInvocation/invoking": "Reading local usage…",
            "openai/toolInvocation/invoked": "Usage ready",
        },
        required=["thread_id"],
    ),
    _tool_descriptor(
        "refresh_usage_card",
        "Refresh the values inside an already-rendered Codex Usage card without creating another inline card.",
        {
            "thread_id": {
                "type": "string",
                "description": "The Codex task/thread ID displayed by the existing card.",
            },
            "live_until_epoch_ms": {
                "type": "number",
                "description": "The original card's fixed live-refresh deadline.",
            },
            "live": {
                "type": "boolean",
                "default": True,
                "description": "Continue live refreshes after the cross-task details load.",
            },
        },
        required=["thread_id", "live_until_epoch_ms"],
    ),
    _tool_descriptor(
        "get_usage_preferences",
        "Read the current automatic-card interval shared by all Codex Usage cards.",
        {},
    ),
    _tool_descriptor(
        "set_auto_card_interval",
        "Set how often a new automatic inline usage card may appear in the same Codex task.",
        {
            "interval_seconds": {
                "type": "integer",
                "enum": [-1, 0, 30, 60, 300, 900],
                "description": "-1 turns automatic cards off; 0 allows every user turn.",
            }
        },
        required=["interval_seconds"],
        read_only=False,
    ),
    _tool_descriptor(
        "open_usage_dashboard",
        "Start the private localhost usage dashboard and return its URL for a Codex browser panel.",
        {
            "thread_id": {"type": "string", "description": "Optional explicit Codex thread ID."},
            "range": {
                "type": "string",
                "enum": ["current_window", "today", "last_7_days", "last_30_days"],
                "default": "current_window",
            },
            "include_internal": {"type": "boolean", "default": False},
        },
    ),
    _tool_descriptor(
        "current_conversation_usage",
        "Show raw local token usage for the current Codex conversation and its subagents.",
        {
            "thread_id": {
                "type": "string",
                "description": "The current Codex task/thread ID from the task context.",
            }
        },
        required=["thread_id"],
    ),
    _tool_descriptor(
        "usage_dashboard",
        "Show an interactive cross-task dashboard of locally recorded Codex usage.",
        {
            "range": {
                "type": "string",
                "enum": ["current_window", "today", "last_7_days", "last_30_days"],
                "default": "current_window",
            },
            "include_internal": {
                "type": "boolean",
                "default": False,
                "description": "Include internal approval-review tasks in task rows.",
            },
        },
    ),
]


def _text_summary(report: dict[str, Any]) -> str:
    if report["kind"] == "panel":
        return f"Open the private Codex Usage dashboard: {report['dashboardUrl']}"
    if report["kind"] == "current":
        return (
            f"{report['thread']['name']}: {report['ownUsage']['totalTokens']:,} raw tokens "
            f"in the conversation and {report['subagentTokens']:,} in subagents."
        )
    if report["kind"] == "usage_preferences":
        interval = int(report["autoCardIntervalSeconds"])
        if interval < 0:
            return "Automatic Codex Usage cards are off."
        if interval == 0:
            return "Automatic Codex Usage cards may appear on every user turn."
        return f"Automatic Codex Usage cards are limited to one every {interval} seconds per task."
    if report["kind"] == "usage_card":
        context = report["context"].get("usedPercent")
        context_text = f"{context:.0f}%" if context is not None else "—"
        account = report.get("limit") or {}
        account_percent = account.get("usedPercent")
        account_text = f"{account_percent:.0f}%" if account_percent is not None else "—"
        window_days = int(account.get("windowMinutes") or 0) // (24 * 60)
        account_label = f"{window_days}-day" if window_days else "Account"
        pace = report.get("pace") or {}
        if pace.get("status") == "likely_exhausts" and pace.get("reachesLimitAt"):
            reaches = datetime.fromtimestamp(
                pace["reachesLimitAt"], _local_timezone()
            )
            pace_text = f" · Pace: limit ~{reaches.strftime('%b')} {reaches.day}"
        elif pace.get("status") == "within_limit":
            pace_text = " · Pace: within limit"
        else:
            pace_text = ""
        token_count = report["combinedTokens"]
        session_text = (
            f"{token_count / 1_000_000:.1f}M"
            if token_count >= 1_000_000
            else f"{token_count / 1_000:.1f}K"
            if token_count >= 1_000
            else str(token_count)
        )
        return (
            f"⚡ Usage · Context {context_text} · Task {session_text} raw · "
            f"{account_label} {account_text}{pace_text} · Say “usage details” for breakdown."
        )
    tasks = report.get("tasks") or []
    leader = tasks[0] if tasks else None
    lead = f" Top task: {leader['name']} ({leader['totalTokens']:,})." if leader else ""
    return (
        f"{report['rangeLabel']}: {report['totals']['totalTokens']:,} locally recorded raw tokens "
        f"across {len(tasks)} visible tasks.{lead}"
    )


def _tool_result(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _text_summary(report)}],
        "structuredContent": report,
    }


def _handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"resources": {}, "tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "resources/list":
        return {
            "resources": [
                {
                    "uri": CARD_RESOURCE_URI,
                    "name": "Codex Usage status card",
                    "description": "Compact expandable local Codex usage status.",
                    "mimeType": "text/html;profile=mcp-app",
                }
            ]
        }
    if method == "resources/templates/list":
        return {"resourceTemplates": []}
    if method == "resources/read":
        uri = params.get("uri")
        if uri != CARD_RESOURCE_URI and uri not in LEGACY_CARD_RESOURCE_URIS:
            raise RuntimeError(f"Unknown resource: {uri}")
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/html;profile=mcp-app",
                    "text": CARD_HTML,
                    "_meta": {
                        "ui": {"prefersBorder": False},
                        "openai/widgetDescription": "Compact local Codex usage status with expandable task details.",
                        "openai/widgetHeightHint": 48,
                        "openai/widgetMinFrameHeight": 48,
                        "openai/widgetPrefersBorder": False,
                        "openai/widgetShowCodexWidgetInline": True,
                    },
                }
            ]
        }
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "show_usage_card":
            return _tool_result(usage_card(arguments, include_details=False))
        if name == "refresh_usage_card":
            return _tool_result(
                usage_card(
                    {
                        "thread_id": arguments.get("thread_id"),
                        "live": bool(arguments.get("live", True)),
                        "live_until_epoch_ms": arguments.get(
                            "live_until_epoch_ms"
                        ),
                    },
                    include_details=True,
                )
            )
        if name == "get_usage_preferences":
            return _tool_result(usage_preferences())
        if name == "set_auto_card_interval":
            return _tool_result(update_auto_card_interval(arguments))
        if name == "open_usage_dashboard":
            return _tool_result(open_usage_dashboard(arguments))
        if name == "current_conversation_usage":
            return _tool_result(current_conversation_usage(arguments))
        if name == "usage_dashboard":
            return _tool_result(usage_dashboard(arguments))
        raise RuntimeError(f"Unknown tool: {name}")
    if method in {"logging/setLevel", "notifications/initialized", "notifications/cancelled"}:
        return {}
    raise RuntimeError(f"Unsupported method: {method}")


def _serve() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            request_id = request.get("id")
            if request_id is None:
                continue
            result = _handle(request.get("method", ""), request.get("params") or {})
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if "request" in locals() else None,
                "error": {"code": -32603, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def _self_test() -> None:
    with _connect() as connection:
        limit = _latest_rate_limit(connection)
    report = usage_dashboard({"range": "current_window"})
    output = {
        "database": "ok",
        "dashboard": DASHBOARD_PATH.exists(),
        "card": CARD_PATH.exists(),
        "limit": limit,
        "visibleTasks": len(report["tasks"]),
        "sources": len(report["sources"]),
        "totalTokens": report["totals"]["totalTokens"],
    }
    current_id = os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
    if current_id:
        current = current_conversation_usage({"thread_id": current_id})
        card = usage_card({"thread_id": current_id})
        output["currentThread"] = current["thread"]["name"]
        output["currentTokens"] = current["combinedTokens"]
        output["contextPercent"] = card["context"]["usedPercent"]
        output["cardResource"] = _handle(
            "resources/read", {"uri": CARD_RESOURCE_URI}
        )["contents"][0]["mimeType"]
        legacy_uri = next(iter(LEGACY_CARD_RESOURCE_URIS))
        output["legacyCardResource"] = _handle(
            "resources/read", {"uri": legacy_uri}
        )["contents"][0]["uri"]
    panel = open_usage_dashboard({"thread_id": current_id, "range": "current_window"})
    with urlopen(panel["dashboardUrl"].replace("/?", "/health?"), timeout=5) as response:
        output["panelHealth"] = json.loads(response.read().decode("utf-8"))["ok"]
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    elif "--serve-dashboard" in sys.argv:
        panel = open_usage_dashboard({"range": "current_window"})
        print(panel["dashboardUrl"], flush=True)
        threading.Event().wait()
    else:
        _serve()
