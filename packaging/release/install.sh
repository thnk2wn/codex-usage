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
echo "Codex Usage is installed. Start a new Codex task to use it."
