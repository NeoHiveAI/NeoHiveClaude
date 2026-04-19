---
name: generate-post-submit-hook
description: Generate a tailored UserPromptSubmit hook that uses a small model (Haiku by default) to intelligently query NeoHive on every user prompt. The default plugin hook just passes the raw prompt to memory_recall; this generator produces a smarter version that rewrites queries, decides when lookup is worthwhile, and formats results. Use when the user asks "can NeoHive use a smaller model to look things up", "give me a smart hook", "generate a post-submit hook", or during `/neohive:getting-started` Phase 4.
user-invocable: true
allowed-tools: Bash, Read, Write, Grep, Glob, AskUserQuestion
---

# Generate a Smart Post-Submit Hook

You are helping the user install a customized `UserPromptSubmit` hook that intercepts their prompt, uses a small model to formulate a good NeoHive query, calls `memory_recall`, and injects relevant results back into Claude's context.

This is a **dynamic setup** — every user has a different hive layout, shell, API key location, and tolerance for latency. You walk them through each choice with a strong recommended default, then write the script.

## Phase 0 — Check prerequisites

Before asking anything, verify:

```bash
command -v claude >/dev/null && echo "claude-cli: OK" || echo "claude-cli: MISSING"
command -v curl   >/dev/null && echo "curl: OK"       || echo "curl: MISSING"
command -v python3>/dev/null && echo "python3: OK"    || echo "python3: MISSING"
[ -n "${ANTHROPIC_API_KEY:-}" ] && echo "ANTHROPIC_API_KEY: set" || echo "ANTHROPIC_API_KEY: not set (required for headless claude)"
```

If `claude-cli` or `python3` is missing, stop and tell the user to install them. If the API key is missing, tell them to export it first and point at https://console.anthropic.com/.

## Phase 1 — Gather configuration

Ask these in sequence, one per `AskUserQuestion` call (never combine):

### 1. Which hive to target

Call `list_hives`. Ask:

- **Header:** "Target hive"
- **Question:** "Which hive should the hook search on every prompt?"
- Options: populate from `list_hives`, first option `(Recommended) All hives (cross-hive RRF)` — this calls `memory_recall` without a `hive` param.

### 2. Which model drives the query rewriter

- **Header:** "Rewriter model"
- **Question:** "Which model should rewrite your prompt into a NeoHive query and filter results?"
- Options:
  - `claude-haiku-4-5 (Recommended) — fast + cheap`
  - `claude-sonnet-4-6 — more accurate, slower, ~10x cost`
  - `claude-opus-4-7 — overkill, only for very noisy hives`

### 3. Trigger policy

- **Header:** "When to run"
- **Question:** "When should the hook fire?"
- Options:
  - `(Recommended) Every prompt longer than 10 chars — skips short clarifications`
  - `Only when prompt contains a keyword I pick`
  - `Every prompt — no filtering`
  - `Manual only — I'll trigger it via an env flag`

If "keyword": ask for the keyword(s) via a follow-up `AskUserQuestion` with `Other`.

### 4. Install location

- **Header:** "Install location"
- **Question:** "Where should the hook live?"
- Options:
  - `(Recommended) ~/.claude/hooks/neohive-smart-recall.sh — personal, all projects`
  - `./.claude/hooks/neohive-smart-recall.sh — this project only`
  - `Just show me the script — I'll place it myself`

### 5. Disable-flag name

- **Header:** "Disable flag"
- **Question:** "What env var should disable the hook when set to 1?"
- Options:
  - `(Recommended) NEOHIVE_SMART_DISABLED`
  - `NEOHIVE_HOOK_DISABLED (same flag as the default dumb hook — one switch turns both off)`
  - `Custom — I'll type it`

## Phase 2 — Preview the generated script

Build the script from the template at `${CLAUDE_PLUGIN_ROOT}/skills/generate-post-submit-hook/template.sh` — substitute the chosen values. Show the final script to the user in a fenced code block. Summarize changes at the top:

```
Generated hook with:
  • Hive:          <hive-or-all>
  • Model:         <model>
  • Trigger:       <policy>
  • Install path:  <path>
  • Disable flag:  <env-var>
```

Ask one last `AskUserQuestion`:

- **Header:** "Install"
- **Question:** "Install this hook now?"
- Options:
  - `(Recommended) Yes, write it and register it in settings.json`
  - `Yes, write it — I'll register it myself`
  - `No — I want to tweak the script first`

If "tweak": ask what they want to change, regenerate, re-preview.
If "no" at any point: stop with "Nothing written."

## Phase 3 — Write the script

Create parent directories if needed. Write the script to the chosen location with mode `0755`. Show:

```
Wrote <path> (N bytes, mode 755).
```

## Phase 4 — Register in settings.json (if user opted in)

Edit `~/.claude/settings.json` (personal) or `./.claude/settings.json` (project) to add the hook under `hooks.UserPromptSubmit`. Preserve existing entries. If the file has an existing NeoHive `UserPromptSubmit` entry from the plugin itself, **do not remove it** — the two can coexist; warn the user that both will run.

Use `python3 -c` with `json` to do the edit — never hand-edit JSON via sed. Pattern:

```bash
python3 <<PY
import json, pathlib, os
p = pathlib.Path(os.path.expanduser("<settings-path>"))
data = json.loads(p.read_text()) if p.exists() else {}
data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
entry = {
    "matcher": "",
    "hooks": [{"type": "command", "command": "<hook-path>", "timeout": 15000}]
}
if entry not in data["hooks"]["UserPromptSubmit"]:
    data["hooks"]["UserPromptSubmit"].append(entry)
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(data, indent=2))
print(f"Registered: {p}")
PY
```

## Phase 5 — Verification

Tell the user:

> Restart Claude (or run `/reload-plugins`) for the hook to take effect.
>
> Test it: start a new session and ask about something you know is in your hive. You should see a block starting with "NeoHive smart context:" before Claude's reply.
>
> Disable temporarily: `export <DISABLE_FLAG>=1` in your shell.
> Disable permanently: remove the entry from your settings.json, or delete the script.

## Important rules

- **Never overwrite an existing hook at the target path without confirmation.** If the file exists, show its contents and ask whether to replace.
- **Never put the API key in the generated script.** The script reads `$ANTHROPIC_API_KEY` at runtime.
- **Never hardcode the hive UUID in the script.** It discovers the MCP URL the same way the default hook does (via `.mcp.json` / `~/.claude.json`).
- **Always set a `--max-time` on every `curl` and `claude -p` call.** A slow hook blocks every prompt.
- **Gracefully exit 0 on any failure.** A broken hook must never block the user's prompt from reaching Claude.
