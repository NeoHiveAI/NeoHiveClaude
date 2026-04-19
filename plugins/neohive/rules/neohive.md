---
version: "1.0.0"
managed_by: neohive-plugin
---

# NeoHive Cognitive Memory

You have access to a persistent semantic memory system via MCP tools. This memory stores knowledge across sessions — corrections, conventions, decisions, insights, and code patterns. **Use it actively, not passively.**

## Session Start — ALWAYS Do This First

Call `memory_context` with a description of your current task BEFORE doing any work. This loads relevant directives, conventions, and task-specific knowledge. Describe the task in affirmative form with specific domain terms:

- GOOD: `"implementing authentication middleware for Express gateway"`
- BAD: `"what do we know about auth?"`

If the task involves a specific domain (e.g., starlang rules, dashboard tiles), call `memory_context` again with a domain-specific description to pre-load relevant context.

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
