from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402


def _token_event(timestamp: str, total: int) -> str:
    record = {
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": {
                    "input_tokens": total,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_output_tokens": 0,
                    "total_tokens": total,
                }
            },
        },
    }
    return json.dumps(record)


class ResolveEventEpochsTest(unittest.TestCase):
    def test_distinct_timestamps_are_left_alone(self) -> None:
        raw = [100.0, 200.0, 300.0]
        self.assertEqual(server._resolve_event_epochs(raw, (0, 1000)), raw)

    def test_single_event_is_left_alone(self) -> None:
        raw = [100.0]
        self.assertEqual(server._resolve_event_epochs(raw, (0, 1000)), raw)

    def test_missing_span_leaves_events_alone(self) -> None:
        raw = [100.0, 100.0]
        self.assertEqual(server._resolve_event_epochs(raw, None), raw)

    def test_empty_span_leaves_events_alone(self) -> None:
        raw = [100.0, 100.0]
        self.assertEqual(server._resolve_event_epochs(raw, (500, 500)), raw)

    def test_collapsed_timestamps_spread_across_the_span(self) -> None:
        raw = [100.0, 100.0, 100.0, 100.0]
        spread = server._resolve_event_epochs(raw, (0, 400))
        self.assertEqual(spread, [50.0, 150.0, 250.0, 350.0])

    def test_spread_events_stay_inside_the_span(self) -> None:
        raw = [100.0] * 5
        spread = server._resolve_event_epochs(raw, (1000, 2000))
        self.assertTrue(all(1000 <= value <= 2000 for value in spread))


class SumRolloutTest(unittest.TestCase):
    def _write(self, lines: list[str]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        handle.write("\n".join(lines) + "\n")
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def test_healthy_timestamps_are_filtered_normally(self) -> None:
        path = self._write(
            [
                _token_event("2026-09-15T00:00:00Z", 10),
                _token_event("2026-09-15T01:00:00Z", 20),
                _token_event("2026-09-15T02:00:00Z", 40),
            ]
        )
        window_start = int(server._event_epoch("2026-09-15T00:30:00Z"))
        window_end = int(server._event_epoch("2026-09-15T01:30:00Z"))

        totals = server._sum_rollout(str(path), window_start, window_end)

        self.assertEqual(totals["totalTokens"], 20)
        self.assertEqual(totals["responses"], 1)

    def test_collapsed_session_is_spread_instead_of_bunched(self) -> None:
        stamp = "2026-09-15T00:00:00Z"
        path = self._write([_token_event(stamp, 10) for _ in range(4)])
        session_start = int(server._event_epoch(stamp))
        session_end = session_start + 4000
        span = (session_start, session_end)

        late_start = session_start + 2000
        late_end = session_end
        totals = server._sum_rollout(str(path), late_start, late_end, span)

        self.assertEqual(totals["totalTokens"], 20)
        self.assertEqual(totals["responses"], 2)

    def test_collapsed_session_without_span_keeps_old_behaviour(self) -> None:
        stamp = "2026-09-15T00:00:00Z"
        path = self._write([_token_event(stamp, 10) for _ in range(4)])
        session_start = int(server._event_epoch(stamp))

        late = server._sum_rollout(
            str(path), session_start + 2000, session_start + 4000
        )

        self.assertEqual(late["totalTokens"], 0)

    def test_whole_collapsed_session_still_totals_correctly(self) -> None:
        stamp = "2026-09-15T00:00:00Z"
        path = self._write([_token_event(stamp, 10) for _ in range(4)])
        session_start = int(server._event_epoch(stamp))
        span = (session_start, session_start + 4000)

        totals = server._sum_rollout(
            str(path), session_start, session_start + 4000, span
        )

        self.assertEqual(totals["totalTokens"], 40)
        self.assertEqual(totals["responses"], 4)

    def test_responses_counts_events_not_fields(self) -> None:
        path = self._write([_token_event("2026-09-15T00:00:00Z", 10)])
        totals = server._sum_rollout(str(path), 0, 4102444800)
        self.assertEqual(totals["responses"], 1)


if __name__ == "__main__":
    unittest.main()
