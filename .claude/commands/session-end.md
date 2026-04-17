---
description: Persist session state before stopping
---

Do the following IN ORDER:

1. **Update the active feature plan (if any)**  
   Check `docs/plans/` for a file with `Status: in-progress`. If found:
   - Mark completed subtasks as `- [x] done`
   - Set `Status: complete` if all acceptance criteria are met, otherwise leave as `in-progress`

2. **Update `journal/BACKLOG.md`**  
   - Check off completed items
   - Add any newly discovered tasks under the correct phase
   - Backlog entries for a feature in progress should reference its plan file:
     `- [x] F<N>: <subtask> → see docs/plans/F<N>-<slug>.md`

3. **Update `journal/DECISIONS.md`** if any architectural decision was made this session.  
   If the decision is non-trivial (new service, data model change, external dependency), also create an ADR in `docs/adr/`.

4. **Append a new entry to the TOP of `journal/SESSIONS.md`** using today's real date:
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
   1. <concrete first action — reference the plan file if a feature is in progress>

   ### Files Touched
   - <file>
   ```

5. **Show the user the journal diffs** and wait for explicit approval before committing.

6. **Invoke the `git-committer` skill** for the final commit. Journal updates and plan file updates are one logical unit — commit them together unless there are unrelated code changes that belong in a separate commit.
