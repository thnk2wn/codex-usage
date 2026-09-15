---
name: codex-usage
description: Show Codex usage for the current conversation or across local tasks. Use whenever the user asks about usage, limits, context pressure, token consumption, expensive sessions, which task used capacity, or requests a Codex Usage card or dashboard.
---

# Codex Usage

Use the plugin's read-only tools instead of querying Codex's private SQLite database or session JSONL files directly.

## Native usage card

Call `show_usage_card` by default when the user asks to show, display, view, or check Codex usage. Always pass the current Codex task ID from the task context as `thread_id`; never make an initial call without it. The card first appears as a compact usage-data row. The user can click that row to expand current-context pressure, latest response output, cached input, subagents, account reset, and top tasks.

Mobile Remote currently preserves the tool result but may not render the MCP App iframe. The text fallback is intentionally one line and tells the user to say `usage details`. When the user asks for those details after a text-only result, call `show_usage_card` again and summarize its structured result in text: context input/window, latest output, cached input, subagents, account usage/reset, alerts, and top tasks. Do not claim that the one-line mobile result is clickable or expandable.

Do not render the card after unrelated replies. MCP UI is tool-result UI and cannot be pushed independently by a background daemon. Do not claim automatic popup alerts. The card may highlight context pressure or a large latest response when it is invoked.

## Optional dashboard

When the user explicitly asks for the full dashboard or a larger cross-task view:

1. Call `open_usage_dashboard` with the closest requested range. Omit `thread_id` so the server scopes the panel to the current task.
2. Read `dashboardUrl` from the tool's structured result.
3. Call the Codex app's `open_in_codex` tool with a browser target using that URL and `placement: "right"`.

The localhost panel refreshes automatically and combines this conversation with the cross-task view. Do not also render a card unless the user asks for both. Explain that the panel lives while the current task and its local MCP process remain open.

## Current conversation

Call `current_conversation_usage` when the user asks for a concise answer about how much this conversation, session, task, or thread has used without asking to open the panel. Always pass the current Codex task ID from the task context as `thread_id`. Pass a different explicit thread ID only when the user names a different task and its ID is already known.

Briefly summarize the result, distinguishing:

- the conversation's own raw tokens;
- child/subagent raw tokens;
- cached input;
- the account's aggregate usage percentage when available.

## Across conversations

Call `usage_dashboard` for cross-task questions. Choose the closest range:

- `current_window` for the active Codex limit window;
- `today` for local midnight through now;
- `last_7_days` or `last_30_days` for rolling ranges.

Set `include_internal` only when the user explicitly wants internal approval/guardrail activity included in task rows. Source totals remain visible so the user can see that supporting activity exists.

## Interpretation

Always describe task values as **raw processed tokens**, not billing or exact quota percentage. Codex's local transcripts expose token counters and coarse aggregate limit snapshots, but not the server-side formula that converts work into subscription capacity. Cached input, model choice, reasoning effort, automations, subagents, and internal reviews may be weighted differently.

The plugin is local-only. Do not imply that its data was uploaded, published, or submitted to a marketplace.
