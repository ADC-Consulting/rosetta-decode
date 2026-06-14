# F60 — PROC FORMAT Translation (user formats → when/otherwise)

**Phase:** 2
**Area:** Backend / Worker
**Status:** complete (committed 256ee51; end-to-end sandbox evidence outstanding)

## Goal

User-defined SAS formats (`PROC FORMAT; value name ...;`) are parsed into `PROC_FORMAT`
blocks but their value mappings are discarded — only `raw_sas` is kept. So when a DATA/PROC
block calls `put(var, customfmt.)`, the translating agent has no definition of `customfmt`,
cannot render it, and the derived column is dropped — a later reference then crashes with
`UNRESOLVED_COLUMN`. F60 closes this gap: **deterministically extract PROC FORMAT `value`
maps into a structured catalog, carry it on `ParseResult`/`JobContext` (like `libname_map`),
and inject the referenced format definitions into the translation agents' prompts** so the
LLM renders `put(var, fmt.)` as a `F.when(...).otherwise(...)` chain. Catalog extraction is
deterministic and unit-tested; application is via the existing LLM agents (the locked primary
translation engine). Done = a block using `put(var, customfmt.)` receives the format's
definition in its prompt and the catalog is correctly extracted for ranges, `$char`, and `other`.

## Acceptance Criteria

- [ ] PROC FORMAT `value` blocks extracted into a catalog: numeric ranges (`a - b`, `a -< b`, `low`, `high`), single values, `$char` formats, and `other`
- [ ] Catalog carried on `ParseResult` and `JobContext`, threaded through `windowed_context`
- [ ] A DATA/PROC block calling `put(var, fmt.)` has the matching format definition injected into its prompt, plus a rule instructing `put()` → `when/otherwise`
- [ ] **A DATA step containing a `put()` assignment routes to `DataStepAgent`, NOT `_SimpleCopyHelper`** (see S-E0 — without this the prompt injection never runs for the triggering block)
- [ ] Format name matching is normalization-correct: detection from `put(var, fmt.)` matches catalog keys across optional width suffix (`agegr1f8.`) and `$`-prefixed char formats (`$sexdec.`)
- [ ] Format definitions resolve across files (format defined in one file, `put()` used in another)
- [ ] Catalog extraction is deterministic and unit-tested (ranges, `$char`, `other`, multiple `value` blocks, multiple formats); detection tests include width-suffixed + `$`-prefixed references
- [ ] The new `put()` rule does NOT regress built-in formats (`put(x, dollar8.)`, `put(date, date9.)`) — rule is scoped to "when a definition is supplied"
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

> **Validation note (2026-06-14):** plan reviewed against code + the real triggering scenario
> (`m_derive_age_group.sas` → `agegr1f`). Structurally sound, but the original plan omitted the
> router layer: the bug's own block (`AGEGR1 = put(AGE, agegr1f.)` with `set`+`length`, no
> `IF/DO/MERGE/RETAIN/ARRAY/OUTPUT`) is classified `_SimpleCopyHelper.is_simple()==True` and
> diverted to the no-LLM copy path that drops the assignment — so prompt injection alone does
> not fix it. S-E0 (router guard) is now the dependency that makes the rest meaningful.

## Design

Mirror the `libname_map` pattern (confirmed in current code):
- **Extract** in a new pure module `src/worker/engine/format_catalog.py`; call it from `SASParser.parse`.
- **Store** a `format_catalog: dict[str, FormatDef]` on `ParseResult` and `JobContext`; pass it through `JobContext.windowed_context` (like `libname_map`).
- **Inject** in each agent's `_build_prompt` — a new "## Available SAS formats" section listing only the formats the block's `raw_sas` references via `put(..., <name>.)`, plus a shared rule in `SHARED_TRANSLATION_RULES`.

Application is LLM-driven (no deterministic `put()→when/otherwise` codegen) — consistent with
DECISIONS (LLM is the primary, mandatory translation engine). End-to-end column creation is
verified manually against the sandbox; automated tests cover the deterministic catalog + the
prompt-injection wiring (the LLM rendering itself is not unit-tested).

## Subtasks

### S-A: format-catalog data model
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** `FormatEntry` and `FormatDef` Pydantic models exist (entry captures single value / range with low/high + exclusive-upper / `other`, plus label; def has `name`, `is_char`, `entries`), and a `format_catalog: dict[str, FormatDef]` field is added to both `ParseResult` and `JobContext` with `windowed_context` passing it through.
- [x] done

### S-B: deterministic PROC FORMAT extractor
**File:** `src/worker/engine/format_catalog.py` (new)
**Depends on:** S-A
**Done when:** `extract_format_catalog(source: str) -> dict[str, FormatDef]` parses every `proc format ... run;` block's `value`/`value $` statements into `FormatDef`s — handling single values (`1='Mild'`), ranges (`18 -< 65`, `75 - high`, `low - 18`), quoted/unquoted operands, and `other='...'`; malformed/unsupported entries are skipped (catalog stays partial, never raises). Catalog **keys** use a normalized format name (lowercased; `$`-prefix preserved for char formats) via a single shared `normalize_format_name()` helper reused by S-E detection.
- [x] done

### S-E0: router guard — don't divert `put()` DATA steps to the no-LLM copy path
**File:** `src/worker/engine/router.py`, `tests/test_router.py` (or existing router test)
**Depends on:** none
**Done when:** `_SimpleCopyHelper.is_simple()` returns `False` when the DATA step body contains an assignment statement / `put(` / anything beyond `SET`/`KEEP`/`DROP` (plus `DATA`/`RUN`) — currently it only checks for absence of `IF/DO/MERGE/RETAIN/ARRAY/OUTPUT`, so `AGEGR1 = put(AGE, agegr1f.)` is wrongly classified "simple" and the assignment is dropped. A unit test asserts a `put()`-bearing DATA step routes to `DataStepAgent`, not `_SimpleCopyHelper`. **This is the dependency that makes S-E meaningful for the triggering block.**
- [x] done — `is_simple` rewritten to a positive allowlist (only `DATA`/`SET`/`KEEP`/`DROP`/`RUN`); 3 router tests added; `make test` green.

### S-C: unit tests for the extractor
**File:** `tests/test_format_catalog.py` (new)
**Depends on:** S-B
**Done when:** tests cover numeric ranges (incl. `low`/`high`/`-<`), `$char` formats, `other`, multiple `value` blocks in one PROC FORMAT, multiple PROC FORMAT blocks, and the real `agegr1f`/`$sexdec`/`aegrf` fixtures from `pharma_formats.sas`.
- [x] done

### S-D: wire extraction into the parser + JobContext
**File:** `src/worker/engine/parser.py`, `src/worker/main.py`
**Depends on:** S-B
**Done when:** `SASParser.parse` calls `extract_format_catalog` on the per-file **`expanded_source`** (post macro-expansion, mirroring `_extract_libnames(expanded_source)` at parser.py:877 — NOT raw `source`, else macro-defined formats are missed) and populates `ParseResult.format_catalog` (collected across all files). `main.py` threads it into `JobContext` via the existing `.model_copy(update={...})` — sourced from **`parse_result.format_catalog`** (NOT re-grepped; unlike `libname_map`, which main.py independently regexes at lines 487–495, there is no regex shortcut for format bodies).
- [x] done

### S-E: inject formats into agent prompts
**File:** `src/worker/engine/agents/shared.py`, `data_step.py`, `proc.py`, `generic_proc.py`
**Depends on:** S-A
**Done when:** a shared helper detects referenced format names from `put(..., <name>.)` in `raw_sas` (using `normalize_format_name()` from S-B; tolerates optional width suffix like `agegr1f8.` and `$`-prefixed char formats like `$sexdec.`), renders the matching `format_catalog` definitions into a `## Available SAS formats` prompt section (conditional, like the existing `## Uploaded data files` section in `generic_proc.py`), each agent's `_build_prompt` includes it, and `SHARED_TRANSLATION_RULES` gains a **scoped** rule: *when a format definition is supplied in the 'Available SAS formats' section*, translate `put(var, fmt.)` using it into `F.when(...).otherwise(...)` (or broadcast lookup), preserving the column; *otherwise treat `fmt` as a built-in* (cross-reference date/numeric rules #10–12) so `put(x, dollar8.)`/`put(date, date9.)` are not regressed.
- [x] done

### S-F: tests for wiring + prompt injection
**File:** `tests/test_format_catalog.py` (extend), agent prompt test (e.g. `tests/test_data_step_agent.py` or new)
**Depends on:** S-D, S-E, S-E0
**Done when:** a test asserts `SASParser.parse` on a multi-file fixture (format defined in file A, `put()` used in file B) populates `format_catalog`; a prompt-builder test asserts a block calling `put(var, fmt.)` yields a prompt containing that format's definition and the `put()` rule, **including a width-suffixed reference and a `$`-prefixed char-format reference** (not just bare `fmt.`); and an integration test parses `m_derive_age_group` + `pharma_formats.sas` through the parser and asserts the `put()`-bearing block reaches `DataStepAgent` (not `_SimpleCopyHelper`) with `agegr1f` in `format_catalog`. End-to-end column survival (`agegr1` produced, no `UNRESOLVED_COLUMN`) is captured as a **documented sandbox-run artefact pasted into this plan at close** — not an untracked "verified manually" (LLM render is non-deterministic, so it is not unit-asserted).
- [x] done

### S-G: full suite green
**File:** n/a
**Depends on:** S-C, S-E0, S-F
**Done when:** `make test` exits 0 with all gates green.
- [x] done

## Dependencies on other features

- F57/F59 (macro expansion) — already merged to main; the block that triggers the bug only appears after `m_derive_age_group` expands

## Out of scope for this feature

- Deterministic `put()→when/otherwise` codegen (LLM renders it; a hybrid deterministic path for simple value maps is a possible future enhancement)
- `picture` formats; `informat` / `input(var, fmt.)` parsing
- Cross-format references (`value` whose label references another format)
- SAS built-in/system formats already handled by native casts (dates, `best.`, `z.`, `comma.`)
- Persisting the catalog to the DB (in-memory `JobContext` only, like `libname_map`)
