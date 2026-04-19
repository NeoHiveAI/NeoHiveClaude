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
| Skill | `start` | Pre-load relevant NeoHive memories for the current task via `memory_context` |
| Skill | `migrate-memory` | Scan local `CLAUDE.md` / `AGENTS.md` / `.claude/rules` and migrate project-scoped entries into NeoHive |
| Skill | `generate-docs` | Design a documentation gold standard through Socratic dialogue, save to NeoHive, validate with sample pages |
| Skill | `generate-post-submit-hook` | Generate a tailored smart-recall hook that rewrites prompts with a small model before querying NeoHive |
| Skill | `revise-vector-memory` | End-of-session extraction of learnings, corrections, and insights into vector memory |
| Hook | `SessionStart` | Installs/updates `~/.claude/rules/neohive.md` with persistent tool-usage instructions |
| Hook | `UserPromptSubmit` | Injects relevant memories into context automatically on every prompt |
| MCP | `securisource-neohive` | HTTP MCP server for the Securisource NeoHive |
| MCP | `snyk-neohive` | HTTP MCP server for the Snyk NeoHive |

The `.mcp.json` inside the plugin registers HTTP MCP servers on the NeoHive gateway. Override the server URLs or add additional hives by editing your project-level `.mcp.json` or `~/.claude.json`.

## Repository Layout

```
NeoHiveClaude/
├── .claude-plugin/
│   └── marketplace.json            # Marketplace catalog
└── plugins/
    └── neohive/
        ├── .claude-plugin/plugin.json
        ├── .mcp.json               # HTTP MCP server registration
        ├── hooks/
        │   ├── hooks.json
        │   ├── session-start.sh    # Manages ~/.claude/rules/neohive.md
        │   └── neohive-context.sh  # UserPromptSubmit memory recall
        ├── rules/neohive.md        # Persistent tool-usage instructions
        └── skills/
            ├── start/SKILL.md
            ├── getting-started/SKILL.md
            ├── migrate-memory/SKILL.md
            ├── generate-docs/SKILL.md
            ├── generate-post-submit-hook/
            │   ├── SKILL.md
            │   └── template.sh
            └── revise-vector-memory/SKILL.md
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
