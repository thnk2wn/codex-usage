#!/usr/bin/env python3
"""Ask Codex to render a fresh usage card when this task's interval is due."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from preferences import claim_auto_card  # noqa: E402


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return

    session_id = str(event.get("session_id") or "").strip()
    if not claim_auto_card(session_id):
        return

    tool_arguments = json.dumps(
        {"thread_id": session_id, "live": True, "automatic": True},
        separators=(",", ":"),
    )
    # This message is injected into the transcript on every qualifying turn and is
    # re-read by every later turn, so it carries only the trigger and arguments.
    # The behaviour (call once, first, do not narrate, do not retry if the tool is
    # unavailable) lives in skills/codex-usage/SKILL.md, which loads once per
    # session rather than once per card.
    instruction = (
        "Codex Usage card due. Call mcp__codex_usage__show_usage_card once, first, "
        f"with {tool_arguments}. Do not mention it."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": instruction,
                }
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
