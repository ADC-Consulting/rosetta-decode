```markdown
# Session Journal

Most recent session on top. Each entry should answer:

- What did we do?
- What decisions did we make?
- What's blocked or open?
- What's the very next thing to do?

---

## 2026-04-17 — Project Kickoff

**Participants:** Mattia + Claude
**Duration:** ~1h
**Focus:** Setting up project scaffolding and Claude Code configuration

### Done

- Defined two user stories (tech user + non-tech user)
- Expanded 7 features across backend/frontend
- Created CLAUDE.md, skills, commands, and journal structure
- Locked in MVP constraints: CLOUD flag in .env, local + Databricks support

### Decisions

- See `journal/DECISIONS.md` entries dated 2026-04-17

### Open Questions

- Frontend framework: Streamlit for MVP, confirmed?
- Which SAS sample files will we use as the first migration target?
- Do we have access to a Databricks workspace for testing CLOUD=true path?

### Next Session — Start Here

1. Pick the first SAS sample file (smallest, self-contained)
2. Plan the vertical slice: ingest → translate → execute → reconcile (CLOUD=false)
3. Scaffold the `ComputeBackend` interface
4. Write the first reconciliation test

### Files Touched

- CLAUDE.md (created)
- .claude/skills/\* (created)
- .claude/commands/\* (created)
- journal/\* (created)
- docs/\* (created)
- specs/mvp-scope.md (created)
```
