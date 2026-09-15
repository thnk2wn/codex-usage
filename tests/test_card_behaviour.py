"""Runs the Node-based card behaviour suite as part of the Python test run.

The card is plain JavaScript inside an HTML asset, so its logic is exercised in
a stub host rather than by importing it. Skipped when Node is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT / "tests" / "card_behaviour.test.js"


class CardBehaviourTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_card_behaviour_suite_passes(self) -> None:
        result = subprocess.run(
            ["node", str(SUITE)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"card behaviour suite failed:\n{result.stdout}\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
