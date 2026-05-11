# NeoHiveClaude

A Claude Code plugin marketplace for the [NeoHive](https://github.com/NeoHiveAi) cognitive memory system. Install the `neohive` plugin to wire Claude Code into any NeoHive MCP server — persistent semantic memory across sessions, automatic context recall, and post-session learning extraction.

## Quick Start

### 1. Add the marketplace

```
/plugin marketplace add NeoHiveAi/NeoHiveClaude
```

### 2. Install the plugin

```
/plugin install neohive@neohive-claude
```

### 3. Run the guided setup

```
/neohive:getting-started
```

One command walks you through verifying the MCP server, setting up auth, migrating any existing project memory (CLAUDE.md, AGENTS.md, `.claude/rules`) into NeoHive, and optionally enabling the smart-recall hook. 3–5 minutes end-to-end.

### 4. (Optional) Environment overrides

If your NeoHive server requires auth, export a bearer token before launching Claude:

```bash
export NEOHIVE_TOKEN="your-token-here"
```

Disable the auto-context hook for a session:

```bash
export NEOHIVE_HOOK_DISABLED=1
```

## Available Plugins

### `neohive`

NeoHive cognitive memory — MCP server registration, managed rules for tool usage, and post-session learning extraction.

| Type | Name | Description |
|------|------|-------------|
| Skill | `getting-started` | Guided first-run: verify MCP, set auth, migrate memory, enable helpers. Start here. |
| Skill | `load-context` | Pre-load relevant NeoHive memories for the current task via `memory_context`. Run at the start of every session. |
| Skill | `migrate-memory` | Scan local `CLAUDE.md` / `AGENTS.md` / `.claude/rules` and migrate project-scoped entries into NeoHive |
| Skill | `design-codebase-docs` | Design a documentation gold standard through Socratic dialogue, save to NeoHive, validate with sample pages |
| Skill | `enable-smart-prompts` | Generate a tailored smart-recall hook that rewrites prompts with a small model before querying NeoHive |
| Skill | `capture-session-learnings` | End-of-session extraction of learnings, corrections, and insights into NeoHive semantic memory |
| Agent | `explore-neohive` | Semantic-first codebase + knowledge exploration subagent. Prefer this over the built-in `Explore` in NeoHive-indexed projects. |
| Hook | `SessionStart` | Installs/updates `~/.claude/rules/neohive.md` with persistent tool-usage instructions |
| Hook | `UserPromptSubmit` | Injects relevant memories into context automatically on every prompt |
| Hook | `PreToolUse` (Glob, Grep) | Nudges Claude toward `memory_recall` when running broad filesystem searches inside an indexed project (`NEOHIVE_PRETOOL_STRICT=1` to hard-deny, `NEOHIVE_PRETOOL_DISABLED=1` to opt out) |

The slugs `start`, `revise-vector-memory`, `generate-docs`, and `generate-post-submit-hook` remain as deprecated aliases that redirect to the new names; they will be removed in a future minor release.

The plugin does **not** ship a pre-configured MCP server — you register your own NeoHive gateway via Claude Code's built-in MCP commands (e.g. `/mcp` in-session or `claude mcp add`). The hook and skills discover any MCP server whose key contains `neohive` in your project `.mcp.json` or `~/.claude.json`, so one registration covers the whole plugin.

## Repository Layout

```
NeoHiveClaude/
├── .claude-plugin/
│   └── marketplace.json                 # Marketplace catalog
└── plugins/
    └── neohive/
        ├── .claude-plugin/plugin.json
        ├── agents/
        │   └── explore-neohive.md       # Semantic-first exploration subagent
        ├── hooks/
        │   ├── hooks.json
        │   ├── session-start.sh         # Manages ~/.claude/rules/neohive.md
        │   ├── neohive-context.sh       # UserPromptSubmit memory recall
        │   └── pretool-tree-walker.sh   # PreToolUse nudge on Glob/Grep
        ├── rules/neohive.md             # Persistent tool-usage instructions
        └── skills/
            ├── getting-started/SKILL.md
            ├── load-context/SKILL.md
            ├── capture-session-learnings/SKILL.md
            ├── migrate-memory/SKILL.md
            ├── design-codebase-docs/SKILL.md
            ├── enable-smart-prompts/
            │   ├── SKILL.md
            │   └── template.sh
            ├── start/SKILL.md                       # deprecated alias
            ├── revise-vector-memory/SKILL.md        # deprecated alias
            ├── generate-docs/SKILL.md               # deprecated alias
            └── generate-post-submit-hook/SKILL.md   # deprecated alias
```

## Development

Test locally without installing:

```bash
claude --plugin-dir ./plugins/neohive
```

Validate the plugin and marketplace manifests:

```bash
claude plugin validate ./plugins/neohive
claude plugin validate .
```

After editing skills/hooks in an active session, run `/reload-plugins` to pick up changes without restarting.

## Versioning

Bump the `version` field in `plugins/neohive/.claude-plugin/plugin.json` on every change — Claude Code uses the version as a cache key, so without a bump installed users will NOT see updates.
