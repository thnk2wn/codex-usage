from __future__ import annotations

import sys
import unittest
from datetime import datetime
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

    def test_initial_card_skips_dashboard_then_refresh_loads_it(self) -> None:
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
            patch.object(server, "current_conversation_usage", return_value=current),
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
            # The reference carries the caller's live setting so the fallback
            # cannot silently start polling; the deadline is a moving value.
            self.assertTrue(reference["live"])
            self.assertIn("liveUntilEpochMs", reference)
            initial = initial_result["_meta"][server.CARD_REPORT_META_KEY]

            self.assertFalse(initial["detailsLoaded"])
            self.assertIsNone(initial["windowUsage"])
            self.assertEqual(initial["topTasks"], [])
            generated_ms = datetime.fromisoformat(initial["generatedAt"]).timestamp() * 1000
            self.assertAlmostEqual(
                initial["liveRefresh"]["untilEpochMs"] - generated_ms,
                20 * 60 * 1000,
                delta=1,
            )
            self.assertEqual(initial["liveRefresh"]["intervalMs"], 15_000)
            scan.assert_not_called()

            refreshed = server._handle(
                "tools/call",
                {
                    "name": "refresh_usage_card",
                    "arguments": {
                        "thread_id": "task-1",
                        "live_until_epoch_ms": 9_999_999_999_999,
                        "live": True,
                    },
                },
            )["structuredContent"]

            self.assertTrue(refreshed["detailsLoaded"])
            self.assertEqual(refreshed["windowUsage"], dashboard["totals"])
            self.assertEqual(refreshed["topTasks"][0]["name"], "Test task")
            scan.assert_called_once_with("current_window", False, 300)


if __name__ == "__main__":
    unittest.main()
