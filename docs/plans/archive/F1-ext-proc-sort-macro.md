# F1 Extension — PROC SORT + %LET Macro Variable Resolution

**Phase:** 2
**Area:** Backend / Worker
**Feature:** F1 extension (Phase 2 — post-MVP backend extension)
**Status:** complete

## Goal

Extend the migration engine to recognise `PROC SORT` blocks and `%LET` macro variable
declarations. PROC SORT blocks are extracted with correct `DATA=`/`OUT=` dataset resolution
and routed through the existing LLM → codegen pipeline, producing `sort_values()` (pandas)
or `orderBy()` (PySpark). `%LET` declarations are extracted as module-level Python constants
and prepended to the generated pipeline by `CodeGenerator`. Previously both constructs were
either silently ignored or flagged as `UNTRANSLATABLE`.

## Acceptance Criteria

- [x] `BlockType.PROC_SORT` exists in `models.py`
- [x] `MacroVar` and `ParseResult` models exist in `models.py`
- [x] `SASParser.parse()` returns `ParseResult(blocks, macro_vars)`
- [x] `SASParser.parse()` extracts `PROC SORT` blocks with correct `input_datasets`, `output_datasets`, `start_line`, `end_line`
- [x] `PROC SORT` blocks are no longer emitted as `UNTRANSLATABLE`
- [x] `%LET` declarations extracted as `MacroVar` entries with name uppercased
- [x] `CodeGenerator.assemble()` accepts `macro_vars` and prepends a constants section
- [x] Sample SAS file `samples/proc_sort_example.sas` exists (DATA step + 2 PROC SORT variants + 1 %LET)
- [x] `samples/proc_sort_expected.csv` exists as reconciliation reference
- [x] Parser unit tests cover: basic BY, DESCENDING, OUT= present, OUT= absent, %LET extraction
- [x] Reconciliation test in `tests/reconciliation/test_proc_sort.py` passes
- [x] `make test` exits 0, coverage ≥ 90%

## Subtasks

### S01: add `PROC_SORT` to `BlockType`, `MacroVar`, `ParseResult` to `models.py`
**File:** `src/worker/engine/models.py`
- [x] done

### S02: add sample SAS file + expected CSV
**Files:** `samples/proc_sort_example.sas`, `samples/proc_sort_expected.csv`
- [x] done

### S03: add PROC SORT + %LET extractors to `parser.py`; change `parse()` to return `ParseResult`
**File:** `src/worker/engine/parser.py`
- [x] done

### S04: update all `parse()` call sites
**Files:** `src/worker/main.py`, `tests/test_parser.py`
- [x] done

### S05: extend `CodeGenerator.assemble()` with `macro_vars` parameter
**File:** `src/worker/engine/codegen.py`
- [x] done

### S06: parser unit tests — PROC SORT + %LET
**File:** `tests/test_parser.py`
- [x] done

### S07: codegen unit tests for `macro_vars`
**File:** `tests/test_codegen.py`
- [x] done

### S08: reconciliation test — PROC SORT
**File:** `tests/reconciliation/test_proc_sort.py`
- [x] done

### S09: `make test` green — full suite + coverage gate
- [x] done (78 tests passing, 93.53% coverage)

## Dependencies on other features

- F1 complete (parser, LLMClient, CodeGenerator, ReconciliationService all in place) ✓

## Out of scope for this feature

- `PROC SORT NODUPKEY` / `DUPKEY` deduplication options
- `WHERE=` dataset option on PROC SORT
- `%MACRO` / `%MEND` macro definition and call expansion (separate backlog item)
- `&varname` substitution in raw SAS before LLM call (LLM handles via pattern catalog)
