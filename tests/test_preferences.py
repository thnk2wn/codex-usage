from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from preferences import claim_auto_card, get_preferences, set_auto_card_interval  # noqa: E402


class PreferencesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = self.temporary.name

    def tearDown(self) -> None:
        if self.previous_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self.previous_codex_home
        self.temporary.cleanup()

    def test_default_and_rate_limit(self) -> None:
        self.assertEqual(get_preferences()["autoCardIntervalSeconds"], 300)
        self.assertTrue(claim_auto_card("task-1", now=1000))
        self.assertFalse(claim_auto_card("task-1", now=1299))
        self.assertTrue(claim_auto_card("task-1", now=1300))

    def test_every_turn_and_off(self) -> None:
        set_auto_card_interval(0)
        self.assertTrue(claim_auto_card("task-1", now=1000))
        self.assertTrue(claim_auto_card("task-1", now=1000))

        set_auto_card_interval(-1)
        self.assertFalse(claim_auto_card("task-1", now=2000))

    def test_rejects_unknown_interval(self) -> None:
        with self.assertRaises(ValueError):
            set_auto_card_interval(45)


if __name__ == "__main__":
    unittest.main()
