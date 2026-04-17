---
name: plan-feature
description: Run when starting any new feature. Reads context, breaks into subtasks, enters plan mode, and waits for approval before coding.
---

## Use for
- Starting work on any new feature from the backlog
- Getting explicit user approval on the implementation plan before any code is written

## Do NOT use for
- Continuing an already-planned feature (pick up from `journal/BACKLOG.md`)
- Small fixes or chores that don't need a formal plan

## Steps

1. Read `docs/features.md`, `docs/architecture.md`, and `docs/mvp-scope.md` to understand the feature's scope and constraints before doing anything else.

2. Break the feature into the smallest independently testable subtasks:
   - Each subtask produces one testable artifact (function, endpoint, component, or test file)
   - Backend order: service layer → API route → tests → `make test`
   - Frontend order: API client → component → page wiring → `make test`
   - Every backend data transform must have a corresponding reconciliation test subtask
   - The final subtask of every feature is always: write tests → run `make test` → confirm pass

3. Write the subtasks to `journal/BACKLOG.md` under the correct phase.

4. Enter plan mode and present the subtask list to the user. Wait for explicit approval before writing any code.

5. Once approved, work through subtasks in order. After each subtask, mark it done in `journal/BACKLOG.md` immediately — do not batch completions.

6. A feature is only complete when `make test` exits 0.
