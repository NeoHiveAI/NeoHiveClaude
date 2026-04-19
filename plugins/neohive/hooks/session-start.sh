#!/usr/bin/env bash
# SessionStart hook — manages ~/.claude/rules/neohive.md
#
# On each session start:
# 1. Checks if ~/.claude/rules/neohive.md exists
# 2. If missing or version is stale → installs/updates from plugin template
# 3. Emits a minimal systemMessage reminder
#
# The rules file provides persistent NeoHive tool usage instructions
# that survive context compression (unlike systemMessage which is ephemeral).

set -euo pipefail

# Read session input (required by hook protocol)
cat > /dev/null

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
TEMPLATE="${PLUGIN_ROOT}/rules/neohive.md"
TARGET_DIR="${HOME}/.claude/rules"
TARGET="${TARGET_DIR}/neohive.md"

# Extract version from YAML frontmatter: version: "X.Y.Z"
extract_version() {
  local file="$1"
  if [ -f "$file" ]; then
    sed -n 's/^version: *"\([^"]*\)".*/\1/p' "$file" | head -1
  fi
}

# Ensure template exists
if [ ! -f "$TEMPLATE" ]; then
  # Plugin template missing — emit fallback systemMessage
  cat <<'JSONEOF'
{"systemMessage":"NeoHive cognitive memory is available. Call memory_context with your task description before starting work."}
JSONEOF
  exit 0
fi

TEMPLATE_VERSION=$(extract_version "$TEMPLATE")
INSTALLED_VERSION=$(extract_version "$TARGET")

# Install or update if versions differ
if [ "$TEMPLATE_VERSION" != "$INSTALLED_VERSION" ]; then
  mkdir -p "$TARGET_DIR"
  cp "$TEMPLATE" "$TARGET"

  if [ -z "$INSTALLED_VERSION" ]; then
    # First install
    cat <<JSONEOF
{"systemMessage":"NeoHive rules installed at ~/.claude/rules/neohive.md (v${TEMPLATE_VERSION}). Call memory_context with your task description before starting work."}
JSONEOF
  else
    # Updated
    cat <<JSONEOF
{"systemMessage":"NeoHive rules updated to v${TEMPLATE_VERSION} (was v${INSTALLED_VERSION}). Call memory_context with your task description before starting work."}
JSONEOF
  fi
else
  # Already up to date — minimal reminder
  cat <<'JSONEOF'
{"systemMessage":"NeoHive cognitive memory is available. Call memory_context with your task description before starting work."}
JSONEOF
fi

exit 0
