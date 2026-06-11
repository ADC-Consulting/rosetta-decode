# F31 — Missing Dependencies Callout on Plan Tab

**Phase:** 2
**Area:** Both (Backend / Worker + Frontend)
**Status:** complete
**GitHub issue:** #61

## Goal

Detect SAS macro calls and `%INCLUDE` references in uploaded code that have no matching definition or uploaded file, store the findings on the job, expose via the plan API, and render an elevated amber callout on the Plan tab. Silently missing dependencies degrade translation quality — surfacing them prompts users to re-upload before accepting.

## Acceptance Criteria

- [ ] `MissingDependency` typed model defined in `models.py`
- [ ] Macro invocations extracted using an allowlist approach (not built-in exclusion blocklist)
- [ ] Missing macro names and missing include paths detected and stored on `MigrationPlan`
- [ ] `GET /jobs/{id}/plan` exposes `missing_dependencies` on `JobPlanResponse`
- [ ] Plan tab shows amber callout when `missing_dependencies` is non-empty
- [ ] Unit tests for `detect_missing_dependencies()` function
- [ ] `make test` exits 0

## Subtasks

### S-A: Define MissingDependency typed model
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** A `MissingDependency` Pydantic model is defined with fields `name: str`, `type: Literal["macro", "include"]`, `reference_count: int`; and `MigrationPlan` has `missing_dependencies: list[MissingDependency] = Field(default_factory=list)`
- [x] done

### S-B: Create dependency checker with allowlist macro detection
**File:** `src/worker/engine/dependency_checker.py` (new file)
**Depends on:** S-A
**Done when:** A function `detect_missing_dependencies(parse_result: ParseResult, files: dict[str, str]) -> list[MissingDependency]` is implemented; macro detection uses an **allowlist approach**: extract all `%word` tokens from SAS source, then KEEP only those where `word` does not appear in a comprehensive SAS built-in list — this is safer than a blocklist because new user macros are unknown; the built-in list covers: all `%` statement keywords (`let`, `if`, `do`, `end`, `then`, `else`, `put`, `global`, `local`, `macro`, `mend`, `include`, `return`, `abort`, `goto`, `to`, `by`, `while`, `until`) AND common SAS macro functions (`str`, `nrstr`, `eval`, `nreval`, `sysevalf`, `sysfunc`, `nrsysfunc`, `qsysfunc`, `scan`, `qscan`, `substr`, `qsubstr`, `index`, `length`, `trim`, `left`, `right`, `compress`, `tranwrd`, `datatyp`, `verify`, `upcase`, `lowcase`, `quote`, `nrquote`, `bquote`, `nrbquote`, `superq`, `unquote`); remaining `%word` tokens that are NOT in `parse_result.macro_defs` names are flagged as missing macros with their occurrence count; for includes: compare paths from `parse_result.includes` against `files.keys()` using basename comparison (strip directory and drive prefix from both sides) to handle absolute vs relative path mismatch; paths containing macro variable references (e.g. `&path`) are skipped rather than flagged (unresolvable at static analysis time); unit tests cover: user macro detected, built-in not flagged, include found, include missing, macro-variable include skipped
- [x] done

### S-C: Add missing_dependencies to MigrationPlan model
**Done when:** Already covered by S-A (`MigrationPlan` field added there)
- [x] done

### S-D: Call dependency checker in worker pipeline
**File:** `src/worker/main.py`
**Depends on:** S-B
**Done when:** `detect_missing_dependencies(parse_result, files)` is called after `SASParser().parse(files)` returns AND after `MigrationPlannerAgent` has constructed the `MigrationPlan` object (so the plan exists to attach findings to); result assigned to `context.migration_plan.missing_dependencies` before `job.migration_plan` is persisted; if `MigrationPlannerAgent` fails gracefully and `context.migration_plan` is None, findings are skipped without crashing
- [x] done

### S-E: Add missing_dependencies to JobPlanResponse API schema
**File:** `src/backend/api/schemas.py`
**Depends on:** S-A
**Done when:** `JobPlanResponse` has `missing_dependencies: list[MissingDependency] = []`; `MissingDependency` imported from worker models or duplicated as a matching Pydantic model in `schemas.py` (prefer duplication to avoid cross-service import)
- [x] done

### S-F: Update JobPlanResponse TypeScript type
**File:** `src/frontend/src/api/types.ts`
**Depends on:** S-E
**Done when:** `JobPlanResponse` interface has `missing_dependencies?: Array<{name: string; type: "macro" | "include"; reference_count: number}>`
- [x] done

### S-G: Render missing dependencies callout on Plan tab
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-F
**Done when:** An amber callout card renders between the metrics card and the verdict strip when `planData.missing_dependencies` is non-empty; lists each item as `macroname (macro, N calls)` or `path/file.sas (include, N refs)`; shows first 3 with "+ N more" if list is long; hidden when list is empty
- [x] done

### S-H: make test exits 0
**Depends on:** S-A through S-G
**Done when:** All 7 gates green; unit tests for `detect_missing_dependencies` passing
- [x] done

## Known limitation

Existing jobs in the database will not have `missing_dependencies` populated. Only jobs parsed after this feature ships will have the data.

## Dependencies on other features

- Merge after F30 (shares `models.py`, `schemas.py`, `types.ts`)
- Merge before F32

## Out of scope

- Auto-resolution or download of missing files
- Alembic migration (stored in existing `job.migration_plan` JSON column)
