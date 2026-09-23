from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402


class UsageCardTest(unittest.TestCase):
    def test_component_only_tools_are_hidden_from_the_model(self) -> None:
        descriptors = {tool["name"]: tool for tool in server.TOOLS}

        for name in (
            "refresh_usage_card",
            "get_usage_preferences",
            "current_conversation_usage",
        ):
            self.assertEqual(
                descriptors[name]["_meta"]["ui"]["visibility"],
                ["app"],
            )
        self.assertEqual(
            descriptors["show_usage_card"]["_meta"]["ui"]["visibility"],
            ["model", "app"],
        )

    def test_compact_card_skips_dashboard_until_details_are_requested(self) -> None:
        current = {
            "thread": {"id": "task-1", "name": "Test task"},
            "ownUsage": {"totalTokens": 1000, "cachedPercent": 80},
            "latestTurn": {"outputTokens": 20, "totalTokens": 100},
            "context": {
                "inputTokens": 80,
                "windowTokens": 1000,
                "usedPercent": 8,
            },
            "subagents": [],
            "subagentTokens": 0,
            "combinedTokens": 1000,
            "limit": None,
        }
        dashboard = {
            "totals": {"totalTokens": 3000},
            "tasks": [
                {
                    "id": "task-1",
                    "name": "Test task",
                    "source": "cli",
                    "model": "test-model",
                    "project": "test-project",
                    "responses": 2,
                    "inputTokens": 2500,
                    "cachedInputTokens": 2000,
                    "cachedPercent": 80,
                    "outputTokens": 500,
                    "reasoningOutputTokens": 100,
                    "totalTokens": 3000,
                    "sharePercent": 100,
                }
            ],
        }

        with (
            patch.object(server, "current_conversation_usage", return_value=current) as current_read,
            patch.object(server, "_cached_usage_dashboard", return_value=dashboard) as scan,
            patch.object(
                server,
                "get_preferences",
                return_value={
                    "autoCardEnabled": True,
                    "autoCardIntervalSeconds": 300,
                },
            ),
        ):
            initial_result = server._handle(
                "tools/call",
                {
                    "name": "show_usage_card",
                    "arguments": {"thread_id": "task-1", "live": True},
                },
            )
            # The card renders from component-only _meta; the transcript sees
            # only a summary line and a reference back to this thread.
            reference = initial_result["structuredContent"]
            self.assertEqual(reference["kind"], "usage_card_ref")
            self.assertEqual(reference["threadId"], "task-1")
            self.assertEqual(set(reference), {"kind", "threadId", "snapshotId"})
            initial = initial_result["_meta"][server.CARD_REPORT_META_KEY]

            self.assertFalse(initial["detailsLoaded"])
            self.assertIsNone(initial["windowUsage"])
            self.assertEqual(initial["topTasks"], [])
            self.assertFalse(initial["liveRefresh"]["enabled"])
            scan.assert_not_called()

            recovered = server._handle(
                "tools/call",
                {
                    "name": "refresh_usage_card",
                    "arguments": {
                        "thread_id": "task-1",
                        "include_details": False,
                        "snapshot_id": reference["snapshotId"],
                    },
                },
            )["structuredContent"]
            self.assertFalse(recovered["detailsLoaded"])
            self.assertEqual(recovered["generatedAt"], initial["generatedAt"])
            current_read.assert_called_once()
            scan.assert_not_called()

            with self.assertRaisesRegex(RuntimeError, "original card snapshot"):
                server._handle(
                    "tools/call",
                    {
                        "name": "refresh_usage_card",
                        "arguments": {
                            "thread_id": "task-1",
                            "include_details": False,
                            "snapshot_id": "missing",
                        },
                    },
                )

            detailed = server._handle(
                "tools/call",
                {
                    "name": "refresh_usage_card",
                    "arguments": {
                        "thread_id": "task-1",
                        "include_details": True,
                    },
                },
            )["structuredContent"]

            self.assertTrue(detailed["detailsLoaded"])
            self.assertEqual(detailed["windowUsage"], dashboard["totals"])
            self.assertEqual(detailed["topTasks"][0]["name"], "Test task")
            self.assertFalse(detailed["liveRefresh"]["enabled"])
            scan.assert_called_once_with("current_window", False, 300)


if __name__ == "__main__":
    unittest.main()
