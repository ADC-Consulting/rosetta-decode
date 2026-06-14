# F57 — Macro Call Expansion (%MACRO/%MEND)

**Phase:** 2
**Area:** Backend / Worker
**Status:** done

## Goal

SAS macro **calls** (e.g. `%m_first_dose(in=sdtm.ex, out=work.dose)`) are currently never
expanded. The parser stores macro **definitions** (`_extract_macro_defs`) but the call sites
are ignored, so datasets produced *inside* a macro body (`work.dose`) are never created. A
downstream `proc sort data=work.dose` then translates to `dose = dose.orderBy(...)` and crashes
with `NameError: name 'dose' is not defined`.

This feature adds **deterministic textual expansion of control-flow-free macro calls**: look up
the called macro's definition, bind call arguments (keyword + positional, honouring declared
defaults) to its parameters, substitute `&param` references in the body, and inline the
substituted body into the source *before* block extraction — so the existing extractors produce
real blocks for the macro's contents. Macros containing macro **control flow** (`%if`, `%do`,
`%while`, `%let`, `%global`, `%return`) are out of scope and left unexpanded (they need macro-logic
evaluation, a separate feature). Done = the `sas_pharma_sandbox` pipeline produces a block that
creates `work.dose`, and the `dose` NameError is gone.

## Acceptance Criteria

- [ ] `%m_first_dose(in=sdtm.ex, out=work.dose)` expands to a PROC SQL block whose output dataset is `work.dose`
- [ ] Keyword args (`in=`, `out=`), positional args, and declared defaults (`by=USUBJID`) all bind correctly
- [ ] Macros containing `%if`/`%do`/`%while`/`%let`/`%global`/`%return` are left unexpanded (no partial/incorrect inlining)
- [ ] Nested macro calls expand to a fixed point, with a recursion-depth guard against cycles
- [ ] Expansion is deterministic: identical SAS input → identical expanded source → identical blocks
- [ ] Expanded blocks carry provenance pointing back to the macro definition
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Subtasks

### S-A: macro signature + call-argument parsing helpers
**File:** `src/worker/engine/macro_call_expander.py` (new)
**Depends on:** none
**Done when:** pure functions exist to (1) parse a macro param declaration string into `[(name, default)]` (handles `in=`, `out=`, `by=USUBJID`, bare positional), and (2) parse a call-arg string into `(positional: list[str], keyword: dict[str, str])`.
- [x] done

### S-B: expandability guard
**File:** `src/worker/engine/macro_call_expander.py`
**Depends on:** none
**Done when:** `_is_expandable(body: str) -> bool` returns `False` when the macro body contains any of `%if %do %while %let %global %return %end` (case-insensitive, word-boundary), else `True`.
- [x] done

### S-C: core `expand_macro_calls(source, macro_defs)`
**File:** `src/worker/engine/macro_call_expander.py`
**Depends on:** S-A, S-B
**Done when:** given a source string and the collected `MacroDef`s, every expandable `%name(args);` call is replaced inline by its substituted body (defaults ⊕ bound args → `var_map`, then reuse `macro_expander._substitute_let_vars`); non-expandable or unknown macros are left untouched; expansion iterates to a fixed point with a max-depth guard (e.g. 10) to break cycles; each inlined body is prefixed with a provenance marker comment (`/* SAS-MACRO-EXPANDED: <name> from <file>:<line> */`). Pure and deterministic.
- [x] done

### S-D: wire two-pass expansion into `SASParser.parse`
**File:** `src/worker/engine/parser.py`
**Depends on:** S-C
**Done when:** `parse` is restructured to (pass 1) collect `macro_defs` across **all** input files first (so calls in `05_*.sas` can resolve defs from `%include`d `macros/*.sas`), then (pass 2) run `expand_macro_calls` on each file's source before comment-stripping/extraction. Existing extractor and topo-sort flow is otherwise unchanged.
- [x] done

### S-E: unit tests for parsing + expansion
**File:** `tests/test_macro_call_expander.py` (new)
**Depends on:** S-C
**Done when:** tests cover signature parsing (defaults, keyword, positional), arg parsing, `_is_expandable` (skips `%if`/`%let` macros), keyword+default binding, fixed-point/nested expansion, depth-guard on a cycle, and that `%m_first_dose(in=sdtm.ex, out=work.dose)` yields PROC SQL text creating `work.dose`.
- [x] done

### S-F: reconciliation/integration test through the parser
**File:** `tests/reconciliation/test_macro_expansion.py` (new)
**Depends on:** S-D
**Done when:** feeding a minimal multi-file fixture (a `macros/*.sas` def + a caller with `%call(...)` then `proc sort data=<macro output>`) through `SASParser.parse` yields a block whose `output_datasets` contains the macro-produced dataset, and the producer is ordered before the consumer by topo sort. Asserts the `dose` NameError class is resolved.
- [x] done

### S-G: full suite green
**File:** n/a
**Depends on:** S-E, S-F
**Done when:** `make test` exits 0 with all gates green.
- [x] done

## Dependencies on other features

- none — reuses `macro_expander._substitute_let_vars`, the existing `MacroDef` model, and all block extractors as-is

## Out of scope for this feature

- Macro **control flow** evaluation: `%if`/`%else`/`%do`/`%while`/`%return` (e.g. `m_derive_age_group`, `m_safety_flag`) — left unexpanded, deferred to a macro-logic resolver feature
- Macros that write to the caller's scope via `%let`/`%global` (`m_safety_flag` SAFETY_RESULT pattern)
- `_ProcSortHelper` hygiene (`output_var` + normalizer) — tracked separately
- Any API, schema, or frontend changes
