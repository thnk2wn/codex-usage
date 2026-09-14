---
name: codex-usage
description: Show Codex usage for the current conversation or across local tasks. Use whenever the user asks about usage, limits, token consumption, expensive sessions, which task used capacity, or requests the Codex Usage dashboard.
---

# Codex Usage

Use the plugin's read-only tools instead of querying Codex's private SQLite database or session JSONL files directly.

## Panel dashboard

When the user asks to open, show, view, launch, or keep the usage dashboard visible:

1. Call `open_usage_dashboard` with the closest requested range. Omit `thread_id` so the server scopes the panel to the current task.
2. Read `dashboardUrl` from the tool's structured result.
3. Call the Codex app's `open_in_codex` tool with a browser target using that URL and `placement: "right"`.

The localhost panel refreshes automatically and combines this conversation with the cross-task view. Do not also render an inline usage widget unless the user asks for one. Explain that the panel lives while the current task and its local MCP process remain open.

## Current conversation

Call `current_conversation_usage` when the user asks for a concise answer about how much this conversation, session, task, or thread has used without asking to open the panel. Omit `thread_id` so the server uses the current Codex thread. Pass an explicit thread ID only when the user names a different task and its ID is already known.

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
