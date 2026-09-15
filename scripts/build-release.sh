#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(python3 -c 'import json, pathlib; print(json.loads((pathlib.Path("'"$repo_root"'") / ".codex-plugin/plugin.json").read_text())["version"])')"
release_name="codex-usage-v${version}"
output_dir="${1:-${repo_root}/dist}"
output_path="${output_dir}/${release_name}.zip"
staging_root="$(mktemp -d)"

cleanup() {
  rm -rf "$staging_root"
}
trap cleanup EXIT

bundle_root="${staging_root}/${release_name}"
plugin_root="${bundle_root}/plugins/codex-usage"

mkdir -p "$plugin_root" "$output_dir"
cp -R "$repo_root/packaging/release/.agents" "$bundle_root/.agents"
cp "$repo_root/packaging/release/INSTALL.md" "$bundle_root/INSTALL.md"
cp "$repo_root/packaging/release/install.sh" "$bundle_root/install.sh"
cp -R "$repo_root/.codex-plugin" "$plugin_root/.codex-plugin"
cp "$repo_root/.mcp.json" "$plugin_root/.mcp.json"
cp "$repo_root/LICENSE" "$plugin_root/LICENSE"
cp "$repo_root/README.md" "$plugin_root/README.md"
cp -R "$repo_root/assets" "$plugin_root/assets"
cp -R "$repo_root/hooks" "$plugin_root/hooks"
mkdir -p "$plugin_root/scripts"
cp "$repo_root/scripts/server.py" "$plugin_root/scripts/server.py"
cp "$repo_root/scripts/preferences.py" "$plugin_root/scripts/preferences.py"
cp -R "$repo_root/skills" "$plugin_root/skills"
chmod +x "$bundle_root/install.sh" "$plugin_root/hooks/auto_usage_card.py" "$plugin_root/scripts/server.py"

if [[ -e "$output_path" ]]; then
  rm -f "$output_path"
fi

(
  cd "$staging_root"
  zip -qry "$output_path" "$release_name"
)

echo "$output_path"
