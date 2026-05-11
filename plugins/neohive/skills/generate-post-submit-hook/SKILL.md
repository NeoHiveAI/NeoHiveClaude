---
name: generate-post-submit-hook
description: DEPRECATED alias for `/neohive:enable-smart-prompts`. This slug will be removed in a future minor release. Use `/neohive:enable-smart-prompts` instead.
user-invocable: true
allowed-tools: Skill
---

# Deprecated: `generate-post-submit-hook`

This skill has been renamed to **`enable-smart-prompts`** to remove internal Claude Code terminology (`post-submit` was implementation jargon). The behavior is identical.

Invoke the new slug now and stop:

```
Skill(skill="neohive:enable-smart-prompts")
```

Tell the user once: "Note: `/neohive:generate-post-submit-hook` was renamed to `/neohive:enable-smart-prompts`; please use the new slug going forward."
