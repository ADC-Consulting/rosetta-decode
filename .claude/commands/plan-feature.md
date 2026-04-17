---
description: Plan a new feature — reads context, writes docs/plans/F<N>-<slug>.md, enters plan mode
---

Read the following before doing anything else:

1. `CLAUDE.md`
2. `docs/features.md` — find the feature definition, area, and phase
3. `docs/architecture.md` — service layout, API contracts, data model
4. `docs/mvp-scope.md` — what is and is not in scope
5. `docs/coding-standards.md` — conventions to follow
6. `journal/BACKLOG.md` — current phase and existing tasks
7. `journal/DECISIONS.md` — locked constraints

Then break the feature into the smallest independently testable subtasks, ordered by dependency.

Derive exact service names and directory paths from the **Directory Structure** section of `docs/architecture.md` — do not hard-code them here. General ordering:

- Worker service: data model/migration → core logic → unit tests → worker loop wiring
- API service: Pydantic schemas → FastAPI route → route tests
- Frontend: API client → component → page wiring
- Always last: run `make test`, confirm exit 0, mark feature done in backlog

Write a plan file at `docs/plans/F<N>-<slug>.md` using this structure:

```
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
**Done when:** <one sentence>
- [ ] done

## Dependencies on other features
- <F-number and what is needed, or "none">

## Out of scope for this feature
- <explicit exclusion>
```

Add entries to `journal/BACKLOG.md` under the correct phase:
```
- [ ] F<N>: <subtask name> → see `docs/plans/F<N>-<slug>.md`
```

Enter plan mode. Present the subtask list to the user. Wait for explicit approval before writing any code.
