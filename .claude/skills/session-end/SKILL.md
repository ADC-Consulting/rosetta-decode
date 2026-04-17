---
name: session-end
description: Run before stopping to update the journal and commit any outstanding work.
---

## Use for
- Closing every working session, no exceptions
- Ensuring context is preserved for the next contributor or session

## Do NOT use for
- Mid-session saves (use `git-committer` directly for atomic mid-session commits)
- Deploying or pushing to remote (ask the user explicitly)

## Steps

### 1. Update the active feature plan (if any)

Check `docs/plans/` for a plan file with `Status: in-progress`. If one exists:
- Mark completed subtasks as `- [x] done`
- Update `Status:` to `in-progress` (still going) or `complete` (all criteria met)
- Do not add new subtasks here — new scope goes in `journal/BACKLOG.md`

### 2. Update BACKLOG.md

- Check off completed items
- Add any newly discovered tasks under the correct phase
- If a feature plan file exists, backlog entries for that feature should reference it:
  `- [x] F<N>: <subtask> → see docs/plans/F<N>-<slug>.md`

### 3. Update DECISIONS.md

If any architectural decision was made this session, append it to `journal/DECISIONS.md`:
```
- **<Decision>:** <what was decided> · <rationale> · revisit <when/never>
```

If the decision is non-trivial (new service, data model change, external dependency added), also create an ADR in `docs/adr/`.

### 4. Append a new entry to the TOP of SESSIONS.md

```
## YYYY-MM-DD — <one-line session title>
**Duration:** ~Xh | **Focus:** <topic>

### Done
- <item>

### Decisions
- <decision and rationale, or "none">

### Open Questions
- <question, or "none">

### Next Session — Start Here
1. <concrete first action, referencing the plan file if a feature is in progress>

### Files Touched
- <file>
```

### 5. Show diffs and wait for approval

Show the user what changed in the journal files. Wait for explicit approval before committing.

### 6. Invoke git-committer

Run the `git-committer` skill for the final commit. Journal updates and feature plan updates are one logical unit — commit them together unless there are also unrelated code changes that should be separate commits.
