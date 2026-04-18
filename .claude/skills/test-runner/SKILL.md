---
name: test-runner
description: Run the full test suite via `make test`, interpret results, and act on failures. Always use this instead of calling pytest directly.
---

## Use for
- Running the full test suite at any point during a session
- Verifying that code changes don't break existing tests
- Checking coverage after new code is written
- Quick sanity check before invoking `git-committer`

## Do NOT use for
- Running a single test file in isolation (use `make test` — it always runs the full suite)
- Committing code (use `git-committer`)
- Fixing failing tests — this skill only surfaces failures; fix them then re-run

## Steps (run IN ORDER)

1. **Run `make test`.** This is the ONLY valid way to run tests. Never call `uv run pytest` or `pytest` directly — this is a Critical Rule in `CLAUDE.md`.

2. **Read the output.** Note:
   - Total passed / failed / error count
   - Coverage percentage (shown by `--cov-report=term-missing`)
   - Any missing-coverage lines flagged in the report

3. **If all tests pass:**
   - Report the pass count and coverage % to the user
   - Flag any coverage gaps (uncovered lines) that relate to recently changed files
   - If coverage is below `fail_under` in `pyproject.toml`, note it explicitly

4. **If tests fail:**
   - Identify the failing test(s) by name and file path
   - Quote the assertion error or exception message
   - Do NOT attempt to fix failures automatically — surface the information clearly, then wait for the user to direct next steps
   - Exception: if the failure is clearly caused by a missing import or trivial typo introduced in the current session, fix it and re-run once

5. **Slow-test variants (use only when the user asks):**
   - `make test-fast` — skips `reconciliation`, `cloud`, and `integration` markers; faster feedback loop
   - `make test-reconciliation` — runs only reconciliation tests; requires Postgres running
   - `make coverage` — generates HTML report in `htmlcov/`; tell the user to open `htmlcov/index.html`
