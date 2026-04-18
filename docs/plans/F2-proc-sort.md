# F2 — PROC SORT Parser and Translation

**Phase:** 2
**Area:** Backend / Worker
**Status:** in-progress

## Goal

Extend the migration engine to recognise `PROC SORT` blocks, extract the sort columns and their direction (`ASC`/`DESCENDING`), and translate them to `sort_values()` (pandas) or `orderBy()` (PySpark) with correct provenance comments. Currently `PROC SORT` falls through to `UNTRANSLATABLE` — after this feature it produces runnable Python and passes reconciliation.

## Acceptance Criteria

- [ ] `BlockType.PROC_SORT` exists in `models.py`
- [ ] `SASParser.parse()` extracts `PROC SORT` blocks with correct `input_datasets`, `output_datasets`, `start_line`, `end_line`
- [ ] `PROC SORT` blocks are no longer emitted as `UNTRANSLATABLE`
- [ ] `LLMClient` translates `PROC SORT` blocks via the existing agent (pattern catalog already covers it)
- [ ] `CodeGenerator` handles `PROC SORT` blocks (no special casing needed — uses same assembly path)
- [ ] A sample SAS file with `PROC SORT` exists in `samples/`
- [ ] Unit tests for the parser cover: basic BY clause, DESCENDING column, OUT= dataset, missing OUT= (in-place sort)
- [ ] Reconciliation test proves pandas output matches expected sorted CSV
- [ ] `make test` exits 0, coverage ≥ 90%

## Subtasks

### S01: add `PROC_SORT` to `BlockType` and update `SASBlock` if needed
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** `BlockType.PROC_SORT` is a valid enum value and `SASBlock` can represent a sort block (no new fields required — `input_datasets`/`output_datasets` already cover `DATA=` and `OUT=`)
- [ ] done

### S02: add PROC SORT extractor to `parser.py`
**File:** `src/worker/engine/parser.py`
**Depends on:** S01
**Done when:** `_extract_proc_sort()` yields `SASBlock(block_type=BlockType.PROC_SORT, ...)` for every `PROC SORT … RUN;` block; PROC SORT spans are added to `covered` so `_extract_unsupported_procs` no longer catches them; `DATA=` → `input_datasets`, `OUT=` → `output_datasets` (falls back to `DATA=` when `OUT=` is absent)
- [ ] done

### S03: add sample SAS file with PROC SORT
**File:** `samples/proc_sort_example.sas` + `samples/proc_sort_expected.csv`
**Depends on:** none
**Done when:** sample file contains at least two PROC SORT variants (basic BY, DESCENDING, OUT= present, OUT= absent); expected CSV reflects the correctly sorted output for the reconciliation test
- [ ] done

### S04: parser unit tests for PROC SORT
**File:** `tests/test_parser.py`
**Depends on:** S02
**Done when:** tests cover: basic single-column sort, multi-column sort with DESCENDING, OUT= extraction, missing OUT= falls back to DATA= as output, PROC SORT block is not emitted as UNTRANSLATABLE
- [ ] done

### S05: reconciliation test — PROC SORT → sorted DataFrame
**File:** `tests/reconciliation/test_proc_sort.py`
**Depends on:** S02, S03
**Done when:** `@pytest.mark.reconciliation` test runs the full pipeline on `proc_sort_example.sas`, executes the generated pandas code via `LocalBackend`, and asserts the output DataFrame matches `proc_sort_expected.csv` (row order, column values)
- [ ] done

### S06: `make test` green — full suite + coverage gate
**Depends on:** S01–S05
**Done when:** `make test` exits 0; overall coverage ≥ 90%; reconciliation coverage on `src/worker/validation` ≥ 80%
- [ ] done

## Dependencies on other features

- F1 complete (parser, LLMClient, CodeGenerator, ReconciliationService all in place) ✓

## Out of scope for this feature

- `PROC SORT NODUPKEY` / `DUPKEY` deduplication options (Phase 2+)
- `WHERE=` dataset option on PROC SORT
- `%LET` macro variable resolution (separate feature)
- PySpark (`orderBy`) codegen — LLMClient handles this via the existing pattern catalog; no engine changes needed
