---
name: revise-vector-memory
description: DEPRECATED alias for `/neohive:capture-session-learnings`. This slug will be removed in a future minor release. Use `/neohive:capture-session-learnings` instead.
user-invocable: true
allowed-tools: Skill
---

# Deprecated: `revise-vector-memory`

This skill has been renamed to **`capture-session-learnings`** for end-user clarity. The behavior is identical.

Invoke the new slug now and stop:

```
Skill(skill="neohive:capture-session-learnings")
```

Tell the user once: "Note: `/neohive:revise-vector-memory` was renamed to `/neohive:capture-session-learnings`; please use the new slug going forward."

Do not duplicate the work locally; the new skill owns the canonical instructions.
