---
name: start
description: Initialize NeoHive memory for the current session. Call at the start of a session to load relevant knowledge before doing any work.
user-invocable: true
---

# Initialize NeoHive Memory

Call `memory_context` immediately to pre-load relevant knowledge for this session.

## Task Description

If the user provided arguments: use `$ARGUMENTS` as the task description.

If no arguments were provided: summarize the current task based on conversation context so far. If there is no context yet, ask the user what they're working on.

## After Loading

Once `memory_context` returns, briefly report:
- How many relevant memories were loaded
- The key topics/directives that were surfaced (1-3 bullet points max)
- Whether any directives or conventions were found that should guide this session

Then proceed with whatever the user asked for. Do not ask for confirmation to continue.
