#!/usr/bin/env bash
# PreToolUse hook — nudges the model toward mcp__neohive__memory_recall
# when it calls Glob/Grep inside a project that has a NeoHive MCP server
# configured in a project-rooted .mcp.json.
#
# Modes:
#   default          — soft: allow the tool call, inject additionalContext
#   NEOHIVE_PRETOOL_STRICT=1  — hard: deny the tool call
#
# Disable entirely with NEOHIVE_PRETOOL_DISABLED=1.

set -uo pipefail

if [ "${NEOHIVE_PRETOOL_DISABLED:-}" = "1" ]; then
  exit 0
fi

INPUT=$(cat)

# Parse cwd from stdin. If anything fails, allow silently.
CWD=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    print(json.loads(sys.stdin.read()).get('cwd', ''))
except Exception:
    pass
" 2>/dev/null) || exit 0

if [ -z "$CWD" ] || [ ! -d "$CWD" ]; then
  exit 0
fi

# Walk up from cwd looking for a project-rooted .mcp.json that references
# a NeoHive MCP server. Pass the directory via env var (avoids quoting issues).
HIVE_HINT=""
DIR="$CWD"
while [ "$DIR" != "/" ] && [ -n "$DIR" ]; do
  if [ -f "$DIR/.mcp.json" ]; then
    HIVE_HINT=$(MCP_FILE="$DIR/.mcp.json" python3 -c "
import os, json
try:
    with open(os.environ['MCP_FILE']) as f:
        d = json.load(f)
    for key, val in d.get('mcpServers', {}).items():
        if not isinstance(val, dict):
            continue
        k = key.lower()
        url = val.get('url', '') or ''
        if 'neohive' in k or 'hivemind' in k \
           or '/hiveminds/' in url or '/projects/' in url:
            print(url or key)
            break
except Exception:
    pass
" 2>/dev/null) || true
    if [ -n "$HIVE_HINT" ]; then
      break
    fi
  fi
  PARENT=$(dirname "$DIR")
  if [ "$PARENT" = "$DIR" ]; then
    break
  fi
  DIR="$PARENT"
done

# Not in an indexed project — pass through silently.
if [ -z "$HIVE_HINT" ]; then
  exit 0
fi

REMINDER="This directory is indexed by NeoHive. Prefer mcp__neohive__memory_recall (semantic search over embedded source) before falling back to Glob/Grep — it returns the most relevant files in a single call, uses far less context than a tree walk, and covers the same content. For multi-file exploration, spawn the bundled explore-neohive subagent instead of Explore. Use Glob/Grep when you need exact-string matching (e.g. a unique symbol or import path) or for files created in this session that the index doesn't yet cover."

if [ "${NEOHIVE_PRETOOL_STRICT:-}" = "1" ]; then
  REMINDER="$REMINDER" python3 -c "
import os, json
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': os.environ['REMINDER']
    }
}))
"
else
  REMINDER="$REMINDER" python3 -c "
import os, json
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'allow',
        'additionalContext': os.environ['REMINDER']
    }
}))
"
fi

exit 0
