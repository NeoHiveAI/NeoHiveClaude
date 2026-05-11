---
name: generate-docs
description: DEPRECATED alias for `/neohive:design-codebase-docs`. This slug will be removed in a future minor release. Use `/neohive:design-codebase-docs` instead.
user-invocable: true
allowed-tools: Skill
---

# Deprecated: `generate-docs`

This skill has been renamed to **`design-codebase-docs`** to better describe the workflow (Socratic standard design + sample validation, not bulk generation). The behavior is identical.

Invoke the new slug now and stop:

```
Skill(skill="neohive:design-codebase-docs")
```

Tell the user once: "Note: `/neohive:generate-docs` was renamed to `/neohive:design-codebase-docs`; please use the new slug going forward."
