---
name: codex-usage
description: Show Codex usage for the current conversation or across local tasks. Use whenever the user asks about usage, limits, context pressure, token consumption, expensive sessions, which task used capacity, or requests a Codex Usage card or dashboard.
---

# Codex Usage

Use the plugin's tools instead of querying Codex's private SQLite database or session JSONL files directly. Usage reads are local and read-only; only the automatic-card preference writes plugin state.

## Native usage card

Call `show_usage_card` by default when the user asks to show, display, view, or check Codex usage. Always pass the current Codex task ID from the task context as `thread_id`; never make an initial call without it. The card first appears as a compact usage-data row with its creation time. The user can click that row to expand current-context pressure, latest-response tokens, cached input, direct child tasks, account reset, average-window pace, the top five tasks, and the automatic-card interval. Each top-task row expands to show its token composition.

Mobile Remote currently preserves the tool result but may not render the MCP App iframe. The text fallback is intentionally one line and tells the user to say `usage details`. When the user asks for those details after a text-only result, call `usage_details` with the same `thread_id` and summarize its structured result in text: context input/window, latest output, cached input, subagents, account usage/reset, alerts, and top tasks. Use `usage_details` rather than `show_usage_card` for this, because a card's render data is delivered to the component only and is not readable in the tool result. Do not claim that the one-line mobile result is clickable or expandable.

The plugin's trusted `UserPromptSubmit` and `PostToolUse` hooks may add developer context saying a Codex Usage card is due. That message is deliberately terse, because it is re-read on every later turn; the behaviour is defined here. When it appears, call `show_usage_card` exactly once before other work with the supplied `thread_id`, `live: true`, and `automatic: true`, then continue the user's request without narrating the card call or adding a usage summary of your own. The named `show_usage_card` tool is the only tool that renders the visual inline card; `current_conversation_usage` returns plain text and JSON. If the tool is unavailable, continue without retrying it. The hooks share a per-task 15-minute default rate limit, so do not second-guess or duplicate them. If neither hook says a card is due, do not render one after an unrelated reply.

Each newly rendered card returns its compact current-task header first. It loads the heavier cross-task breakdown only on first expansion, then keeps its usage values fixed; the footer shows both creation and details-load times. A subsequent card is a new conversation item and never rewrites an older card. The expanded card can set the minimum gap between new automatic cards, applied independently per task, to every turn, 30 seconds, 1 minute, 5 minutes, 15 minutes, or off. The hook's `live: true` argument is accepted for compatibility but does not enable polling. Do not claim background popup alerts when no user turn is running.

## Optional dashboard

When the user explicitly asks for the full dashboard or a larger cross-task view:

1. Call `open_usage_dashboard` with the closest requested range. Omit `thread_id` so the server scopes the panel to the current task.
2. Read `dashboardUrl` from the tool's structured result.
3. Call the Codex app's `open_in_codex` tool with a browser target using that URL and `placement: "right"`.

The localhost panel refreshes automatically and combines this conversation with the cross-task view. Do not also render a card unless the user asks for both. Explain that the panel lives while the current task and its local MCP process remain open.

## Current conversation

Call `show_usage_card` when the user asks how much this conversation, session, task, or thread has used without asking to open the panel. Always pass the current Codex task ID from the task context as `thread_id`. Pass a different explicit thread ID only when the user names a different task and its ID is already known. The compact card result gives a one-line answer and expandable detail.

If the user explicitly wants a text breakdown instead of the card, call `usage_details` and briefly summarize:

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

The account pace projection uses the aggregate limit percentage and elapsed time in the active window. Describe it as a changing estimate, not a guarantee. It does not infer pace from raw per-task tokens.

The plugin is local-only. Do not imply that its data was uploaded, published, or submitted to a marketplace.
