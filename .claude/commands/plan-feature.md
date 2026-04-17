```markdown
---
description: Produce a plan for a new feature using grounded context
---

Before planning:

1. Read `CLAUDE.md`
2. Read `docs/user-stories.md` and `docs/features.md`
3. Read `specs/mvp-scope.md`
4. Read the TOP entry of `journal/SESSIONS.md`

Then produce a plan for the feature the user names, containing:

1. **User story mapping** — which US and acceptance criteria this serves
2. **File tree changes** — new/modified files
3. **Implementation order** — smallest vertical slice first
4. **Interfaces** — function signatures and data contracts
5. **Test strategy** — unit + reconciliation tests
6. **CLOUD flag handling** — how this behaves in both modes
7. **Open questions** — anything requiring user input before coding

STOP after the plan. Do not write code until the user approves.
```
