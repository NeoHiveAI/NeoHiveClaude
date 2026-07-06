#!/usr/bin/env bash
# PostToolUse hook: stamps every model-initiated NeoHive MCP tool call
# (recall, context, store, forget, stats, list_hives) into the per-session
# state file (HIVE-237 / F1).
#
# Why this hook exists: the model calls these tools directly via MCP many times
# per session, and those calls never pass through the UserPromptSubmit
# auto-context hook. PostToolUse is the only place the harness hands us the
# response of a model-initiated MCP call, so without it the state file would
# capture only the one auto-context recall per prompt and miss the rest.
#
# Matcher (hooks.json): mcp__.*__(memory_.*|list_hives) - the server key is
# user-configured, so we match on the tool suffix, not a hardcoded server name.
# The matcher may over-match (e.g. a future memory_* tool); session-state.py is
# the authoritative filter and ignores any unrecognised tool.
#
# Best-effort by contract: never blocks the tool, never errors the session.
# Set NEOHIVE_HOOK_DISABLED=1 to skip.
set -uo pipefail

if [ "${NEOHIVE_HOOK_DISABLED:-}" = "1" ]; then
  cat > /dev/null  # drain stdin (hook protocol) before exiting, like the path below
  exit 0
fi

HELPER="${CLAUDE_PLUGIN_ROOT:-.}/hooks/session-state.py"
if [ ! -f "$HELPER" ]; then
  # No helper present: consume stdin (hook protocol) and exit cleanly.
  cat > /dev/null
  exit 0
fi

cat | python3 "$HELPER" stamp-posttool 2>/dev/null || true
exit 0
