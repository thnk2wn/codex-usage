"""Pins the size and content of the message the prompt hook injects.

The hook's additionalContext becomes a developer message that persists in the
transcript and is re-read by every later turn, so its size is a recurring cost
on every automatic card. These tests run the real hook script.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "auto_usage_card.py"
THREAD = "01a0a5c2-c8de-79c1-bb84-222c77f62008"

# Generous ceiling above the ~180 characters the message measures today, so a
# future edit that quietly grows it back toward the old 387 fails here.
MAX_CHARS = 220


def _run_hook(codex_home: str, session_id: str = THREAD) -> dict | None:
    event = json.dumps({"session_id": session_id})
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=event,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "CODEX_HOME": codex_home},
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


class HookInstructionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _context(self) -> str:
        output = _run_hook(self.temporary.name)
        self.assertIsNotNone(output, "first turn in a fresh task should emit a card request")
        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "UserPromptSubmit")
        return specific["additionalContext"]

    def test_message_names_the_tool_and_carries_the_arguments(self) -> None:
        context = self._context()
        self.assertIn("mcp__codex_usage__show_usage_card", context)
        arguments = json.dumps(
            {"thread_id": THREAD, "live": True, "automatic": True},
            separators=(",", ":"),
        )
        self.assertIn(arguments, context)

    def test_message_still_suppresses_narration(self) -> None:
        # The one behavioural clause kept in-turn, because the skill alone is a
        # weaker guarantee against the model announcing the card call.
        self.assertIn("Do not mention it", self._context())

    def test_message_stays_small(self) -> None:
        context = self._context()
        self.assertLessEqual(
            len(context),
            MAX_CHARS,
            f"hook message grew to {len(context)} chars; the behaviour belongs in SKILL.md",
        )

    def test_behaviour_lives_in_the_skill(self) -> None:
        skill = (ROOT / "skills" / "codex-usage" / "SKILL.md").read_text(encoding="utf-8")
        for clause in (
            "exactly once before other work",
            "without narrating the card call",
            "If the tool is unavailable, continue without retrying",
        ):
            self.assertIn(clause, skill)

    def test_nothing_is_emitted_while_rate_limited(self) -> None:
        self.assertIsNotNone(_run_hook(self.temporary.name))
        self.assertIsNone(_run_hook(self.temporary.name), "second turn inside the interval must be silent")


if __name__ == "__main__":
    unittest.main()
