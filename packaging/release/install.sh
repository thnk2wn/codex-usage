#!/usr/bin/env bash

set -euo pipefail

if ! command -v codex >/dev/null 2>&1; then
  echo "Codex CLI is required but was not found on PATH." >&2
  exit 1
fi

bundle_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

codex plugin marketplace add "$bundle_root"
codex plugin add codex-usage@codex-usage-release

echo
echo "Codex Usage is installed."
echo ""
echo "To enable automatic cards, run 'codex' and review the bundled hook:"
echo "  1. Choose 'Review hooks' at startup, or enter /hooks."
echo "  2. Open UserPromptSubmit and verify it is from codex-usage."
echo "  3. Press t to trust it, exit the CLI, and start a new desktop task."
echo ""
echo "Codex Desktop currently does not show this pending hook review itself."
