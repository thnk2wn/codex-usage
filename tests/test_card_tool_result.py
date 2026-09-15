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

    def test_reference_carries_the_thread_id_for_rehydration(self) -> None:
        result = server._card_tool_result(_card_report())
        self.assertEqual(result["structuredContent"]["kind"], "usage_card_ref")
        self.assertEqual(result["structuredContent"]["threadId"], "task-1")

    def test_reference_survives_a_missing_thread(self) -> None:
        report = _card_report()
        report.pop("thread")
        result = server._card_tool_result(report)
        self.assertIsNone(result["structuredContent"]["threadId"])

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

    def test_refresh_path_still_returns_structured_content(self) -> None:
        # The card requests refreshes itself; those never enter the transcript,
        # so they keep the full structured payload the widget already reads.
        result = server._tool_result(_card_report())
        self.assertEqual(result["structuredContent"]["kind"], "usage_card")


class CardResourceTest(unittest.TestCase):
    def test_cachebuster_advanced_and_old_uri_retired(self) -> None:
        self.assertIn("v8", server.CARD_RESOURCE_URI)
        self.assertIn(
            "ui://codex-usage/status-card-v7.html", server.LEGACY_CARD_RESOURCE_URIS
        )
        self.assertNotIn(server.CARD_RESOURCE_URI, server.LEGACY_CARD_RESOURCE_URIS)

    def test_card_html_reads_the_meta_key(self) -> None:
        self.assertIn(server.CARD_REPORT_META_KEY, server.CARD_HTML)


if __name__ == "__main__":
    unittest.main()
