```markdown
---
description: Persist session state before stopping
---

You are ending the current Claude Code session. Update the journal so the next
session can resume cleanly.

Do the following:

1. **Append a new entry to the TOP of `journal/SESSIONS.md`** with today's date
   and a structured summary:
   - Focus
   - Done (bullets)
   - Decisions (reference DECISIONS.md entries)
   - Open Questions
   - Next Session — Start Here (concrete, actionable first step)
   - Files Touched

2. **Update `journal/BACKLOG.md`:**
   - Check off completed items
   - Add any new items discovered this session
   - Reorder if priorities shifted

3. **Update `journal/DECISIONS.md`** if any new decisions were made.

4. **Create an ADR in `docs/adr/`** if a non-trivial architectural choice was made
   (use `/adr` command as reference).

5. **Create a detailed session file** at
   `journal/sessions/YYYY-MM-DD-<slug>.md` summarizing transcript highlights,
   artifacts produced, and handoff notes.

6. Show the user a diff summary of what you updated and ask them to confirm
   before committing.

IMPORTANT: Use today's real date from the system, not a placeholder.
```
