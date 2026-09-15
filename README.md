# Codex Usage

A local-first Codex plugin that attributes raw processed tokens to conversations, subagents, automations, and internal activity. It reads local Codex metadata and never uploads it. It supports personal installs, workspace distribution, and self-contained GitHub release bundles without public marketplace publication.

Collapsed warning state:

![Codex Usage collapsed critical warning](assets/codex-usage-card-collapsed.png)

Expanded details:

![Codex Usage expanded critical warning](assets/codex-usage-card.png)

## Install

This repository is also a small Git marketplace, so installation does not require publication or OpenAI marketplace review. It is public, so anyone can install it directly.

```bash
codex plugin marketplace add git@github.com:thnk2wn/codex-usage.git --ref main
codex plugin add codex-usage@thnk2wn
```

Start a new Codex task after installation so the skill and tools are loaded. The commands above use SSH, so they need working SSH credentials; swap in the HTTPS URL if you would rather not use SSH.

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

## Share with a team

Without workspace-admin access, sharing is per user rather than an organization-wide deployment. Send teammates the two installation commands above, or have them use the GitHub release bundle below. Distribution stays under GitHub, with no marketplace listing or external approval workflow.

Each teammate must install the plugin themselves. Their workspace must also permit personal or local plugins. If workspace policy disables those installations, there is no supported admin-free bypass; a workspace admin must allow the plugin or import it for the workspace.

## Install across a workspace

A ChatGPT workspace admin is required to distribute this plugin automatically across a workspace. The admin can import it directly from the GitHub repository:

1. Make sure the GitHub account used for the import has any required organization approval.
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

The release bundle installs entirely from the extracted files. Keep that directory if you want Codex to retain the local marketplace source. A workspace-admin import is more convenient for a broad managed rollout.

## Public marketplace

This build is intentionally not submitted to OpenAI's universal Plugins Directory. Public submission requires a verified publisher, production listing and policy materials, reproducible test cases, automated scanning, and OpenAI review. MCP-backed submissions normally also require a stable public HTTPS server.

Codex Usage instead runs its MCP server locally because its core purpose is reading local Codex metadata without uploading it. Publishing it universally would therefore require either explicit OpenAI support for a local MCP design or a privacy-sensitive architectural change. The Git marketplace above keeps the current local-only behavior intact.

See [OpenAI's plugin submission documentation](https://developers.openai.com/plugins/deploy/submission) for the current public review requirements.

## UI surfaces

- Automatic cards are rate-limited to one per task every five minutes by default. A qualifying user prompt creates a **new** compact snapshot near that turn; it refreshes in place for up to two minutes while work continues, then freezes in conversation history. Older cards are never rewritten.
- The minimized header includes the snapshot time and remaining account capacity. It turns amber when 15% or less remains or current pace projects over the limit, and red when 10% or less remains. Clicking it expands clearly defined token metrics, a limit-window pace projection, a subdued compaction notice, the top five tasks, and a global automatic-card frequency control (every turn, 30 seconds, 1/5/15 minutes, or off). Open card instances synchronize that preference when the client permits it, and every historical card rechecks it when expanded.
- `show_usage_card` can also render a card on demand. `refresh_usage_card` is used only by an already-rendered card, so live updates do not add more conversation items.
- Mobile Remote falls back to a single-line status result when it does not render the MCP App iframe; say `usage details` for a text breakdown. That path uses `usage_details`, which returns the same report as model-readable data, because a card's own render payload is delivered to the component only.
- `open_usage_dashboard` starts the optional private localhost dashboard for a larger cross-task view.
- `current_conversation_usage` returns a concise snapshot for the active conversation when a panel is not needed.
- `usage_dashboard` returns structured cross-task data for the current limit window, today, or rolling 7/30-day ranges.

## How automatic cards work

The trusted prompt hook only decides whether a card is due and asks Codex to invoke it; it does not scan usage data itself. The first tool result reads the current task and latest account-limit snapshot, so the compact header can appear quickly with context, task tokens, remaining capacity, warning color, and snapshot time.

Once that header is rendered, the embedded card requests the heavier limit-window scan asynchronously. Expanding immediately may briefly show **Loading cross-task breakdown…** before the top-five task list arrives. That scan is cached for five minutes, while the current-task values can continue refreshing every few seconds for up to two minutes. This background hydration does not hold up the agent after the initial compact result has returned.

The five-minute automatic-card cadence limits how often a new conversation item is added; it is separate from the short-lived refreshes inside an existing card. Change the cadence from any expanded card. The preference is shared globally, while the last-rendered timestamp is tracked per task.

## What the plugin itself costs

Cards are MCP tool results, so they occupy conversation context and are not free. Each automatic card costs roughly 160 tokens: about 96 for the hook instruction and about 65 for the summary line and a small reference. That is down from roughly 410 before the render data was moved out of context.

The card's own render data does not enter the conversation at all. It travels in the tool result's `_meta`, which the host delivers only to the component, so the card draws every metric it shows while the transcript carries just the summary. Measured on a real card, the model-visible result drops from 1,259 bytes to 262, a 79% cut, which is a 61% cut per card once the hook instruction is counted.

The hook instruction is now the larger half of what remains, so it is the next thing to shorten if this needs to go lower.

The cross-task breakdown is fetched separately by the rendered card through `refresh_usage_card`, which updates the card in place without adding a conversation item, so the top-task list never costs context either.

The larger cost is not the card itself but how long it lives. A card stays in conversation history and is re-read on every later turn, so one card early in a 500-turn session is re-read hundreds of times. In one measured week, cards accounted for about 0.65% of raw token usage, and two long sessions produced over 98% of it. Most of those re-reads are cache hits, so the cost against your actual quota is a fraction of the raw number.

After updating a local copy of the plugin, reinstall it before measuring. A stale install keeps returning the older, heavier card.

Practical consequence: **session length matters far more than card frequency.** Lowering the cadence in a short session saves very little. Avoiding automatic cards in very long sessions saves a lot.

To reduce the cost:

- **Zero ongoing cost per task.** Set automatic cards to **off** from any expanded card, then ask for the dashboard and leave the panel open. Opening it returns a tool result like any other tool, so it costs roughly 100 tokens one time. Every refresh after that is served from the browser to the local server every 20 seconds and never enters the model's context, so the ongoing cost really is zero. Note that the dashboard server lives inside the task's local MCP process and stops when that task closes, and it binds a fresh random port each time, so a new task means paying that one-time cost again on a new URL.
- **Lower the cadence.** Moving from every 5 minutes to every 15 minutes cuts card volume roughly threefold. Use this in long sessions especially.
- **Ask on demand.** With automatic cards off, `show_usage_card` still works whenever you want a snapshot, and `current_conversation_usage` returns a much smaller text-only answer.

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
