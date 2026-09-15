# Codex Usage

A private, local-first Codex plugin that attributes raw processed tokens to conversations, subagents, automations, and internal activity.

It is designed for personal installation; publishing it to a shared marketplace is optional.

## Install

This repository is also a small Git marketplace, so installation does not require publication or OpenAI marketplace review.

```bash
codex plugin marketplace add git@github.com:thnk2wn/codex-usage.git --ref main
codex plugin add codex-usage@thnk2wn
```

Start a new Codex task after installation so the skill and tools are loaded. The repository is currently private, so the installing user needs GitHub read access and working SSH credentials.

To pick up a newer version later:

```bash
codex plugin marketplace upgrade thnk2wn
codex plugin add codex-usage@thnk2wn
```

## Share privately

For teammates, grant read access to this repository and send them the two installation commands above. That is a private Git marketplace: distribution and access stay under GitHub, with no public listing or external approval workflow.

For wider organization distribution, transfer or mirror the repository into the organization and change the Git URL in the install command and `.claude-plugin/marketplace.json`. A public or OpenAI-curated marketplace listing can remain a later step after the plugin has been tested more broadly.

## Public marketplace

This build is intentionally not submitted to OpenAI's universal Plugins Directory. Public submission requires a verified publisher, production listing and policy materials, reproducible test cases, automated scanning, and OpenAI review. MCP-backed submissions normally also require a stable public HTTPS server.

Codex Usage instead runs its MCP server locally because its core purpose is reading local Codex metadata without uploading it. Publishing it universally would therefore require either explicit OpenAI support for a local MCP design or a privacy-sensitive architectural change. The private Git marketplace above keeps the current local-only behavior intact.

See [OpenAI's plugin submission documentation](https://developers.openai.com/plugins/deploy/submission) for the current public review requirements.

## UI surfaces

- `show_usage_card` renders a compact native usage-data row directly in the conversation, without a separate tool disclosure after loading. Clicking the row expands clearly defined token metrics, a limit-window pace projection, a subdued compaction notice, and the top five tasks. Each task row expands to show why its raw total is large.
- Mobile Remote falls back to a single-line status result when it does not render the MCP App iframe; say `usage details` for a text breakdown.
- `open_usage_dashboard` starts the optional private localhost dashboard for a larger cross-task view.
- `current_conversation_usage` returns a concise snapshot for the active conversation when a panel is not needed.
- `usage_dashboard` returns structured cross-task data for the current limit window, today, or rolling 7/30-day ranges.

## Data and privacy

The MCP server reads `~/.codex/state_5.sqlite` and the rollout files already referenced by that database. It is read-only, binds its optional dashboard only to `127.0.0.1`, uses no external network access, and stores no copy of task content. Task names are displayed locally in the card and dashboard.

Cards render when the tool is invoked. Codex hooks cannot independently push unsolicited UI into an idle conversation, so the plugin does not claim background popup alerts.

The numbers are raw local token counters, not a server-authoritative quota ledger. The aggregate usage percentage is the latest coarse snapshot recorded in local session metadata.

## Development

```bash
/usr/bin/python3 scripts/server.py --self-test
```

After changing a locally installed copy, update its cachebuster and reinstall it from the personal marketplace before testing in a new Codex task.

## License

MIT
