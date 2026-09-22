"""Persistent preferences and rate-limit state for Codex Usage."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


DEFAULT_AUTO_CARD_INTERVAL_SECONDS = 900
AUTO_CARD_INTERVAL_OPTIONS = {-1, 0, 30, 60, 300, 900}
STATE_RETENTION_SECONDS = 30 * 24 * 60 * 60


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _data_dir() -> Path:
    return _codex_home() / "codex-usage"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def get_preferences() -> dict[str, Any]:
    stored = _read_json(_data_dir() / "preferences.json")
    interval = stored.get(
        "autoCardIntervalSeconds", DEFAULT_AUTO_CARD_INTERVAL_SECONDS
    )
    if not isinstance(interval, int) or interval not in AUTO_CARD_INTERVAL_OPTIONS:
        interval = DEFAULT_AUTO_CARD_INTERVAL_SECONDS
    return {
        "autoCardEnabled": interval >= 0,
        "autoCardIntervalSeconds": interval,
    }


def set_auto_card_interval(interval_seconds: int) -> dict[str, Any]:
    if interval_seconds not in AUTO_CARD_INTERVAL_OPTIONS:
        allowed = ", ".join(str(value) for value in sorted(AUTO_CARD_INTERVAL_OPTIONS))
        raise ValueError(f"interval_seconds must be one of: {allowed}")
    preferences = {"autoCardIntervalSeconds": interval_seconds}
    _write_json(_data_dir() / "preferences.json", preferences)
    return get_preferences()


def claim_auto_card(session_id: str, now: float | None = None) -> bool:
    """Return true and reserve this task's next automatic card when it is due."""
    if not session_id:
        return False

    preferences = get_preferences()
    interval = int(preferences["autoCardIntervalSeconds"])
    if interval < 0:
        return False

    current = time.time() if now is None else now
    state_path = _data_dir() / "auto-card-state.json"
    state = _read_json(state_path)
    sessions = state.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}

    previous = sessions.get(session_id)
    if isinstance(previous, (int, float)) and current - float(previous) < interval:
        return False

    cutoff = current - STATE_RETENTION_SECONDS
    sessions = {
        key: value
        for key, value in sessions.items()
        if isinstance(value, (int, float)) and float(value) >= cutoff
    }
    sessions[session_id] = current
    _write_json(state_path, {"sessions": sessions})
    return True
