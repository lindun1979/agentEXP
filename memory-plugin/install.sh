#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
CFG_SRC="$SRC_DIR/config"
CFG_DST="$HOME/.openclaw/memory"

mkdir -p "$CFG_DST"
cp -f "$CFG_SRC"/*.json "$CFG_DST"/

echo "✅ Installed config files to: $CFG_DST"
echo "- chinese_rewrite_map.json"
echo "- noise_intent_patterns.json"
echo "- hybrid_search_config.json"
echo
echo "Next:"
echo "1) Ensure qmd is available: command -v qmd"
echo "2) Import adapter in your workflow"
