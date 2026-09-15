# Install Codex Usage

This archive is a self-contained local Codex marketplace. It does not need public marketplace publication or an internet connection after download.

From Terminal, run:

```bash
bash ./install.sh
```

Then approve the automatic-card hook once in Codex CLI. Codex Desktop does not currently display this pending review:

1. Run `codex` in Terminal.
2. Choose **Review hooks** at startup, or enter `/hooks` after Codex opens.
3. Open **UserPromptSubmit** and verify the source is **Plugin - codex-usage@...** and the command is `python3 "$PLUGIN_ROOT/hooks/auto_usage_card.py"`.
4. Press `t` to trust that hook, exit the CLI, and start a new desktop task.

Automatic cards remain off until this exact hook definition is trusted; on-demand cards continue to work. A future plugin update that changes the hook will require another review.

The installer registers this extracted directory as the `codex-usage-release` marketplace and installs `codex-usage` from it. Keep the extracted directory if you want Codex to continue recognizing the marketplace source.
