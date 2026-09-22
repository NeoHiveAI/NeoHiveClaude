#!/usr/bin/env bash
# NeoHive Context Injection: UserPromptSubmit hook (plugin version)
# Passes the user's prompt to NeoHive memory_recall via stateless MCP JSON-RPC.
# Works for any project with a NeoHive MCP server configured.
#
# MCP URL discovery (in order):
#   1. Project .mcp.json → mcpServers.<*neohive*>.url
#   2. ~/.claude.json → mcpServers.<*neohive*>.url (global config)
#
# Auth: reads NEOHIVE_TOKEN env var for Bearer auth (Auth0/PAT).
# Set NEOHIVE_HOOK_DISABLED=1 to skip entirely.
set -uo pipefail

if [ "${NEOHIVE_HOOK_DISABLED:-}" = "1" ]; then
  cat > /dev/null  # drain stdin (hook protocol) before exiting
  exit 0
fi

# Read hook input from stdin
INPUT=$(cat)

# Extract user message: data goes through stdin, never interpolated into source
USER_MSG=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except:
    d = {}
msg = d.get('user_message') or d.get('message') or d.get('prompt') or ''
print(msg[:400])
" 2>/dev/null) || true

# Session id: used to stamp this recall into the per-session state file (HIVE-237)
SESSION_ID=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except:
    d = {}
print(d.get('session_id') or '')
" 2>/dev/null) || true

# Skip if no message, too short, or slash command
if [ -z "$USER_MSG" ] || [ ${#USER_MSG} -lt 10 ]; then
  exit 0
fi
if [[ "$USER_MSG" == /* ]]; then
  exit 0
fi

# ── Discover NeoHive MCP URL ────────────────────────────────────────
# Search project .mcp.json first, then global ~/.claude.json

MCP_URL=""

discover_url() {
  python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    # Check mcpServers for any key containing 'neohive' or 'hivemind' (legacy)
    servers = d.get('mcpServers', {})
    for key, val in servers.items():
        k = key.lower()
        if ('neohive' in k or 'hivemind' in k) and isinstance(val, dict):
            url = val.get('url', '')
            if url:
                print(url)
                break
except:
    pass
" 2>/dev/null
}

# Try project-level .mcp.json (cwd = project root when hook fires)
if [ -f ".mcp.json" ]; then
  MCP_URL=$(discover_url < .mcp.json) || true
fi

# Fallback: try global Claude config
if [ -z "$MCP_URL" ] && [ -f "$HOME/.claude.json" ]; then
  MCP_URL=$(discover_url < "$HOME/.claude.json") || true
fi

if [ -z "$MCP_URL" ]; then
  exit 0
fi

# ── Build JSON-RPC payload ──────────────────────────────────────────

PAYLOAD=$(python3 -c "
import sys, json
query = sys.stdin.read().strip()
payload = {
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'tools/call',
    'params': {
        'name': 'memory_recall',
        'arguments': {'query': query, 'limit': 5}
    }
}
print(json.dumps(payload))
" <<< "$USER_MSG" 2>/dev/null) || exit 0

# ── Call NeoHive ────────────────────────────────────────────────────

# Identify this caller in the User-Agent. The server records the request
# User-Agent into query_log.client (mcp-handler.ts) as the only per-request
# interface identifier available on the stateless MCP transport. Without an
# explicit UA, curl sends a bare "curl/<ver>", which (a) misattributes this
# hook-fired auto-context recall to a generic "curl" client indistinguishable
# from any other curl caller, and (b) splits one Claude Code session's rows
# across "curl" (these auto-context recalls) and "claude-code/<ver>" (the
# model's own MCP calls). A self-identifying UA makes the client column
# attributable and lets readers tell hook-fired (auto-context) recalls apart
# from model-initiated ones server-side.
CURL_ARGS=(-s --connect-timeout 3 --max-time 8 -X POST "$MCP_URL"
           -A "neohive-context-hook"
           -H "Content-Type: application/json"
           -H "Accept: application/json, text/event-stream")
if [ -n "${NEOHIVE_TOKEN:-}" ]; then
  CURL_ARGS+=(-H "Authorization: Bearer $NEOHIVE_TOKEN")
fi

RESPONSE=$(curl "${CURL_ARGS[@]}" -d "$PAYLOAD" 2>/dev/null) || exit 0

# ── Stamp this recall into the per-session state file (HIVE-237) ─────
# This auto-context recall is fired by the hook, not by the model, so the
# PostToolUse stamp hook never sees it; stamp it here. Best-effort.
STATE_HELPER="${CLAUDE_PLUGIN_ROOT:-.}/hooks/session-state.py"
if [ -n "$SESSION_ID" ] && [ -f "$STATE_HELPER" ]; then
  printf '%s' "$RESPONSE" | python3 "$STATE_HELPER" \
    stamp-recall-sse --session "$SESSION_ID" --query "$USER_MSG" 2>/dev/null || true
fi

# ── Parse SSE response ──────────────────────────────────────────────

echo "$RESPONSE" | python3 -c "
import sys, json
try:
    raw = sys.stdin.read().strip()
    payload = None
    for line in raw.splitlines():
        if line.startswith('data: '):
            payload = line[6:]
            break
    if payload is None:
        payload = raw
    d = json.loads(payload)
    result = d.get('result', {})
    contents = result.get('content', [])
    texts = [c['text'] for c in contents if c.get('type') == 'text']
    combined = '\n'.join(texts)
    if combined and 'No relevant memories found' not in combined:
        if len(combined) > 4000:
            combined = combined[:4000] + '\n\n... (truncated)'
        print('NeoHive auto-context (from project memory):')
        print(combined)
except:
    pass
" 2>/dev/null || true
