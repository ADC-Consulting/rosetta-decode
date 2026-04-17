---
name: session-start
description: Run at the start of every session to restore context before proposing any work.
---

## Use for
- Starting every working session, no exceptions
- Onboarding a new contributor who needs context fast

## Do NOT use for
- Mid-session context checks (just read the journal directly)
- Resuming after a short break in the same session

## Steps

1. Read `journal/SESSIONS.md` — top entry only (most recent session).

2. Read `journal/BACKLOG.md` — identify what phase is active and what tasks are pending.

3. Read `journal/DECISIONS.md` — note any constraints that affect today's work.

4. Check `docs/plans/` for any feature plan files with `Status: in-progress`. If one exists, read it — it is the active work context and takes priority over the general backlog.

5. Summarize to the user:
   - What was done last session
   - What feature (if any) is in progress, and which subtask is next
   - What is next on the backlog if no feature is in progress
   - Any open questions or blockers

6. Wait for the user to confirm the context or redirect before proposing or starting any work.
