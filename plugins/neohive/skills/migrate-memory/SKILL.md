---
name: migrate-memory
description: Scan local project memory files (CLAUDE.md, AGENTS.md, GEMINI.md, .claude/rules) and migrate the PROJECT-SPECIFIC entries into NeoHive so the whole team can share them. User-preference entries are filtered out. Always read-only until the user explicitly confirms. Use when the user says "migrate my memory", "move my CLAUDE.md into NeoHive", or during first-time setup via `/neohive:getting-started`.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

# Migrate Local Memory Into NeoHive

You are migrating a user's existing project knowledge (files they've already written, conventions their CLAUDE.md records, rules in `.claude/rules`) into NeoHive so it becomes shared team memory instead of per-machine memory.

**Two non-negotiable rules for this skill:**

1. **Read-only until confirmation.** Scan, classify, present a preview. Do NOT call `memory_store` until the user explicitly says go.
2. **Project-specific only.** User-preference content ("I prefer tabs", "my editor is neovim") must never land in a shared hive. If classification is ambiguous, default to excluding.

## Arguments

If `$ARGUMENTS` contains `review=each`, pause between each candidate for user approval. Otherwise batch confirm at the end.

## Phase 1 — Discover local memory sources

Scan these locations relative to the current working directory. Report what you find, with byte counts:

```bash
# Project-scoped (CANDIDATES for migration)
for f in ./CLAUDE.md ./AGENTS.md ./GEMINI.md; do
  [ -f "$f" ] && echo "$f ($(wc -c < "$f") bytes)"
done
find ./.claude/rules -type f -name '*.md' 2>/dev/null
find ./docs -maxdepth 2 -type f -name 'CONVENTIONS*.md' -o -name 'CONTRIBUTING.md' 2>/dev/null | head -20

# User-scoped (SCANNED for context only; never migrated)
[ -f "$HOME/.claude/CLAUDE.md" ] && echo "user: ~/.claude/CLAUDE.md (for reference only, will NOT migrate)"
```

Report findings as a compact block:

```
Project-scoped sources found:
  - ./CLAUDE.md (4.2 KB)
  - ./.claude/rules/testing.md (1.1 KB)
User-scoped (will be skipped):
  - ~/.claude/CLAUDE.md (8.7 KB)
```

If nothing project-scoped is found, stop and say so: "No project-scoped memory files found in this repo. Nothing to migrate. If you've stored knowledge elsewhere, point me at the file(s)."

## Phase 2 — Parse into candidate memories

For each project-scoped file, break the content into **atomic candidate memories**. A candidate is a single self-contained directive, convention, decision, or insight that would make sense read in isolation 6 months from now.

Heuristics:
- One markdown bullet → one candidate
- One paragraph containing a rule ("Always use X", "Never do Y") → one candidate
- A section like "## Testing" containing multiple rules → one candidate per rule, not the whole section
- Code examples: keep the surrounding prose + example together as one candidate

Skip content that is:
- Pure metadata (version headers, tables of contents)
- Installation/setup instructions (these belong in README, not memory)
- Transient state (TODO lists, "currently broken" sections)
- Content that duplicates what's obviously already in NeoHive (you won't know this yet — deduplication happens in Phase 4)

## Phase 3 — Classify each candidate

For each candidate, assign:

**Scope:** `project` | `user` | `ambiguous`
- `project`: references this specific codebase, team practices, domain-specific rules. Examples: "We use sqlite-vec for embeddings", "Always run tests through `.venv/bin/python3`", "The `starlang` rule format requires X".
- `user`: references personal preferences, editor settings, generic "I prefer X" statements. Examples: "I prefer tabs over spaces", "Use fish shell", "My name is X".
- `ambiguous`: could be either. Examples: "Never use `--no-verify`" (could be personal discipline OR a team rule).

**Type:** one of `directive`, `convention`, `decision`, `insight`, `error_pattern`, `syntax_rule`, `semantic_rule`, `example_pattern`, `idiom` (same taxonomy as `revise-vector-memory`).

**Importance:** 1–10. Rules/musts → 8–9. Conventions → 6–7. Insights/gotchas → 5–7.

**Tags:** 3–6 domain-specific terms someone would search for.

## Phase 4 — Pick a target hive

Call `list_hives`. Report the list with descriptions. Then use `AskUserQuestion`:

- **Header:** "Target hive"
- **Question:** "Which hive should these memories land in?"
- Options: dynamically populated from `list_hives`, with `(Recommended)` suffix on the hive whose description best matches the project (e.g. a hive with "securisource" in its description for a securisource repo)

If only one hive exists, skip the question and announce "Using the only available hive: <name>".

## Phase 5 — Preview and confirm

Build a preview table of **only the `project`-scoped candidates**. Show count summary at top. Use this exact format:

```
Ready to migrate N project-scoped memories to hive `<hive-name>`.
(Skipping M user-scoped + K ambiguous candidates — see below.)

┌─────┬──────────────┬───────┬────────────────────────────────────────────────────┐
│ #   │ type         │ imp   │ content (first 80 chars)                           │
├─────┼──────────────┼───────┼────────────────────────────────────────────────────┤
│ 1   │ directive    │  9    │ Always run python scripts through .venv/bin/py... │
│ 2   │ convention   │  7    │ Prefer dedicated tools (Grep, Read) over Bash ... │
│ ... │ ...          │ ...   │ ...                                                │
└─────┴──────────────┴───────┴────────────────────────────────────────────────────┘

Skipped as user-preference:
  - "I prefer fish shell" (from ~/.claude/CLAUDE.md)
Skipped as ambiguous (migrate manually if you want these):
  - "Never use --no-verify" (could be personal or team rule)
```

Then ask via `AskUserQuestion`:

- **Header:** "Confirm migration"
- **Question:** "Migrate these N memories to `<hive>`?"
- Options: `Yes, migrate all (Recommended)`, `Yes, but let me exclude some first`, `No, abort migration`, `Re-classify the ambiguous ones`

If "exclude some first": ask the user to name numbers to drop, then re-preview.
If "re-classify": walk through ambiguous ones one at a time.
If "abort": print "Migration aborted. No memories stored." and stop.

If `review=each` was passed in arguments, override the above: walk through candidates one by one with yes/no prompts.

## Phase 6 — Deduplicate and store

For each approved candidate:

1. Call `memory_recall` with a query derived from the candidate content. Include `limit=3`.
2. Read the results:
   - **Strong match (score > 0.85 and semantically identical):** skip, report "already known".
   - **Weak/partial match:** store anyway — adds a new semantic angle.
   - **No match:** store.
3. Call `memory_store` with:
   - `hive`: the chosen hive
   - `content`: the candidate content (full, not truncated)
   - `type`, `tags`, `importance` from Phase 3
   - `metadata`: `{"source": "migrate-memory", "origin_file": "<path>", "origin_line": <line>}`

Do writes sequentially, not in parallel — rate limiting matters. If any write fails, report the error and ask whether to continue with remaining candidates or abort.

## Phase 7 — Summary

Print this exact block:

```
Migration complete.
  Candidates found:     N
  Migrated:             X (IDs: ...)
  Already in NeoHive:   Y (skipped via dedup)
  User-scoped:          Z (skipped)
  Ambiguous:            W (skipped — migrate manually if needed)

Next: update your CLAUDE.md to reference NeoHive instead of duplicating these rules. Run /neohive:revise-vector-memory at the end of each session to keep the hive fresh.
```

## Important rules

- **NEVER write to a hive before Phase 5 confirmation.** This is the difference between a safe skill and a destructive one.
- **NEVER migrate `~/.claude/CLAUDE.md` content.** That file is per-user by definition.
- **NEVER guess at classification.** When ambiguous, mark ambiguous and surface it.
- **ALWAYS preserve the full content.** Do not summarize candidates before storing — summarization loses information.
- **If `list_hives` fails, stop immediately.** Tell the user the MCP server isn't reachable and point them at `/neohive:getting-started` Phase 1.
