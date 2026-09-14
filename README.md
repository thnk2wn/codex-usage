# Codex Usage

A private, local-first Codex plugin that attributes raw processed tokens to conversations, subagents, automations, and internal activity.

It is designed for personal installation; publishing it to a shared marketplace is optional.

## UI surfaces

- `open_usage_dashboard` starts a private localhost dashboard intended for a persistent Codex right-hand browser panel. It shows the active conversation and the cross-task view together and refreshes automatically.
- `current_conversation_usage` returns a concise snapshot for the active conversation when a panel is not needed.
- `usage_dashboard` returns structured cross-task data for the current limit window, today, since Friday, or rolling 7/30-day ranges.

## Data and privacy

The MCP server reads `~/.codex/state_5.sqlite` and the rollout files already referenced by that database. It is read-only, binds its dashboard only to `127.0.0.1`, uses no external network access, and stores no copy of task content. Task names are displayed locally in the panel.

The numbers are raw local token counters, not a server-authoritative quota ledger. The aggregate usage percentage is the latest coarse snapshot recorded in local session metadata.

## Development

```bash
/usr/bin/python3 scripts/server.py --self-test
```

After changing a locally installed copy, update its cachebuster and reinstall it from the personal marketplace before testing in a new Codex task.

## License

MIT
