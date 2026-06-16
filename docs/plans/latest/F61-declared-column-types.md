# F61 — Type-Aware Schema Contract: bake source-declared column types into delivered PySpark

**Phase:** 2
**Area:** Backend / Worker
**Status:** complete (verified end-to-end in sandbox; full-pipeline reconciliation green)
**Depends on:** F57/F59 (macro expansion — merged), F60 (PROC FORMAT catalog — merged)
**Branch:** `feat/F61-declared-column-types` (cut from latest `main`)

## Context

When translating SAS DATA steps, the worker derives output column types from the uploaded
**reference** file (`.sas7bdat`/`.csv`) at runtime rather than from the **SAS-declared** type.
Two failure classes result:

1. **Type drift** — a key like `subjid` declared char (`length SUBJID $10`) in SAS is read as
   `int64` from the reference CSV. Downstream joins compare mismatched types and silently produce
   nulls / zero-row joins.
2. **Null propagation** — a derived column computed from a mis-cast key collapses to null, so
   aggregates go to null/`inf`.

The symptom (discovered during F60 sandbox validation): full-pipeline reconciliation shows
`subjid`/`siteid` with `inf` aggregate parity (all-null in generated output) while **per-block
recon is green** — a misleading false-pass, because per-block tests run against clean reference
input while the full pipeline chains actual DataFrames where the mismatch propagates.

**Root cause:** there is no mechanism to capture the declared type and bake it into delivered code;
types are inferred at runtime from reference data, which may differ from the SAS declaration.

**Fix (decided 2026-06-14, this session):** capture declared types from `.sas7bdat` metadata via
pyreadstat at parse time, surface them on `DataFileInfo.column_types`, and bake explicit
`.cast(...)` calls into delivered PySpark — sourced from the **declared** type, never the reference
schema (respects the existing "never cast to match ref" rule). Two complementary mechanisms
(refined from the user's "both" choice — see note):
- **Deterministic injector** (the guarantee, and the *sole author* of the load-time cast) — a regex
  post-processor in the mold of `normalise_output_var_in_code` that adds the cast after the
  lowercase-normalization line. Makes the cast + provenance comment a hard, unit-assertable,
  byte-reproducible invariant.
- **Informational prompt section** (the nudge, consistency with the locked "LLM is primary engine"
  decision) — a per-block `## Declared source column types` section telling the LLM the declared
  types so it makes correct *translation decisions* (treat `subjid` as a string key; don't compare a
  char key to a numeric literal; pick join/filter logic accordingly). It explicitly instructs the LLM
  **not** to hand-write the load-time cast — that is injected automatically.

> **Refinement note (challenged from literal "both"):** the original "both" had the injector *and*
> the LLM each emit the load cast. That risks duplicate casts or an LLM cast placed *after* a join
> (where the null propagation has already happened, defeating the fix), which the idempotence guard
> can't dedupe, and forces contradictory edits to rules 1/5/8. Making the prompt section
> informational (LLM uses types for decisions, injector owns the cast) keeps a single deterministic
> author, removes the rule-1 contradiction, and still gives the LLM the type context. This is faithful
> to "both" — both mechanisms ship — while removing the part that doesn't make sense.
> **Cast ordering (decided):** deterministic injector owns the cast outright; the LLM never authors
> the load cast and there is no LLM fallback path (chosen for byte-reproducibility over edge-case coverage).

## Key code facts (verified during exploration)

- `DataFileInfo`: [models.py:432-448](src/worker/engine/models.py#L432) — only `columns` + `row_count`; **no types**.
- `_sniff_file`: [main.py:63-102](src/worker/main.py#L63) — for `.sas7bdat` returns only `list(meta.column_names)` (line 96). The `meta` object also exposes `meta.readstat_variable_types` (varname → `"string"`/`"double"`), the authoritative char-vs-numeric class. (`original_variable_types` returns SAS format tokens like `$10`/`BEST12.` — **not** used.)
- Data-file catalog built at [main.py:411-442](src/worker/main.py#L411); threaded to `JobContext` at [main.py:498-507](src/worker/main.py#L498); reaches agents via `JobContext.windowed_context` ([models.py:489-504](src/worker/engine/models.py#L489)) which already forwards `data_files` unchanged — **no edit needed there**.
- Deterministic post-processing pattern to extend: `normalise_output_var_in_code` ([shared.py:669-708](src/worker/engine/agents/shared.py#L669)), `normalise_input_vars_in_code` (579-637); generic_proc regex helpers `_fix_excel_spark_reads`/`_fix_workspace_paths` ([generic_proc.py:40-85](src/worker/engine/agents/generic_proc.py#L40)). Agents call these right after the LLM returns, before building `GeneratedBlock`.
- Prompt-section pattern to mirror (F60): `render_format_section` returns `""` when nothing matches; each agent's `_build_prompt` conditionally appends it — [data_step.py:209-213](src/worker/engine/agents/data_step.py#L209), [proc.py:217-221](src/worker/engine/agents/proc.py#L217), [generic_proc.py:407-421](src/worker/engine/agents/generic_proc.py#L407).
- Rule to clarify: `SHARED_TRANSLATION_RULES` section 1 ([shared.py:71-74](src/worker/engine/agents/shared.py#L71)) — "NEVER cast a column to a different type just to match a reference schema." F61 casts to the **declared source** type (a different intent), and the cast is injected automatically — so sections 1, 5 (join-key normalization, 174-196), and 8 (249-270) need only a clarifying note that the LLM must not hand-write load casts (NOT a new contradicting cast instruction — see S-F).
- Reconciliation: [recon.py:61-88](src/executor/recon.py#L61) `_aggregate_parity` sums numeric columns; an all-null key → the `inf`/false-pass symptom. Reference loader reads `.sas7bdat` via pyreadstat → float64 for numerics, so **numeric → `"double"`** matches the reference's own representation and avoids reintroducing drift.

## Design decisions

- **Authoritative field:** `meta.readstat_variable_types`. Map `"string"` → `"string"`; everything else (`"double"`, int/float classes) → `"double"`. Unknown values pass through conservatively.
- **Key normalization:** store `column_types` keyed by **lowercased** varname, to align with the post-`toDF(lower)` column names the agents produce (resolves the SAS-uppercase vs PySpark-lowercase edge case).
- **Always emit the cast** for declared columns (not conditional on divergence): the injector operates on code strings and can't know the inferred type without running the read; `F.col(c).cast("string"/"double")` is idempotent, so over-casting is a harmless, auditable no-op. Group casts per source variable under one provenance comment; skip if an identical cast already exists (idempotence guard — avoids double-cast with section-5 join-key normalization).
- **Placement:** immediately after the `v = v.toDF(*[c.lower() for c in v.columns])` line for the variable. If the LLM omitted that line, synthesize it then inject — guarantees lowercase keys align. This keeps casts before any downstream transform (satisfies section-4 column-lifecycle rule).
- **Provenance:** `.sas7bdat` has no source line; cite the file: `# SAS: <info.path> (declared type)`.
- **CSV-only / no-metadata safety:** CSV/TSV/XLSX and derived/intermediate datasets carry empty `column_types` → injector and prompt section are pure no-ops. Primary safety guarantee.
- **Injector fragility (acknowledged):** matching `spark.read.*` assignments + locating the `toDF(lower)` line by regex is heavier than the existing `normalise_*` substitutions. Mitigations: (1) synthesize the `toDF(lower)` line when absent so there is always a known anchor; (2) the informational prompt section makes the LLM's read code more predictable; (3) S-I asserts the end-to-end outcome, not just the regex. If a read form escapes the regex, the result is a *missing* cast (degrades to today's behaviour), never a *wrong* one.
- **Optional DRY (standard-practice tidy):** the three agents each call `normalise_output_var_in_code` + `normalise_input_vars_in_code` at separate sites. S-D may introduce a single `postprocess_generated_code(code, block, context, agent_name)` in `shared.py` bundling those two calls + `inject_declared_casts`, and have each agent call the one helper — reduces drift across agents. Kept optional to bound blast radius; if it complicates the diff, wire `inject_declared_casts` per-agent like the existing helpers.

## Subtasks

### S-A: extend `DataFileInfo` with `column_types`
**File:** `src/worker/engine/models.py` (~432-448)
**Depends on:** none
**Done when:** `column_types: dict[str, str] = Field(default_factory=dict)` added with a docstring noting it is lowercased-varname → Spark cast type (`"string"`/`"double"`), empty for non-`.sas7bdat` files. Existing constructions remain valid (defaulted field). `windowed_context` needs no change.

### S-B: capture declared types in `_sniff_file` + wire into catalog
**File:** `src/worker/main.py` (`_sniff_file` 63-102; catalog loop 411-442)
**Depends on:** S-A
**Done when:** add pure helper `_map_readstat_type(rs_type: str) -> str` (`"string"`→`"string"`, else `"double"`). `_sniff_file` returns a 3-tuple `(columns, row_count, column_types)`; `.sas7bdat` branch builds lowercased `column_types` from `meta.readstat_variable_types`; CSV/TSV/XLSX and all error/`ImportError` paths return `{}`. The single catalog call site unpacks the 3-tuple and passes `column_types=` into `DataFileInfo`. All `_sniff_file` callers updated to new arity.

### S-C: deterministic `inject_declared_casts` helper (the guarantee)
**File:** `src/worker/engine/agents/shared.py` (new helper near 669-708)
**Depends on:** S-A
**Done when:** `inject_declared_casts(python_code, data_files, agent_name) -> str` (1) finds each `spark.read.*(...)`/`pd.read_*`/Excel-bridge assignment + its `/workspace/data/<basename>`, (2) matches a `DataFileInfo` with non-empty `column_types` by basename (case-insensitive), (3) finds or synthesizes the `toDF(lower)` line for that variable, (4) inserts a grouped, idempotent cast block (`v = v.withColumn(col, F.col(col).cast(<type>))`) with a `# SAS: <path> (declared type)` provenance comment, (5) logs one WARNING per injected file (mirroring the other normalisers), (6) is a no-op when `data_files` is empty / has no `column_types` / a matching cast already exists.

### S-D: wire injector into all three agents
**Files:** `data_step.py` (~299), `proc.py` (~313), `generic_proc.py` (~534/551)
**Depends on:** S-C
**Done when:** each agent calls `inject_declared_casts(fixed_code, context.data_files, "<AgentName>")` after the existing `normalise_*` calls (and after generic_proc's `_fix_excel_spark_reads`/`_fix_workspace_paths`, so basenames are already normalized) and before constructing `GeneratedBlock`.

### S-E: informational prompt-section helpers (the nudge)
**File:** `src/worker/engine/agents/shared.py` (alongside `render_format_section`, ~527-554)
**Depends on:** S-A
**Done when:** `detect_referenced_data_files(block, data_files) -> list[str]` returns `data_files` keys whose ext-stripped lowercased basename appears in `block.input_datasets` (primary) or `block.raw_sas` (fallback); `render_declared_types_section(referenced, data_files) -> str` returns `""` when no referenced file has `column_types`, else a `## Declared source column types` section listing `<col>: <string|numeric>` per file (deterministic order) followed by one line: *"Use these types when deciding join/compare/derivation logic. Do NOT write the load-time `.cast(...)` yourself — it is injected automatically after the lowercase-normalization step."*

### S-F: reconcile existing rules with F61 (informational, no new cast rule)
**File:** `src/worker/engine/agents/shared.py` (edit sections 1, 5, 8 — no new scoped cast rule)
**Depends on:** none (text only; pairs with S-E)
**Done when:** section 1 gains a one-line note that a deterministic declared-type cast (F61) is injected automatically from `.sas7bdat` metadata and the LLM must not hand-write load casts — preserving the existing "never cast to match a reference schema" intent unchanged; section 5 notes the declared-type cast runs first so its save/restore composes correctly. No instruction is added telling the LLM to emit a cast (the injector owns it), which is why sections 1/5/8 need only clarifying notes, not contradiction-resolution.

### S-G: wire section into all three prompt builders
**Files:** `data_step.py` (~209-213), `proc.py` (~217-221), `generic_proc.py` (~407-421)
**Depends on:** S-E, S-F
**Done when:** after the existing `format_section` block, each `_build_prompt` appends the `render_declared_types_section(detect_referenced_data_files(...))` output when non-empty. generic_proc's unconditional "## Uploaded data files" list stays as-is (the new section is additive + per-block scoped).

### S-H: unit tests (deterministic layers — directly assertable)
**Files:** `tests/test_shared_normalisers.py`, `tests/test_worker_main*.py`, a `_build_prompt` test per agent
**Depends on:** S-B, S-D, S-G
**Done when:** assert `_map_readstat_type` mapping; `_sniff_file` returns lowercased `{col: "string"|"double"}` for a `.sas7bdat` — tested by **monkeypatching `pyreadstat.read_sas7bdat`** to return a stub `meta` with `readstat_variable_types` (NOTE: `pyreadstat.write_sas7bdat` does not exist in this environment — confirmed — so do NOT try to author a real `.sas7bdat` fixture; mock the reader), and CSV returns `{}`; `inject_declared_casts` inserts the right cast after `toDF(lower)` for the correct variable, with provenance, idempotent on re-run, no-op for empty/CSV-only `data_files`, synthesizes `toDF(lower)` when missing, handles SAS-uppercase column names (build `DataFileInfo(column_types=...)` directly — no file I/O); `render_declared_types_section`/`detect_referenced_data_files` select only files the block reads and return `""`/`[]` otherwise; each agent's `_build_prompt` with a typed `DataFileInfo` contains the section + correct types (char + numeric) and the "do not hand-write the cast" line, absent when no typed file is read.

### S-I: end-to-end injection + reconciliation test (no real .sas7bdat)
**File:** `tests/test_worker_main_comprehensive.py` (or a recon-focused module)
**Depends on:** S-B, S-D
**Done when:** construct a `JobContext` whose `data_files` carries `column_types={"subjid": "string", ...}` directly (or monkeypatch `_sniff_file`), run a block's generated read code through `inject_declared_casts`, and assert the delivered code contains `.cast("string")` on `subjid` with a `# SAS:` provenance comment. Pair with a `recon.py` unit over two hand-built DataFrames — one where `subjid` is string (declared) joining cleanly, one where it is int (drifts to null) — asserting the injected-cast path yields finite `aggregate_parity`/`schema_parity` pass while the baseline drifts. Proves the fix closes the per-block-green/full-pipeline-`inf` false-pass without depending on `.sas7bdat` round-tripping.

### S-J: green gate
**Depends on:** all above
**Done when:** `make test` exits 0 (never `pytest` directly); ruff + mypy clean. No Dockerfile/compose changes → no `make docker-build` needed.

## Verification

- `make test` green with the new unit + e2e tests; coverage ≥90% (F60 gate).
- Capture a documented sandbox artefact (paste into this plan / journal at close, as F60 did): a real migration on the `subjid $10` fixture showing the `.cast("string")` + `# SAS:` provenance comment in delivered PySpark, and full-pipeline reconciliation no longer false-passing.

## Session close (2026-06-15) — verification outcome + downstream fixes

End-to-end sandbox verification confirmed the `.cast("string")` + `# SAS:` provenance injection in
delivered PySpark. Driving the full pipeline to green surfaced four issues — only the first is F61
itself; the rest were latent problems F61's correct casting *exposed* (committed separately):

- **F61 casting works** — `subjid`/`siteid` now carry the declared `string` type into delivered code.
- **Recon dtype detection (pandas 3.0):** `is_object_dtype` is `False` for the new `StringDtype`, so
  the recon type-alignment branch never fired. Switched the discriminator to `not is_numeric_dtype`.
- **Executor date serialization:** `to_json(orient='records')` encoded `DateType` columns as epoch-millis
  (pandas default), which recon misread as numeric SAS-days → `OutOfBoundsDatetime`. Fixed with
  `date_format='iso'` at the serialization boundary — the true root cause of the `firstaedt` mismatch.
- **`trtdurd` drift was NOT a code bug:** the generated `datediff+1` was faithful to `%m_first_dose`;
  the golden `adsl_expected.csv` was stale (built from a richer exposure dataset, end dates ~29d later).
  Regenerated `TRTEDT`/`TRTDURD` from the current `ex_raw.csv`. **Decision: never auto-fix parity
  mismatches with an agent** — it rewards gaming the golden and falsifies correct translations.
- **AMBIGUOUS_REFERENCE self-heal:** sharpened §5 (mandate `on=[...]` equi-joins) + deterministic
  bare→alias-qualified `F.col` rewrite in both `_safe_exec` and the executor's (new) bounded retry.

## Out of scope

- Parsing SAS source `LENGTH`/`FORMAT`/`ATTRIB` declarations for declared types (only `.sas7bdat` metadata is authoritative here; source-declaration parsing is the separate F34 P2-C path, not merged).
- Type coercion for calculated/derived columns (resolved by the translation agent output, not from source metadata).
- Date/datetime/decimal semantic typing beyond char-vs-numeric (`readstat_variable_types` only distinguishes string vs double; format-aware typing is a future enhancement).
- Persisting `column_types` to the DB (in-memory `JobContext` only, like `libname_map`/`format_catalog`).
- Changing the reconciliation harness itself (no new key-null-rate check) — the e2e test proves the fix; a structural recon guard can be a follow-up.
