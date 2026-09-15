# Codex Usage

A private, local-first Codex plugin that attributes raw processed tokens to conversations, subagents, automations, and internal activity. It supports personal installs, private workspace distribution, and self-contained GitHub release bundles without public marketplace publication.

![Codex Usage expanded usage card](assets/codex-usage-card.png)

## Install

This repository is also a small Git marketplace, so installation does not require publication or OpenAI marketplace review.

```bash
codex plugin marketplace add git@github.com:thnk2wn/codex-usage.git --ref main
codex plugin add codex-usage@thnk2wn
```

Start a new Codex task after installation so the skill and tools are loaded. The repository is currently private, so the installing user needs GitHub read access and working SSH credentials.

Automatic cards require a one-time trust review for the bundled `UserPromptSubmit` hook. Codex Desktop does not currently surface that pending review, so complete it in Terminal:

1. Run `codex`.
2. Choose **Review hooks** in the startup warning, or enter `/hooks` after Codex opens.
3. Open **UserPromptSubmit** and verify the source is **Plugin - codex-usage@...** and the command is `python3 "$PLUGIN_ROOT/hooks/auto_usage_card.py"`.
4. Press `t` to trust that hook, then exit the CLI and start a new desktop task.

Trust is saved globally for that exact hook definition. If a later plugin update changes the hook, Codex will require another review.

To pick up a newer version later:

```bash
codex plugin marketplace upgrade thnk2wn
codex plugin add codex-usage@thnk2wn
```

## Share privately

Without workspace-admin access, private sharing is per user rather than an organization-wide deployment. Grant each teammate read access to this repository and send them the two installation commands above, or have them use the GitHub release bundle below. Distribution and access stay under GitHub, with no public listing or external approval workflow.

Each teammate must install the plugin themselves. Their workspace must also permit personal or local plugins. If workspace policy disables those installations, there is no supported admin-free bypass; a workspace admin must allow the plugin or import it for the workspace.

## Install across a private workspace

A ChatGPT workspace admin is required to distribute this plugin automatically across a private workspace. The admin can import it directly from the private GitHub repository:

1. Make sure the GitHub account used for the import can read this repository and has any required organization approval.
2. In ChatGPT, open **Admin → Plugins**, then choose **Add → Import marketplace**.
3. Use `https://github.com/thnk2wn/codex-usage` as the source. Leave **Path** empty. Use `main` for automatic updates, or a release tag such as `v0.2.0` for a pinned rollout.
4. Review the imported plugin and set its installation policy to **Installed** for the roles that should receive it. Use **Available** instead if members should opt in.
5. Use **Sync now** when you want to pull an update immediately; otherwise GitHub marketplaces sync daily.

The repository includes both native Codex and Claude-compatible marketplace manifests. Because Codex Usage includes a local MCP server, workspace imports are marked desktop-only; the compact text fallback remains available when a client does not render the inline app.

See [OpenAI's plugin management guide](https://learn.chatgpt.com/docs/enterprise/plugin-management) for current workspace import and access controls.

## Install from a GitHub release

Each release includes a self-contained `codex-usage-vX.Y.Z.zip` marketplace bundle. Download it from [GitHub Releases](https://github.com/thnk2wn/codex-usage/releases), extract it, and run:

```bash
bash ./codex-usage-vX.Y.Z/install.sh
```

The release bundle installs entirely from the extracted files. Keep that directory if you want Codex to retain the local marketplace source. Since this repository is private, downloaders still need GitHub read access; a workspace-admin import is more convenient for a broad managed rollout.

## Public marketplace

This build is intentionally not submitted to OpenAI's universal Plugins Directory. Public submission requires a verified publisher, production listing and policy materials, reproducible test cases, automated scanning, and OpenAI review. MCP-backed submissions normally also require a stable public HTTPS server.

Codex Usage instead runs its MCP server locally because its core purpose is reading local Codex metadata without uploading it. Publishing it universally would therefore require either explicit OpenAI support for a local MCP design or a privacy-sensitive architectural change. The private Git marketplace above keeps the current local-only behavior intact.

See [OpenAI's plugin submission documentation](https://developers.openai.com/plugins/deploy/submission) for the current public review requirements.

## UI surfaces

- Automatic cards are rate-limited to one per task per minute by default. A qualifying user prompt creates a **new** compact snapshot near that turn; it refreshes in place for up to two minutes while work continues, then freezes in conversation history. Older cards are never rewritten.
- The minimized header includes the snapshot time. Clicking it expands clearly defined token metrics, a limit-window pace projection, a subdued compaction notice, the top five tasks, and a global automatic-card frequency control (every turn, 30 seconds, 1/5/15 minutes, or off). Open card instances synchronize that preference when the client permits it, and every historical card rechecks it when expanded.
- `show_usage_card` can also render a card on demand. `refresh_usage_card` is used only by an already-rendered card, so live updates do not add more conversation items.
- Mobile Remote falls back to a single-line status result when it does not render the MCP App iframe; say `usage details` for a text breakdown.
- `open_usage_dashboard` starts the optional private localhost dashboard for a larger cross-task view.
- `current_conversation_usage` returns a concise snapshot for the active conversation when a panel is not needed.
- `usage_dashboard` returns structured cross-task data for the current limit window, today, or rolling 7/30-day ranges.

## Data and privacy

The MCP server reads `~/.codex/state_5.sqlite` and the rollout files already referenced by that database without modifying them. It binds its optional dashboard only to `127.0.0.1`, uses no external network access, and stores no copy of task content. Task names are displayed locally in the card and dashboard. The only plugin writes are the selected automatic-card preference and per-task throttle timestamps under `~/.codex/codex-usage/`.

Cards are still MCP tool-result UI: the plugin's `UserPromptSubmit` hook asks Codex to invoke the card at the start of a qualifying user turn. It cannot push unsolicited UI into an idle conversation. The hook stores only its per-task last-card time, and preferences live in `~/.codex/codex-usage/`.

Plugin hooks must be reviewed and trusted before Codex will run them. Use the CLI `/hooks` flow described under **Install**; the current desktop app silently skips an unreviewed hook rather than showing the review UI. Until the hook is trusted, cards remain available on demand but will not appear automatically.

The numbers are raw local token counters, not a server-authoritative quota ledger. The aggregate usage percentage is the latest coarse snapshot recorded in local session metadata.

## Development

```bash
/usr/bin/python3 scripts/server.py --self-test
```

After changing a locally installed copy, update its cachebuster and reinstall it from the personal marketplace before testing in a new Codex task.

## License

MIT
