# F27 — Trust Report Bug Fixes

**Phase:** 3
**Area:** Backend / API + Frontend
**Status:** in-progress

## Goal

Fix three bugs in the trust report that cause the Evaluation tab to display misleading data. `auto_verified` is always 0 because the condition requires reconciliation to have run, which it never does without a reference CSV. `needs_attention` misses `translated_with_review` blocks whose confidence is medium or high, silently dropping planner-flagged blocks from the review queue. `translate_best_effort` is a dead enum value that the LLM never assigns, cluttering the schema and frontend label map. When done, the Evaluation tab accurately reflects block status for all jobs, including those without reference CSVs.

## Acceptance Criteria

- [ ] `auto_verified` counts blocks with high/medium confidence and no reconciliation failure (not just recon pass)
- [ ] `needs_attention` flags all `translated_with_review` blocks regardless of confidence band
- [ ] `translate_best_effort` removed from backend enum, schemas, and frontend label map
- [ ] Existing trust report tests updated to match corrected logic
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Subtasks

### S-A: Fix `auto_verified` counter
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** none
**Done when:** both `auto_verified` sum expressions (job-level line ~2003, file-level line ~1849) use `reconciliation_status != "fail"` instead of `reconciliation_status == "pass"`, with confidence band check unchanged

- [ ] done

### S-B: Fix `needs_attention` condition
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** none
**Done when:** `needs_attention` also triggers when `strategy == "translated_with_review"`, so planner-flagged blocks always appear in the review queue

- [ ] done

### S-C: Remove `translate_best_effort` from backend
**Files:** `src/worker/engine/models.py`, `src/backend/api/schemas.py`
**Depends on:** none
**Done when:** `TRANSLATE_BEST_EFFORT` removed from `TranslationStrategy` enum; `"translate_best_effort"` removed from the allowed strategy list in `schemas.py`; router comment updated

- [ ] done

### S-D: Remove `translate_best_effort` from frontend
**File:** `src/frontend/src/components/LiveTraceDialog.tsx`
**Depends on:** S-C
**Done when:** `translate_best_effort: "Best-effort"` entry removed from the strategy label map

- [ ] done

### S-E: Update tests
**File:** `tests/test_changelog_trust_report.py`
**Depends on:** S-A, S-B
**Done when:** test cases for `auto_verified` and `needs_attention` reflect the corrected logic; any test asserting `auto_verified == 0` on a job without ref CSV is updated to expect a non-zero count where confidence is high/medium

- [ ] done

### S-F: `make test` exits 0
**Depends on:** S-A, S-B, S-C, S-D, S-E
**Done when:** ruff, mypy, tsc, frontend-lint, frontend-build, and pytest all pass

- [ ] done

## Dependencies on other features

- none

## Out of scope for this feature

- Adding `translate_best_effort` to agent prompts as a live strategy
- Changing how `criticality` or `human_review_required` are computed
- Row-level reconciliation (F15)
- Any changes to how `reconciliation_status` is written by the worker
