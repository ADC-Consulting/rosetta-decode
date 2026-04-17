---
name: plan-feature
description: Run when starting any new feature. Reads context, breaks into ordered subtasks with dependencies, writes a feature plan file, and waits for approval before coding.
---

## Use for
- Starting work on any new feature from the backlog
- Getting explicit user approval on the implementation plan before any code is written

## Do NOT use for
- Continuing an already-planned feature — read the existing plan file in `docs/plans/` instead
- Small fixes or chores that do not need a formal plan

## Steps

### 1. Read context

Read all of the following before doing anything else:

- `docs/features.md` — feature definition, area, phase
- `docs/architecture.md` — service layout, API contracts, data model
- `docs/mvp-scope.md` — what is and is not in scope
- `docs/coding-standards.md` — conventions to follow
- `journal/BACKLOG.md` — current phase and existing tasks
- `journal/DECISIONS.md` — locked constraints

### 2. Break the feature into subtasks

Rules for subtask decomposition:
- Each subtask produces exactly one independently testable artefact: a function, a route, a schema migration, a component, or a test file
- Subtasks must be ordered — list blocked subtasks after the ones they depend on
- Mark dependencies explicitly: "requires: <subtask name>"
- Never combine data model + service logic + route in one subtask

**Ordering by area** (derive exact paths from `docs/architecture.md` — Directory Structure section):

Worker service:
1. Data model / Alembic migration (if new DB columns needed)
2. Core logic: engine, validation, or compute layer
3. Unit tests for core logic
4. Integration with worker poll loop (if applicable)

API service:
1. Request/response Pydantic schemas
2. FastAPI route
3. Route tests (pytest + TestClient)

Frontend:
1. API client function
2. Component
3. Page wiring
4. Manual smoke test note

Always last:
- Run `make test` and confirm exit 0
- Mark feature done in `journal/BACKLOG.md`

### 3. Write the feature plan file

Create `docs/plans/F<N>-<slug>.md` (e.g. `docs/plans/F1-pipeline-generation.md`).

Use this structure:

```markdown
# F<N> — <Feature Name>

**Phase:** <1|2|3|4>
**Area:** <Backend / Worker | Backend / API | Frontend | Both>
**Status:** in-progress

## Goal

One paragraph: what this feature does, why it matters, what done looks like.

## Acceptance Criteria

- [ ] <concrete, testable criterion>
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Subtasks

### <subtask-id>: <name>
**File:** `<exact path>`
**Depends on:** <subtask-id or "none">
**Done when:** <one sentence — what exists that didn't before>
- [ ] done

(repeat for each subtask)

## Dependencies on other features

- <F-number and what specifically is needed, or "none">

## Out of scope for this feature

- <explicit exclusion>
```

### 4. Update BACKLOG.md

Add the subtasks under the correct phase in `journal/BACKLOG.md`, formatted as:
```
- [ ] F<N>: <subtask name> → see `docs/plans/F<N>-<slug>.md`
```

### 5. Enter plan mode

Present the plan to the user. Wait for explicit approval before writing any code.

### 6. Execute in order

Work through subtasks sequentially. After each one:
- Mark it done in the plan file (`- [x] done`)
- Mark it done in `journal/BACKLOG.md`
- Do not batch completions

A feature is only complete when `make test` exits 0 and all acceptance criteria are checked off.
