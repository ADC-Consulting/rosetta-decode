---
name: test-runner
description: Run the full test suite via `make test`, interpret results, and act on failures. Always use this instead of calling pytest directly.
---

## Use for

- Running the full test suite at any point during a session
- Verifying that code changes don't break existing tests
- Quick sanity check before invoking `git-committer`

## Do NOT use for

- Committing code (use `git-committer`)
- Fixing failing tests — surface failures only, then stop

## How to run

```
make test
```

Never call `uv run pytest`, `pytest`, or any other direct invocation — Critical Rule in `CLAUDE.md`.

## What to expect from the output

`make test` runs seven sequential gates wrapped in `run_quiet`. It **short-circuits** on the first failure — later gates do not run.

- **Green gate:** prints only `✓ <gate-name>`. No pass counts, no coverage %, no per-test lines.
- **Failing gate:** dumps its full output, then `make` exits. Subsequent gates are skipped.

Gates in order: `ruff-check` → `ruff-format` → `mypy` → `pytest+coverage` → `tsc` → `frontend-lint` → `frontend-build`

Coverage is enforced automatically via `--cov-fail-under=90`; no separate check is needed.

## Interpreting results

**Green run** — all seven `✓` lines present:

- Report the gate list as confirmation; verdict: **GREEN**.

**Red run** — one gate failed:

- Report: which gate failed, the exact error output (quoted), and which gates did not run.
- Do not attempt fixes; surface the information and stop. Verdict: **RED**.

## Iterative fix cycle

Work through failures one gate at a time — never try to fix everything in a single pass:

1. Run `make test`. Report the first failing gate and its errors.
2. Stop. Let the appropriate agent fix those errors.
3. Re-run `make test`. Confirm the gate now passes, then handle the next failure.
4. Repeat until all seven `✓` lines appear.

Because `make test` short-circuits, you will only ever see one gate's failures at a time. This is by design — use it to keep fixes focused and incremental.

## Alternate targets

| Target                                  | When to use                                              |
| --------------------------------------- | -------------------------------------------------------- |
| `make test-fast`                        | Skip `reconciliation`, `cloud`, `integration` markers    |
| `make test-reconciliation`              | Reconciliation tests only (requires Postgres)            |
| `make coverage`                         | Verbose term output + HTML report → `htmlcov/index.html` |
| `make test-file FILE=tests/test_foo.py` | Single test file                                         |
