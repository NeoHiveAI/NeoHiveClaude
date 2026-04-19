---
name: getting-started
description: First-run setup for NeoHive. Walks a new user through verifying the MCP server, setting up auth, migrating existing project memory, and enabling optional helpers. Invoke this once per machine after installing the neohive plugin. Use when the user says "set up NeoHive", "get me started with NeoHive", "first time using NeoHive", or when `list_hives` has never been called in this repo.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion, Skill
---

# Getting Started with NeoHive

You are onboarding a user who has just installed the NeoHive plugin. Your job is to get them from zero to a fully working setup — MCP reachable, memory migrated, helpers configured — without ever leaving them staring at a blank screen.

**Golden rule for this skill: never act silently.** Narrate every step. Every decision has a recommended default. Every write is gated by an explicit confirmation.

## Phase 0 — Tell the user what's about to happen

Open with this exact script (do not paraphrase):

> I'll walk you through setting up NeoHive on this machine. This takes 3–5 minutes and covers:
>   1. Confirming your NeoHive server is reachable
>   2. (Optional) Setting up your auth token
>   3. Migrating existing project knowledge into NeoHive
>   4. (Optional) Turning on the smart-recall hook
>
> You can stop at any point by saying "stop" or answering "skip" to a step.

Wait for acknowledgement (any affirmative reply, or just continue if they say nothing).

## Phase 1 — Verify MCP reachability

Call `list_hives` immediately. Interpret the outcome:

| Outcome | What to tell the user |
|---|---|
| Returns hives | "Connected. I can see N hives: X, Y, Z." Proceed to Phase 2. |
| Empty list | "Server is reachable but reports no hives. Confirm with your admin — without at least one hive, NeoHive has nowhere to store memories." Pause for user input. |
| Tool unavailable / error | "I can't reach the NeoHive MCP server." Run the diagnostics below. |

### Diagnostics if unreachable

Run these checks and report results in a compact block:

```bash
# 1. Is .mcp.json present in the plugin install?
ls "$CLAUDE_PLUGIN_ROOT/.mcp.json" 2>&1 || echo "missing"
# 2. Is NEOHIVE_TOKEN set?
[ -n "${NEOHIVE_TOKEN:-}" ] && echo "token set" || echo "token not set"
# 3. Can we reach the server?
grep -oE 'https?://[^"]+' "$CLAUDE_PLUGIN_ROOT/.mcp.json" | head -1 | xargs -I{} curl -sS -o /dev/null -w "HTTP %{http_code}\n" --max-time 5 "{}" 2>&1 || true
```

Then use `AskUserQuestion` to offer: "Fix token now", "I'll fix it later and restart Claude", "Skip MCP setup for now". If they skip, jump to Phase 5 with a warning that memory features won't work.

## Phase 2 — Auth token (only if needed)

If `list_hives` succeeded, skip this phase. Otherwise ask:

- **Header:** "Auth token"
- **Question:** "Does your NeoHive server require a bearer token?"
- Options: `Yes — I have one (Recommended)`, `Yes — I need to get one from my admin`, `No — it's open`, `I'm not sure`

For "Yes — I have one", show:

> Export it before launching Claude:
> ```bash
> export NEOHIVE_TOKEN="your-token-here"
> ```
> Add that line to your shell rc (`~/.bashrc`, `~/.zshrc`, or `~/.config/fish/config.fish`) so it persists. Then restart Claude and rerun `/neohive:getting-started`.

For the other answers, provide the matching guidance verbatim — don't improvise.

## Phase 3 — Migrate existing project memory

Ask (one `AskUserQuestion`):

- **Header:** "Migrate memory"
- **Question:** "Want me to scan this project for existing knowledge (CLAUDE.md, AGENTS.md, .claude/rules) and migrate the project-specific parts into NeoHive?"
- Options: `Yes (Recommended)`, `Yes, but let me review each memory first`, `Skip — nothing worth migrating`, `Skip — I'll do this manually later`

If Yes, invoke the migrate skill via the Skill tool:

```
Skill(skill="neohive:migrate-memory")
```

Wait for it to complete. Report: "Migration done — N memories stored." Then continue.

If "Yes, but review each": invoke `neohive:migrate-memory` with argument `review=each` so it pauses per candidate.

## Phase 4 — Smart-recall hook (optional, power users)

Ask:

- **Header:** "Smart recall"
- **Question:** "The default hook passes your prompt verbatim to NeoHive. A smarter version uses a small model to rewrite the query first — usually better results, but costs a few tokens per prompt. Set it up?"
- Options: `Not now (Recommended)`, `Yes, set it up`, `Tell me more first`

If "Yes": invoke `Skill(skill="neohive:generate-post-submit-hook")`.
If "Tell me more": explain in 3–4 sentences (what it adds, what it costs, how to disable) then re-ask.

## Phase 5 — Final summary

Print a checklist of what's been set up and what's left. Use ✓ / ○ prefixes:

```
✓ MCP server reachable (N hives: ...)
✓ Auth token configured
✓ N project memories migrated
○ Smart-recall hook (skipped — rerun /neohive:generate-post-submit-hook anytime)
```

Then this exact closing block:

> **You're set. Three things to remember:**
>   1. Start every new session with `/neohive:start <what you're working on>` to pre-load relevant memory.
>   2. End sessions with `/neohive:revise-vector-memory` so new insights get captured.
>   3. When docs feel stale, try `/neohive:generate-docs`.
>
> Run `/neohive:getting-started` again anytime to revisit these steps.

## Important rules

- **Never call `memory_store` directly from this skill.** Delegate to `migrate-memory` or `revise-vector-memory`.
- **Never edit the user's shell rc files yourself.** Show the command, let them paste.
- **If the user says "stop" or "skip" at any phase, stop immediately** and print the Phase 5 summary with what's done so far.
- **If any sub-skill fails, surface the error plainly** and offer to skip that phase rather than retrying silently.
