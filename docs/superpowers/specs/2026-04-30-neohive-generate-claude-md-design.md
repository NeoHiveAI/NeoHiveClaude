# Design — `/neohive:generate-claude-md`

**Status:** Draft, post-brainstorm
**Date:** 2026-04-30
**Author:** brainstormed via `superpowers:brainstorming`
**Target repo:** `~/Logilica/NeoHiveClaude` (NeoHive plugin marketplace)

## Summary

Add a new user-invocable skill, `generate-claude-md`, to the `neohive` plugin. The skill auto-generates a project-specific NeoHive cognitive-memory block in the user's `./CLAUDE.md` by surveying the connected NeoHive hives (`list_hives` + `memory_stats` + sampled `memory_recall` probes) and synthesizing a topology table, write-routing rules, and session-start non-negotiables tailored to that user's hive set. The skill is also wired in as a new Phase 3 of the existing `getting-started` skill, between MCP verification and memory migration.

The motivating problem: design partners running the `neohive` plugin show low NeoHive tool-calling rates because their `CLAUDE.md` does not give Claude a concrete, project-specific map of _which_ hive serves _which_ query and _where_ new writes should land. The shipped `rules/neohive.md` covers generic tool-usage rules but cannot encode this per-project topology — by design, those generic rules are loaded once at session start, before any hive-specific information exists. This skill closes that gap.

## Goals

- Generate a project-specific topology block (`<!-- BEGIN neohive-managed v=1 -->` ... `<!-- END neohive-managed v=1 -->`) inside the repo's `./CLAUDE.md` containing: hive topology table, query-phrasing guidance, hive-provenance interpretation guide, project-specific session-start non-negotiables, "what goes where" routing table, and default write-target rationale.
- Ground every column of the topology table in _evidence_ from the user's actual hives (cartography phase) rather than inference from hive names alone.
- Make the skill safely re-runnable: existing marker blocks are replaced; no clobbering of user content outside the markers.
- Integrate with the `getting-started` first-run flow as a new Phase 3, while remaining independently invocable as `/neohive:generate-claude-md`.
- Coexist cleanly with `migrate-memory`: marker-block content is excluded from migration parsing.

## Non-goals

- Generating equivalent blocks for `AGENTS.md` or `GEMINI.md` (deferred to a follow-up).
- Generating a topology block in user-scope `~/.claude/CLAUDE.md` (deferred — cross-project topology is qualitatively different).
- Drift detection at session-start via a hook (deferred — v1 relies on manual re-run).
- Per-row in-place edits without full regeneration (deferred — re-running the whole skill is the v1 update path).
- Modifying `rules/neohive.md` to be richer / Snyk-equivalent (separate change, separate PR).
- Cross-skill optimization between `generate-claude-md` and `generate-post-submit-hook`'s rewrite rules (deferred).

## Architecture

### Skill location

```
~/Logilica/NeoHiveClaude/plugins/neohive/skills/generate-claude-md/SKILL.md
```

### Skill front-matter (planned)

```yaml
---
name: generate-claude-md
description: Generate a project-specific NeoHive topology block in ./CLAUDE.md by surveying connected hives (list_hives + memory_stats + sampled memory_recall probes). Runs as Phase 3 of /neohive:getting-started, and is also user-invocable for re-runs when hives change. Use when the user says "generate my NeoHive CLAUDE.md", "regenerate the topology", "re-survey my hives".
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion
---
```

Notes on `allowed-tools`:

- NeoHive MCP tools (`list_hives`, `memory_stats`, `memory_recall`) are available globally to the session and are NOT declared in `allowed-tools`.
- The `Skill` tool is intentionally NOT listed — this skill does not invoke any sub-skill. Conversely, `getting-started` (the parent) MUST list `Skill` so it can invoke `generate-claude-md`; that's already true today.

### Three internal stages

The skill runs as three stages internally. To avoid collision with `getting-started`'s own "Phase N" numbering, this spec calls them **Stage A**, **Stage B**, **Stage C**:

- **Stage A — Cartography** — read-only data-gathering against the connected NeoHive MCP server. No user input required.
- **Stage B — Synthesis** — LLM judgment over cartography output produces a draft topology block; user reviews and approves the draft.
- **Stage C — Write** — file-safety logic detects existing markers, computes diff, gets explicit user confirmation, then writes.

Each stage has at most one user gate (Stage B has the table-review gate; Stage C has the diff-confirm gate). Stage A is silent unless it errors.

## Stage A — Cartography (no user input)

```
1.1  list_hives                         → name, UUID, type, description per hive
1.2  memory_stats                       → type-distribution per hive (single call, all hives)
1.3  for each hive:
       probe_queries = derive_probes(hive.name, hive.description)
       memory_recall(hive=<uuid>, queries=probe_queries)
       → 5-10 sample memories per hive
```

### Probe derivation

`derive_probes(name, description)` produces 2-3 query strings per hive:

- Tokenize name and description, extract content words (drop stopwords, MCP boilerplate like "stores", "hive").
- Combine with intent suffixes: `"<token> convention"`, `"<token> directive"`, `"<token> example pattern"`.
- If `description` is missing or generic ("default hive", "main store"), fall back to generic probes: `"convention"`, `"directive"`, `"insight"`, `"example pattern"`.
- Cap probe count at 3 per hive to bound cartography token cost.

### Cartography failure modes

- `list_hives` empty / errors → abort with: "Cannot generate topology — no hives reachable. Confirm Phase 1 of getting-started passed before re-running." Do not write.
- `memory_stats` unavailable → continue; mark every row's "Write to it?" cell with `(verify)` and surface a one-line warning during the synthesis review gate.
- `memory_recall` returns nothing for a hive after the derived probes → re-attempt with the generic fallback probes. If still empty, set "What it holds" to `description` verbatim and append `(no sampled memories)`.

## Stage B — Synthesis

For each hive, the skill produces:

| Column          | Source                                                 | Inference rule                                                                                                                                                                                                                                                                                                                                      |
| --------------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hive (UUID)     | `list_hives`                                           | verbatim                                                                                                                                                                                                                                                                                                                                            |
| Name            | `list_hives`                                           | verbatim                                                                                                                                                                                                                                                                                                                                            |
| Type            | `list_hives`                                           | verbatim (`repo` / `knowledge` / `markdown` / etc.)                                                                                                                                                                                                                                                                                                 |
| Embedding model | `list_hives.description` + heuristic                   | code-tuned (e.g., `jina-embeddings-v2-base-code`) if hive is type `repo` or description mentions "code" / "indexed"; prose-tuned (e.g., `nomic-embed-text-v1.5`) if type is `knowledge` / `markdown` / description mentions "prose" / "curated". When uncertain, emit `(verify)`.                                                                   |
| What it holds   | sampled memories from 1.3 + type-distribution from 1.2 | 1-2 sentence synthesis grounded in real content; cite memory-type composition (e.g., "Mostly `convention` and `insight` entries — curated knowledge.")                                                                                                                                                                                              |
| Write to it?    | type-distribution from 1.2                             | heavy `example_pattern`/`syntax_rule`/`stdlib_reference` → "**NO** — auto-managed; manual writes risk being overwritten by indexing." ・ mixed `convention`/`directive`/`insight` → "**YES** — default write target." ・ small + `directive`-heavy → "**RARELY** — only for durable, language-level conventions. Ask the user before writing here." |

### Default write target selection

After table rows are computed, select `DEFAULT_WRITE_HIVE` as the hive with the largest write-safe (`YES`) memory count. Tie-break by hive name alphabetically. If no hive is write-safe, set default to `<none — ask before any write>` and emit a warning row in the table.

### Synthesis review gate

Render the proposed table to the terminal, then `AskUserQuestion`:

- **Header:** "Topology"
- **Question:** "Topology table looks right?"
- Options: `Looks good — proceed to write`, `Edit a row`, `Re-sample with different probes`, `Cancel`

`Edit a row` → ask which row + which column → accept free-text override → re-render and re-confirm.
`Re-sample with different probes` → ask for probe terms → re-run Stage A.3 only → re-synthesize.
`Cancel` → exit cleanly, no file writes.

## Stage C — Write

### Write-behavior matrix

| Existing state of `./CLAUDE.md`                                | Action                                                                                                        |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| File absent                                                    | Create `./CLAUDE.md` containing only the marker block.                                                        |
| File present with `<!-- BEGIN neohive-managed v=N -->` markers | Replace contents between the markers; preserve everything outside. Update `v=N` to current generator version. |
| File present without markers                                   | Append the marker block to end-of-file (preserves user-authored content at the top).                          |

### Marker format

```
<!-- BEGIN neohive-managed v=1 -->
<!-- Generated by /neohive:generate-claude-md on YYYY-MM-DD. Re-run to refresh. -->

...generated content...

<!-- END neohive-managed v=1 -->
```

Both markers carry the same `v=` integer.

**v1 upgrade behavior:** any existing block, regardless of `v=` value, is replaced wholesale on regeneration. v1 does NOT implement format-aware upgrade migration — older blocks are not parsed, only located and overwritten. The `v=` integer exists so that future generator versions (v2+) can introduce migration paths if the block format changes incompatibly; until then, treat it as advisory metadata.

### Diff-and-confirm gate

1. Compute proposed file content in memory.
2. Write to a temp file allocated via `mktemp` in `$TMPDIR` (NOT in the project worktree — keeps `git status` clean and avoids accidentally committing the temp file). Register a cleanup trap so the temp file is removed on any exit path including SIGINT and uncaught errors.
3. Run `diff -u CLAUDE.md "$tmp"` (treating absent `CLAUDE.md` as `/dev/null`); print the unified diff to terminal.
4. `AskUserQuestion`:
    - **Header:** "Write block"
    - **Question:** "Write this block to ./CLAUDE.md?"
    - Options: `Write`, `Edit block first`, `Cancel`
5. `Write` → atomic `mv "$tmp" ./CLAUDE.md` (atomic within same filesystem; fall back to `cp + rm` with a warning if `mv` crosses filesystems). `Edit block first` → spawn `$EDITOR` on `$tmp` → re-show diff → re-confirm. `Cancel` → cleanup trap fires, exit.

### Pre-write safety check

The check is gated on whether the **target file** (`./CLAUDE.md`) is inside a git worktree, not on the cwd. Logic:

- If `git -C $(dirname ./CLAUDE.md) rev-parse --is-inside-work-tree` returns `true`:
    - Run `git status --porcelain -- ./CLAUDE.md`. If non-empty, warn:
        > `CLAUDE.md` has uncommitted changes — recommend committing first so this skill's diff is easy to review separately. Continue?
    - User can confirm or cancel. Do not auto-commit.
- If the rev-parse fails (not a git repo): silently skip the check. The user has chosen to work outside a repo; do not nag.

## Generated content template

```markdown
<!-- BEGIN neohive-managed v=1 -->
<!-- Generated by /neohive:generate-claude-md on {{DATE}}. Re-run to refresh. -->

## NeoHive Cognitive Memory — Project Topology

Generic NeoHive tool-usage rules are loaded from `~/.claude/rules/neohive.md`.
This block adds the **project-specific** topology and routing that determine
WHICH hive serves which query, and where new writes should land.

### Hive Topology

| Hive (UUID) | Name | Type | Embedding model | What it holds | Write to it? |
| ----------- | ---- | ---- | --------------- | ------------- | ------------ |

{{ROWS}}

**Why query phrasing matters here.** {{QUERY_PHRASING_GUIDANCE}}

**Interpreting `[hive: <uuid>]` in recall results.** {{HIVE_PROVENANCE_GUIDE}}

### Session Start — Non-Negotiable (Project-Specific)

1. `memory_context` is your FIRST action — see `~/.claude/rules/neohive.md`.
2. Confirm the topology above has not drifted: call `list_hives` once per session.
   If a hive is added / removed / renamed, re-run `/neohive:generate-claude-md`.
3. Follow up with a targeted `memory_recall` for this project's domain. Suggested seeds:
   {{DOMAIN_RECALL_SEEDS}}

### What Goes Where: Cognitive Memory vs CLAUDE.md

| Store in **Cognitive Memory** | Store in **CLAUDE.md** |
| ----------------------------- | ---------------------- |

{{ROUTING_TABLE}}

### Hive routing for writes

Writes default to **{{DEFAULT_WRITE_HIVE}}** — {{DEFAULT_WRITE_RATIONALE}}.
**Do not pass an explicit `hive` parameter to `memory_store` unless you have a
specific reason.** When you do, write one sentence in the memory body explaining why.

{{ADDITIONAL_WRITE_HIVES_DISAMBIGUATION}}

<!-- END neohive-managed v=1 -->
```

### Substitution-variable contracts

| Variable                                    | Source                                                                                            | Format                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `{{DATE}}`                                  | system date at run time                                                                           | `YYYY-MM-DD`                                                                                                                                                                                                                                                                                                                                    |
| `{{ROWS}}`                                  | Stage B synthesis                                                                                 | one markdown table row per hive                                                                                                                                                                                                                                                                                                                 |
| `{{QUERY_PHRASING_GUIDANCE}}`               | Stage B — adapted to embedder mix                                                                 | 1 paragraph; mentions code-token queries iff any code-tuned hive present; mentions affirmative-statement queries iff any prose-tuned hive present; recommends both styles via `queries` parameter when both present.                                                                                                                            |
| `{{HIVE_PROVENANCE_GUIDE}}`                 | Stage B                                                                                           | 1 paragraph; per-hive 1-liner mapping name → typical content profile (e.g., "a hit from `<name>` came from indexed code; treat as factual").                                                                                                                                                                                                    |
| `{{DOMAIN_RECALL_SEEDS}}`                   | Stage B — synthesized from sampled content                                                        | 3-5 example query strings as a markdown bullet list, scoped to the project's domain.                                                                                                                                                                                                                                                            |
| `{{ROUTING_TABLE}}`                         | static template + actual hive names interpolated where the routing rules reference specific hives | 2-column markdown table; structurally same as Snyk's "What Goes Where" table; row contents reference user's actual hive names. **N=1 case:** still emit the full 2-column table — the conceptual split between cognitive memory and CLAUDE.md is independent of hive count, and a single-hive install still benefits from the routing guidance. |
| `{{DEFAULT_WRITE_HIVE}}`                    | Stage B default-write-target selection                                                            | hive name in backticks                                                                                                                                                                                                                                                                                                                          |
| `{{DEFAULT_WRITE_RATIONALE}}`               | Stage B                                                                                           | 1 sentence; cites why this hive was chosen (e.g., "it is the only `knowledge`-typed hive and accepts curated prose entries").                                                                                                                                                                                                                   |
| `{{ADDITIONAL_WRITE_HIVES_DISAMBIGUATION}}` | Stage B — only emitted when 2+ hives are write-safe                                               | bulleted disambiguation rules ("Use `<X>` when ...; use `<Y>` when ..."). Empty when only 1 write-safe hive.                                                                                                                                                                                                                                    |

## Coordination changes (existing files)

### `migrate-memory/SKILL.md` — marker-aware parsing

The marker exclusion is a **parser-level** concern, so it belongs in Phase 2 (Parse into candidate memories), not Phase 1 (Discover local memory sources). Phase 1's Bash discovery block continues to emit only filenames + sizes.

Add this rule at the top of Phase 2:

> Before splitting a project file into candidate memories, strip any content between `<!-- BEGIN neohive-managed v=N -->` and `<!-- END neohive-managed v=N -->` markers. The marker block is generated by `/neohive:generate-claude-md` and is intentionally not migrated — it's the topology/routing reference Claude needs in context BEFORE `memory_context` is called, so it must stay in CLAUDE.md.

**Concrete parsing strategy:** a line-range scan suffices. Match the regex `<!-- BEGIN neohive-managed v=\d+ -->` to find an opening marker; drop every line until matching `<!-- END neohive-managed v=\d+ -->`. Mismatched / unterminated markers are treated as a parse error and surfaced to the user with the offending file path; do not silently consume content.

Optionally enrich Phase 1's discovery report with a small marker-detection note (cheap — single grep per file):

```
Project-scoped sources found:
  - ./CLAUDE.md (4.2 KB, contains neohive-managed block — will be skipped during parsing)
```

Implementer's choice on whether to add this enrichment to Phase 1; the parsing exclusion in Phase 2 is the load-bearing change.

### `getting-started/SKILL.md` — phase reorganization

The current file has six numbered phases (Phase 0 — _Tell the user what's about to happen_ through Phase 5 — _Final summary_). Insert the new Phase 3 between current Phase 2 and current Phase 3, then renumber so the file ends at Phase 6.

**Renumbering map (exhaustive):**

| Current | New         | Phase title                                   |
| ------- | ----------- | --------------------------------------------- |
| Phase 0 | Phase 0     | Tell the user what's about to happen          |
| Phase 1 | Phase 1     | Register and verify the MCP server            |
| Phase 2 | Phase 2     | Auth token (only if needed)                   |
| —       | **Phase 3** | **Generate project CLAUDE.md topology (NEW)** |
| Phase 3 | Phase 4     | Migrate existing project memory               |
| Phase 4 | Phase 5     | Smart-recall hook (optional, power users)     |
| Phase 5 | Phase 6     | Final summary                                 |

New Phase 3 prose:

> ### Phase 3 — Generate project CLAUDE.md topology
>
> Now that the MCP is reachable, generate a project-specific topology block for `./CLAUDE.md`. This is what makes Claude reliable about _which_ hive to query and _where_ new writes should land — without it, the rules in `~/.claude/rules/neohive.md` are running blind.
>
> Ask (one `AskUserQuestion`):
>
> - **Header:** "Topology block"
> - **Question:** "Generate a project topology block in ./CLAUDE.md? (Recommended — improves tool-calling accuracy for everyone on this repo.)"
> - Options: `Yes (Recommended)`, `Yes, but let me review the table before writing`, `Skip — I'll run /neohive:generate-claude-md later`
>
> If "Yes" or "Yes, but review": invoke `Skill(skill="neohive:generate-claude-md")`. The sub-skill handles its own confirmation gates, so getting-started just waits for it to return.
>
> Report what happened: `Topology block written to ./CLAUDE.md (N hives mapped).`

Update Phase 6 (renumbered) summary block:

```
✓ MCP server reachable (N hives: ...)
✓ Auth token configured
✓ Project topology block in ./CLAUDE.md (N hives mapped)   ← NEW
✓ N project memories migrated
○ Smart-recall hook (skipped — rerun /neohive:generate-post-submit-hook anytime)
```

## Observability

End-of-run single-line summary:

```
generate-claude-md: 3 hives mapped, default write target: Knowledge,
written to ./CLAUDE.md (block lines 42-87, +35 lines vs previous version).
```

When the skill replaces an existing block, the summary additionally reports row-level diffs in a terse form. **Only emit a row when something actually changed** — unchanged hives are not listed:

```
  Topology changes:
    + added hive: StarlangLearnings (markdown, prose-tuned, RARELY write)
    ~ updated hive: patterns ("What it holds" updated; sample memory count grew 12 → 38)
```

If nothing changed at all (the regenerated block is identical to the existing one), surface that explicitly:

```
  Topology changes: none — block already up to date.
```

## Error-handling table

| Failure                                   | Handling                                                                       | User-visible behavior                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| `list_hives` empty / errors               | Abort, do not write                                                            | Error message naming the suspected cause; suggest re-running getting-started Phase 1 |
| `memory_stats` unavailable                | Continue with `(verify)` write-policy                                          | Warning in synthesis review gate; user may proceed                                   |
| `memory_recall` empty for hive            | Use generic fallback probes; if still empty, fall back to description verbatim | "What it holds" cell tagged `(no sampled memories)`                                  |
| User declines synthesis review            | Offer re-sample / edit-row / cancel                                            | No file writes                                                                       |
| User declines write gate                  | Print would-be content; exit                                                   | No partial writes                                                                    |
| `./CLAUDE.md` has uncommitted git changes | Warn; user confirms or cancels                                                 | Skill does not auto-commit                                                           |
| File write fails (permissions / disk)     | Surface OS error; leave file untouched                                         | No retry, no partial state                                                           |

## Testing

Manual verification steps for the implementer:

**Stage A (Cartography) — run in isolation against a real NeoHive MCP:**

- Confirm `list_hives` returns names + UUIDs; record output for fixture-building.
- Confirm `memory_stats` returns per-hive type counts; record output.
- Confirm probe-derivation produces sane queries for at least one realistic hive description (e.g., a hive named `Knowledge` with description "Curated insights"). Spot-check that probes are not just stopwords.

**Stage B (Synthesis) — fixture-driven:**

- Write a small fixture file capturing 2-3 representative `list_hives` + `memory_stats` + `memory_recall` shapes (one code-tuned hive, one prose-tuned hive, one auto-managed hive heavy in `example_pattern`).
- Run synthesis against the fixture; assert the produced table has the expected `Write to it?` policy per hive (`NO`/`YES`/`RARELY`) and that `(verify)` markers appear iff a column is uncertain.
- Decline the review gate; confirm no file is written.

**Stage C (Write) — three integration cases:**

1. Empty directory (no `./CLAUDE.md`): run skill, accept gates → assert `./CLAUDE.md` exists with marker block.
2. Existing `./CLAUDE.md` with marker block (from a previous run): run skill → assert only the marker block region changed; pre-existing user content outside markers byte-for-byte identical.
3. Existing `./CLAUDE.md` without markers (e.g., user-authored repo CLAUDE.md): run skill → assert original file content is preserved verbatim, marker block appended at EOF.

**Coordination — migrate-memory regression:**

- After Stage C runs, invoke `/neohive:migrate-memory` against the same `./CLAUDE.md`. Confirm: (a) Phase 1 detects the file; (b) Phase 2 parsing produces zero candidates from the marker-block region; (c) any user-authored content outside markers is parsed as candidates normally.

**Coordination — getting-started end-to-end:**

- Fresh repo + fresh NeoHive install. Run `/neohive:getting-started`. Confirm phases 0-6 fire in order, the new Phase 3 invokes `generate-claude-md`, and the final summary shows `✓ Project topology block in ./CLAUDE.md (N hives mapped)`.

No automated test harness is in scope for v1; manual verification per the above is sufficient. If the marketplace later adopts a test harness, fold these into it.

## Files changed by implementation

```
ADD     plugins/neohive/skills/generate-claude-md/SKILL.md
EDIT    plugins/neohive/skills/getting-started/SKILL.md         (add Phase 3, renumber)
EDIT    plugins/neohive/skills/migrate-memory/SKILL.md          (marker-aware exclusion)
EDIT    README.md                                               (add new skill to plugin table)
EDIT    plugins/neohive/.claude-plugin/plugin.json              (only if skill registration is required by the plugin system)
```

(The `.claude-plugin/plugin.json` edit is conditional — Claude Code auto-discovers SKILL.md files under `plugins/<plugin>/skills/<name>/SKILL.md`, so most likely no manifest change is needed; the implementation plan should verify.)

## Open questions

None at design time. All scope decisions were resolved during the brainstorm:

- Skill scope → project CLAUDE.md only; generic rules stay in `rules/neohive.md`. (Resolved.)
- Discovery method → auto-discover via `list_hives` + `memory_stats` + `memory_recall` probes (cartography). (Resolved.)
- Integration ordering → new Phase 3 in `getting-started`, before `migrate-memory`; also separately invocable. (Resolved.)
- Write safety → HTML-comment markers + diff-and-confirm; behavior matrix defined above. (Resolved.)
- Worked example → omitted from generated block; if added later, belongs in `rules/neohive.md`. (Resolved.)
- AGENTS.md / GEMINI.md / user-scope CLAUDE.md → out of scope for v1. (Resolved.)
