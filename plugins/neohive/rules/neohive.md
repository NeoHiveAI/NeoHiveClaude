---
version: '1.6.4'
managed_by: neohive-plugin
---

# NeoHive Cognitive Memory

You have access to a persistent semantic memory system via MCP tools. The hives connected to this session may contain durable team knowledge **and indexed source code** (typically embedded with a code-tuned model such as `jina-embeddings-v2-base-code`). Treat the hives as a first-class navigation surface, not a side-channel. **Use them actively, not passively.**

## Session Start — ALWAYS Do This First

Call `memory_context` with a description of your current task BEFORE doing any work. This loads relevant directives, conventions, and task-specific knowledge. Describe the task in affirmative form with specific domain terms:

- GOOD: `"implementing authentication middleware for Express gateway"`
- BAD: `"what do we know about auth?"`

If the task involves a specific domain (e.g., starlang rules, dashboard tiles), call `memory_context` again with a domain-specific description to pre-load relevant context.

## Codebase Exploration — Prefer `memory_recall` Over File Traversal

If a hive contains the codebase you're working in (the `list_hives` output names a `repo`-typed hive, or `memory_context` returned indexed code snippets), call `memory_recall` BEFORE doing broad file exploration with Glob, Grep, or Read. The indexed embedding is almost always faster and uses less context than walking the tree:

- Frame the query as what you'd say to a teammate: `"how does the sync engine handle git clone credentials"` not `"find git clone code"`.
- Use `memory_recall` to locate the relevant files, then use `Read` for the precise line numbers you need to edit.
- Fall back to Glob/Grep only when you need an exact symbol that semantic search misses, or for files outside the index (e.g. brand-new files in your working tree).

This applies for the entire session, not just at start: every time you'd reach for "let me search the codebase for X," try `memory_recall` first.

The plugin also ships a `PreToolUse` hook (`pretool-tree-walker.sh`) that fires on `Glob` and `Grep` whenever the current working directory is inside a project with a NeoHive MCP server configured in `.mcp.json`. By default the hook lets the tool run and injects a reminder; set `NEOHIVE_PRETOOL_STRICT=1` to make it hard-deny those tools in indexed projects, or `NEOHIVE_PRETOOL_DISABLED=1` to opt out entirely.

## Delegating to Subagents — Prefer `explore-neohive` Over Built-In `Explore`

This plugin bundles a subagent called **`explore-neohive`** whose tool allowlist and system prompt force semantic recall first. Whenever you would dispatch the built-in `Explore` agent for codebase or knowledge exploration in this project, dispatch `explore-neohive` instead. It is faster, uses less context, and returns ranked snippets with provenance metadata that filesystem tools cannot produce.

Examples of when to pick `explore-neohive`:

- "Where is X defined?" / "How does Y work?" / "What's the convention for Z?"
- Architecture questions, decision archaeology, locating files by concept rather than by exact symbol.
- Open-ended research where you don't yet know the precise file paths.

Stick with the built-in `Explore` only when:

- The project has no NeoHive instance reachable (no `mcp__neohive__*` tools available), or
- You need an exact-symbol search that semantic recall has already missed in this session.

**Other subagents (implementation, general-purpose, etc.):** The MCP tool list is inherited by subagents you spawn, but **the directives in this rules file are not.** When the work touches an indexed area of the codebase, include in the subagent's prompt:

> "This project has a NeoHive instance with indexed code/knowledge. Before file exploration, call `mcp__neohive__memory_recall` (or `mcp__neohive__memory_context` if you're starting fresh) with an affirmative description of what you're looking for. Use Glob/Grep/Read only for precise line numbers or files the index doesn't cover."

## Discovering Hives

Call `list_hives` to see what hives are available. Each hive has a description explaining what it stores (code, knowledge, rules, etc.). Use this to decide which hive to target for writes.

## Reading — memory_recall & memory_context

When no `hive` parameter is specified, reads search across ALL hives using cross-hive RRF fusion — the most relevant results from any hive are returned. You usually want this behavior.

Query formulation matters:

- Write **affirmative statements**, not questions: `"error handling in async batch processing"` not `"How do we handle errors?"`
- Include **specific domain terms** that would appear in stored knowledge: `"sqlite-vec F32_BLOB column type"` not `"vector database column"`
- Use the **types parameter** to narrow results: `types: ["directive", "convention"]` for rules, `types: ["error_pattern", "insight"]` for gotchas
- For important retrievals, pass **multiple queries** via the `queries` parameter — 2-4 different phrasings of the same need

Call `memory_recall` before working on unfamiliar topics or when you need specific knowledge. If results are weak, reformulate and retry with synonyms or broader/narrower scope.

## Writing — memory_store

A `hive` parameter is **required** for writes. Use `list_hives` to find the right hive.

Call `memory_store` when:

- The user corrects you or says "no, we do X instead"
- A new convention or rule is established
- You discover a non-obvious gotcha or insight
- An architectural decision is made with rationale
- A tricky bug is debugged and solved

Write content as a **self-contained statement** that someone with no context could understand in 6 months. Include specific terms that future searches would use to find this knowledge.

Memory types: `directive` (rules/musts), `convention` (practices/preferences), `decision` (trade-offs with rationale), `insight` (gotchas/discoveries), `error_pattern` (bugs/pitfalls), `syntax_rule`, `semantic_rule`, `example_pattern`, `idiom`.

## Forgetting — memory_forget

Call `memory_forget` when knowledge becomes outdated or is superseded by a correction. Always provide a `reason` and `superseded_by` ID if a replacement was stored.

## User-Invocable Skills

The plugin ships these slash commands. Suggest them when the user's request matches:

- `/neohive:getting-started` — first-run setup (verify MCP, configure auth, generate topology block, migrate memory, enable helpers). Run once per machine.
- `/neohive:load-context` — pre-load relevant memory for the current task via `memory_context`. Run at the start of every session.
- `/neohive:generate-claude-md` — survey connected hives and write a project-specific topology block into `./CLAUDE.md`. Re-run when hives are added, removed, or renamed.
- `/neohive:capture-session-learnings` — end-of-session extraction of corrections, conventions, decisions, and insights into NeoHive. Also fires automatically from the stop hook.
- `/neohive:migrate-memory` — scan local `CLAUDE.md` / `AGENTS.md` / `.claude/rules` and import project-scoped entries into a hive.
- `/neohive:design-codebase-docs` — Socratic design of a documentation standard, save to NeoHive, validate with sample pages.
- `/neohive:enable-smart-prompts` — install a smarter UserPromptSubmit hook that rewrites prompts with a small model before querying NeoHive.

The slugs `revise-vector-memory`, `start`, `generate-docs`, and `generate-post-submit-hook` are deprecated aliases that redirect to the new names; they will be removed in a future minor release.
