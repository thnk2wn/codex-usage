from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402


def _card_report() -> dict:
    return {
        "kind": "usage_card",
        "thread": {"id": "task-1", "name": "Test task"},
        "context": {"usedPercent": 53.0},
        "combinedTokens": 74_800_000,
        "limit": None,
        "pace": None,
        "topTasks": [],
        "alerts": [],
        "preferences": {"autoCardEnabled": True, "autoCardIntervalSeconds": 300},
    }


class CardToolResultTest(unittest.TestCase):
    def test_report_travels_in_meta(self) -> None:
        report = _card_report()
        result = server._card_tool_result(report)
        self.assertIs(result["_meta"][server.CARD_REPORT_META_KEY], report)

    def test_model_visible_payload_excludes_the_report(self) -> None:
        result = server._card_tool_result(_card_report())
        visible = json.dumps(
            {key: value for key, value in result.items() if key != "_meta"}
        )
        self.assertNotIn("combinedTokens", visible)
        self.assertNotIn("topTasks", visible)

    def test_mobile_fallback_has_no_json_panel(self) -> None:
        result = server._card_tool_result(_card_report())
        self.assertEqual(set(result), {"content", "_meta"})
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertTrue(
            all(len(line) <= 36 for line in result["content"][0]["text"].splitlines())
        )

    def test_summary_line_is_still_present_for_the_model(self) -> None:
        result = server._card_tool_result(_card_report())
        text = result["content"][0]["text"]
        self.assertTrue(text)
        self.assertIn("Usage", text)

    def _visible(self, report: dict) -> str:
        card = server._card_tool_result(report)
        return json.dumps(
            {key: value for key, value in card.items() if key != "_meta"},
            separators=(",", ":"),
        )

    def test_model_visible_size_does_not_grow_with_the_report(self) -> None:
        # This is the property that bounds cost: a bigger report must not make
        # the transcript entry bigger, because the growth lives in _meta.
        small = _card_report()
        large = _card_report()
        large["topTasks"] = [
            {
                "id": f"task-{index}",
                "name": f"A task with a reasonably long name {index}",
                "totalTokens": 12_345_678,
                "sharePercent": 4.2,
            }
            for index in range(5)
        ]
        self.assertGreater(
            len(json.dumps(server._tool_result(large), separators=(",", ":"))),
            len(json.dumps(server._tool_result(small), separators=(",", ":"))),
        )
        self.assertEqual(len(self._visible(large)), len(self._visible(small)))

    def test_component_detail_path_still_returns_structured_content(self) -> None:
        # The one-time expansion request stays outside the transcript.
        result = server._tool_result(_card_report())
        self.assertEqual(result["structuredContent"]["kind"], "usage_card")


class TextFallbackContractTest(unittest.TestCase):
    """The card tells users to say "usage details"; that path must stay readable.

    A card's render data is component-only, so a client that cannot draw the
    component has nothing to summarise from show_usage_card. usage_details is
    the model-visible path that keeps that promise.
    """

    def _tool(self, name: str) -> dict:
        return next(tool for tool in server.TOOLS if tool["name"] == name)

    def test_usage_details_tool_is_exposed(self) -> None:
        tool = self._tool("usage_details")
        self.assertIn("thread_id", tool["inputSchema"]["properties"])
        self.assertEqual(tool["inputSchema"].get("required"), ["thread_id"])

    def test_usage_details_is_not_a_component(self) -> None:
        # No ui resource: this path exists to be read, not rendered.
        self.assertNotIn("ui", (self._tool("usage_details").get("_meta") or {}))

    def test_card_summary_still_points_at_the_details_phrase(self) -> None:
        text = server._text_summary(_card_report())
        self.assertIn("usage details", text)

    def test_skill_routes_the_details_phrase_away_from_the_card(self) -> None:
        skill = (
            Path(server.PLUGIN_ROOT) / "skills" / "codex-usage" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("usage_details", skill)


class CardResourceTest(unittest.TestCase):
    def test_card_resource_uri_stays_stable(self) -> None:
        # ac487d8 deliberately stopped bumping this; the manifest version is the
        # cachebuster for UI revisions, so a card change must not move the URI.
        self.assertEqual(
            server.CARD_RESOURCE_URI, "ui://codex-usage/status-card-v7.html"
        )
        self.assertNotIn(server.CARD_RESOURCE_URI, server.LEGACY_CARD_RESOURCE_URIS)

    def test_manifest_base_version_matches_the_server(self) -> None:
        manifest = json.loads(
            (Path(server.PLUGIN_ROOT) / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["version"].split("+", 1)[0], server.SERVER_VERSION)
        self.assertNotEqual(manifest["version"], "0.2.0")

    def test_card_announces_the_server_version(self) -> None:
        # The ui/initialize handshake hard-codes a version string; keep it from
        # drifting behind the manifest the way it did across the last two bumps.
        self.assertIn(
            f"version: '{server.SERVER_VERSION}'", server.CARD_HTML
        )

    def test_card_html_reads_the_meta_key(self) -> None:
        self.assertIn(server.CARD_REPORT_META_KEY, server.CARD_HTML)


if __name__ == "__main__":
    unittest.main()
