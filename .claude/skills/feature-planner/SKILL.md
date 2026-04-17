---
name: feature-planner
description: Use when the user asks to build or implement a feature. Reads the feature definition, breaks it into ordered subtasks, updates the backlog, and enters plan mode before any code is written.
---

1. Read the feature definition from `docs/features.md`, `docs/architecture.md`, and `docs/mvp-scope.md` to fully understand scope and constraints before doing anything else.

2. Break the feature into the smallest independently testable subtasks:
   - Each subtask produces one testable artifact (function, endpoint, component, or test file)
   - Backend order: service layer → API route → tests → `make test`
   - Frontend order: API client → component → page wiring → `make test`
   - Every backend data transform must have a corresponding reconciliation test subtask
   - The final subtask of every feature is always: write tests → run `make test` → confirm pass

3. Write the subtasks to `journal/BACKLOG.md` under the correct phase, then enter plan mode and present the list to the user.

4. Wait for explicit user approval before writing any code. Do not begin implementation speculatively.

5. Once approved, work through subtasks in order. After each subtask, mark it done in `journal/BACKLOG.md` immediately — do not batch completions.

6. A feature is only complete when `make test` exits 0. Never mark a feature done before this.
