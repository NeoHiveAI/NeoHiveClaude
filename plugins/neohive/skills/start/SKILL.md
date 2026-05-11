---
name: start
description: DEPRECATED alias for `/neohive:load-context`. This slug will be removed in a future minor release. Use `/neohive:load-context` instead.
user-invocable: true
allowed-tools: Skill
---

# Deprecated: `start`

This skill has been renamed to **`load-context`** for end-user clarity (`start` was generic and collided with built-in commands in many tools). The behavior is identical.

Invoke the new slug now and stop:

```
Skill(skill="neohive:load-context")
```

Tell the user once: "Note: `/neohive:start` was renamed to `/neohive:load-context`; please use the new slug going forward."
