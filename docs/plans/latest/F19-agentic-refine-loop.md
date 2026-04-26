# F19 — Agentic Execute-and-Refine Loop

**Phase:** 2  
**Area:** Backend / Worker  
**Status:** in-progress

## Goal

After the initial translation of each block, execute the generated code and reconcile it. If reconciliation fails, pass the failure context (error message + diff summary) back to the originating translation agent and retry — up to 3 attempts per block. Structured log lines announce which agent is running and which attempt number it is, without leaking LLM prompt content to the log.

This replaces the current two-phase whole-job retry (Phase 1: translate all, Phase 2: re-translate one block via FailureInterpreterAgent) with a per-block execute→refine loop that runs before assembly, giving the LLM precise per-block feedback.

## Acceptance Criteria

- [ ] Each block is executed and reconciled immediately after translation (per-block recon)
- [ ] On failure, the agent retries up to 3 times with the error + diff summary injected into context
- [ ] Attempt 4 (if still failing) uses the last generated code as-is
- [ ] Log lines follow the format: `[F19] <AgentName> block <id> attempt <n>/3`  — no prompt content
- [ ] The existing whole-job Phase 2 retry (FailureInterpreterAgent) is preserved as a final fallback after all blocks are assembled
- [ ] `make test` exits 0

## Subtasks

### S1: Per-block executor helper
**File:** `src/worker/engine/block_executor.py`  
**Depends on:** none  
**Done when:** `BlockExecutor.run(python_code, block_id, backend) -> ReconResult | None` exists — executes a code snippet wrapping just that block's function and returns a pass/fail result; returns `None` if no reference data available.  
- [ ] done

### S2: Refine-loop in `_translate_blocks`
**File:** `src/worker/main.py`  
**Depends on:** S1  
**Done when:** `_translate_blocks` wraps each block in a `for attempt in range(1, 4)` loop — translates, executes via `BlockExecutor`, breaks on pass, otherwise injects `recon_failure_hint` into `risk_flags` and retries. Structured log line emitted at start of each attempt.  
- [ ] done

### S3: Structured attempt logging
**File:** `src/worker/main.py`  
**Depends on:** S2  
**Done when:** Every translation attempt logs exactly: `[F19] <AgentClassName> block <source_file>:<start_line> attempt <n>/3` at INFO level. No LLM prompt content, no diff text in log.  
- [ ] done

### S4: Unit tests
**File:** `tests/test_refine_loop.py`  
**Depends on:** S2  
**Done when:** Tests cover: (a) block passes on first attempt — no retry; (b) block fails twice then passes on attempt 3; (c) block fails all 3 — last code used; (d) log lines match expected format.  
- [ ] done

### S5: `make test` green
**Depends on:** S4  
**Done when:** `make test` exits 0 with all gates passing.  
- [ ] done

## Key files

| File | Role |
|---|---|
| `src/worker/main.py` (lines 627-658) | `_translate_blocks` — where the loop lives |
| `src/worker/main.py` (lines 560-625) | `_translate_with_reconciliation` — whole-job recon, preserved |
| `src/worker/engine/router.py` | Routes block → agent; agent class name available via `type(translator).__name__` |
| `src/worker/engine/agents/generic_proc.py` | `GenericProcAgent.translate(block, context)` |
| `src/worker/engine/agents/data_step.py` | `DataStepAgent.translate(block, context)` |
| `src/worker/engine/agents/proc.py` | `ProcAgent.translate(block, context)` |
| `src/worker/validation/reconciliation.py` | `ReconciliationService.run(ref_csv, code, backend, ref_sas7bdat)` |
| `src/worker/engine/models.py` | `JobContext.risk_flags` — where failure hint is injected |

## Implementation notes

- Inject failure context as a new `risk_flags` entry: `"recon_failure_attempt_<n>: <error_summary>"` — one sentence max, no stack traces
- `BlockExecutor` wraps the single block's code in a minimal harness; if no reference data is present it returns `None` (no-op, loop proceeds as pass)
- Agent class name for logging: `type(translator).__name__` on the routed translator
- Log format must be a single `logger.info` call — not assembled from f-string with diff content

## Out of scope

- UI changes (recon attempt count is not surfaced in the UI for this feature)
- Changing the whole-job Phase 2 FailureInterpreterAgent retry — it stays as-is
- Per-block recon when no reference data is provided — graceful no-op
