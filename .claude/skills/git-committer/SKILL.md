---
name: git-committer
description: Use before making any git commit. Enforces conventional commit format, verifies the journal is up to date, and ensures no secrets are staged.
---

1. Before staging anything, verify `journal/BACKLOG.md` has been updated: completed items checked off, any newly discovered items added. If architectural decisions were made this session, verify `journal/DECISIONS.md` has been updated too.

2. Stage specific files by name. Never use `git add -A` or `git add .` — inspect what is being staged and confirm no `.env`, credentials, or secrets are included.

3. Draft a conventional commit message:
   - `feat(FX):` new capability tied to a feature ID
   - `fix:` bug fix
   - `refactor:` restructuring without behaviour change
   - `test:` adding or updating tests
   - `docs:` documentation only
   - `chore:` tooling, config, dependencies
   - Subject line: imperative mood, ≤72 characters, no trailing period
   - Body (optional): explain the why, not the what

4. Show the staged file list and commit message to the user and wait for explicit approval before running `git commit`.

5. Never use `--no-verify`. Pre-commit hooks are the quality gate — if a hook fails, fix the underlying issue and retry. Never bypass.

6. Never amend a commit that has already been pushed.
