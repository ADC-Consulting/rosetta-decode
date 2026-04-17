---
name: git-committer
description: Use before making any git commit. Enforces atomic commits, conventional commit format, verifies the journal is up to date, and ensures no secrets are staged.
---

## Use for
- Committing any completed unit of work (feature subtask, fix, refactor, docs update)
- Verifying the journal is current before sealing a commit
- Mid-session commits when a logical unit is complete

## Do NOT use for
- Pushing to remote (ask the user explicitly)
- Amending already-pushed commits
- Bulk "save everything" commits — each commit must be atomic

## What is an atomic commit

One commit = one logical change. A reviewer should be able to read the subject line and understand exactly what changed and why, without reading the diff.

**Good — atomic:**
```
feat(F1): add SAS DATA step parser returning block list

fix: handle empty PROC SQL block without raising KeyError

test: add reconciliation test for DATA step → DataFrame transform

chore: add ruff and mypy pre-commit hooks
```

**Bad — not atomic:**
```
various fixes and updates

wip

add stuff and also fix the parser and update readme
```

A commit that touches `src/backend/engine/parser.py` AND `README.md` AND `journal/BACKLOG.md` is fine — as long as all three files are part of the same logical change (e.g. "implement parser + mark backlog item done + document the new command"). A commit that mixes two unrelated features is not.

## Steps (run IN ORDER)

1. **Run `make test`.** Tests must pass before staging anything. If `make test` fails, fix the failure first — never commit broken code. For docs-only or journal-only commits with no code changes, this step can be skipped.

2. **Verify the journal.** Check that `journal/BACKLOG.md` has completed items checked off and any newly discovered tasks added. If architectural decisions were made, verify `journal/DECISIONS.md` is updated too.

3. **Identify the logical unit.** If there are changes spanning multiple unrelated concerns, split them into separate commits — run this skill once per logical unit.

4. **Stage specific files by name.** Never use `git add -A` or `git add .`. Inspect each file before staging. Confirm no `.env`, credentials, API keys, or secrets are included.

5. **Draft a conventional commit message:**
   - `feat(FX):` new capability tied to a feature ID (e.g. `feat(F1): add PROC SQL parser`)
   - `fix:` bug fix
   - `refactor:` restructuring without behaviour change
   - `test:` adding or updating tests
   - `docs:` documentation only
   - `chore:` tooling, config, dependencies
   - Subject line: imperative mood, ≤72 characters, no trailing period
   - Body (optional): explain the *why*, not the *what*

6. **Show the user the staged file list and commit message.** Wait for explicit approval before running `git commit`. Never add Co-Authored-By or any Claude attribution.

7. **Run `git commit`.** Never use `--no-verify`. Pre-commit hooks (ruff + mypy) run automatically — if a hook fails, fix the underlying issue and retry. Hooks enforce code quality; `make test` (step 1) enforces correctness.

8. **Never amend a commit that has already been pushed.**
