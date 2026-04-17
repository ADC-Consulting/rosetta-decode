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

1. Append a new entry to the TOP of `journal/SESSIONS.md` using this format:
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
   - <concrete first action>

   ### Files Touched
   - <file>
   ```

2. Update `journal/BACKLOG.md`: check off completed items, add any newly discovered tasks under the correct phase.

3. If any architectural decision was made this session, log it in `journal/DECISIONS.md` with rationale and a revisit flag if appropriate.

4. If a non-trivial architectural choice was made, create an ADR in `docs/adr/` following the existing format.

5. Show the user the journal diffs and wait for approval before committing. Then invoke the `git-committer` skill for the commit.
