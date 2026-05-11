---
name: load-context
description: Use when the user says "start", "load context", "pre-load memory", "what do we know about X", or at the beginning of any session before doing real work. Calls `memory_context` with the current task description so directives, conventions, and relevant prior knowledge land in context before Claude starts editing or exploring.
user-invocable: true
---

# Load NeoHive Context for This Session

Call `memory_context` immediately to pre-load relevant knowledge for this session. Prefer this skill over manually crafting an opening `memory_recall` query — `memory_context` is tuned to load both directives (project rules) and task-specific snippets in one pass.

## Task Description

If the user provided arguments: use `$ARGUMENTS` as the task description.

If no arguments were provided: summarize the current task based on conversation context so far. If there is no context yet, ask the user what they're working on.

## After Loading

Once `memory_context` returns, briefly report:
- How many relevant memories were loaded
- The key topics/directives that were surfaced (1-3 bullet points max)
- Whether any directives or conventions were found that should guide this session

Then proceed with whatever the user asked for. Do not ask for confirmation to continue.
