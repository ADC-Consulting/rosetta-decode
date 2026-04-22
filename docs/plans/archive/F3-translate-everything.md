# F3 — Translate-Everything Pipeline

**Phase:** 2 (agentic pipeline overhaul)
**Area:** Worker / Backend / Frontend
**Status:** planned
**Branch:** feat/F3-translate-everything

## Goal

Remove the current hard-coded "refuse-to-translate" paths for PROC IML, PROC FCMP, PROC OPTMODEL,
and anything the parser tagged UNTRANSLATABLE. Every SAS block must attempt a real Python
translation. Non-translation outcomes (manual / skip) require an explicit, justified reason with
a non-empty `detected_features` list. Target platform is Python 3.12 + numpy, pandas, scipy,
statsmodels, scikit-learn, sqlalchemy, duckdb, pyarrow, matplotlib on Databricks or plain Python.

Done looks like:
- The `sas_project/05_risk_scoring_iml.sas` fixture produces real NumPy/SciPy code, not a TODO.
- Every block in every test case has `python_code` with real executable code **or** a `manual`
  decision accompanied by a non-empty `detected_features` list.
- `make test` exits 0, ruff + mypy pass.

---

## Subtasks

### S-A: Extend models — `src/worker/engine/models.py`
**Depends on:** none
**Done when:** new fields compile; existing tests still pass.

1. Extend `BlockType` with named PROC variants so the parser can preserve them:
   ```python
   PROC_IML = "PROC_IML"
   PROC_FCMP = "PROC_FCMP"
   PROC_MEANS = "PROC_MEANS"
   PROC_FREQ = "PROC_FREQ"
   PROC_TRANSPOSE = "PROC_TRANSPOSE"
   PROC_IMPORT = "PROC_IMPORT"
   PROC_EXPORT = "PROC_EXPORT"
   PROC_PRINT = "PROC_PRINT"
   PROC_CONTENTS = "PROC_CONTENTS"
   PROC_DATASETS = "PROC_DATASETS"
   PROC_OPTMODEL = "PROC_OPTMODEL"
   PROC_UNKNOWN = "PROC_UNKNOWN"   # unfamiliar PROC with parseable body
   ```
   Keep `UNTRANSLATABLE` for genuinely unparsable SAS (syntax errors, binary includes, etc.).

2. Extend `GeneratedBlock`:
   ```python
   confidence_score: float = 1.0        # 0.0–1.0, self-reported by LLM
   confidence_band: str = "high"        # "high" | "medium" | "low" | "very_low"
   assumptions: list[str] = []          # SAS quirks the translation relies on
   strategy_used: str = "translate"     # actual strategy applied
   ```
   Keep `confidence: str` as a deprecated alias (= `confidence_band`) for backward compat with
   existing callers. Remove it in a follow-up.

3. Extend `BlockPlan`:
   ```python
   confidence_score: float = 1.0
   confidence_band: str = "high"
   detected_features: list[str] = []   # required non-empty when strategy = "manual"
   ```
   Add validator: if `strategy == "manual"` and `detected_features == []`, raise ValueError.

- [ ] done

---

### S-B: Parser — preserve actual PROC type — `src/worker/engine/parser.py`
**Depends on:** S-A
**Done when:** `parse_file("... PROC IML; ...RUN;")` returns a block with
`block_type=BlockType.PROC_IML`, not `UNTRANSLATABLE`. Tests updated.

Changes:
1. Replace `_UNSUPPORTED_PROC_RE` with per-PROC patterns. Add a mapping:
   ```python
   _KNOWN_PROCS: dict[str, BlockType] = {
       "SORT": BlockType.PROC_SORT,
       "SQL": BlockType.PROC_SQL,
       "IML": BlockType.PROC_IML,
       "FCMP": BlockType.PROC_FCMP,
       "MEANS": BlockType.PROC_MEANS,
       "FREQ": BlockType.PROC_FREQ,
       "TRANSPOSE": BlockType.PROC_TRANSPOSE,
       "IMPORT": BlockType.PROC_IMPORT,
       "EXPORT": BlockType.PROC_EXPORT,
       "PRINT": BlockType.PROC_PRINT,
       "CONTENTS": BlockType.PROC_CONTENTS,
       "DATASETS": BlockType.PROC_DATASETS,
       "OPTMODEL": BlockType.PROC_OPTMODEL,
   }
   ```
2. For any PROC not in `_KNOWN_PROCS`, emit `BlockType.PROC_UNKNOWN` (not `UNTRANSLATABLE`).
   Set `untranslatable_reason=None` on these blocks.
3. Reserve `UNTRANSLATABLE` only for text that cannot be matched by any SAS block regex
   (syntax error, partial blocks, binary content).
4. Update `_parse_proc_blocks()` to extract `input_datasets` / `output_datasets` for the new
   types (DATA=/OUT= patterns as best-effort — OK to leave empty for IML/FCMP).

- [ ] done

---

### S-C: New `GenericProcAgent` — `src/worker/engine/agents/generic_proc.py`
**Depends on:** S-A
**Done when:** agent handles any block type and returns real Python; unit test mocks LLM.

Purpose: handle PROC_IML, PROC_FCMP, PROC_MEANS, PROC_FREQ, PROC_TRANSPOSE, PROC_UNKNOWN, and
any other PROC not covered by a specialist agent. Also handles PROC_OPTMODEL when the solver call
is simple enough to map to scipy.optimize.

Output model:
```python
class GenericProcResult(BaseModel):
    python_code: str
    strategy_used: str          # "translate" | "translate_with_review" | "manual_ingestion" |
                                #  "manual" | "skip"
    confidence_score: float     # 0.0–1.0
    confidence_band: str        # "high" | "medium" | "low" | "very_low"
    uncertainty_notes: list[str] = []
    assumptions: list[str] = []
    detected_features: list[str] = []   # required non-empty when strategy_used = "manual"
```

System prompt (key rules):
```
# agent: GenericProcAgent

You are a SAS-to-Python migration engineer targeting a modern Python 3.12 data platform.
The target environment has: numpy, pandas, pyarrow, scipy, scikit-learn, statsmodels,
sqlalchemy, duckdb, matplotlib.

Your job is to translate ANY SAS PROC block into idiomatic Python.
Default assumption: translation is POSSIBLE. Only choose strategy="manual" when the block
relies on features with NO reasonable Python equivalent — and you MUST list those features
in detected_features. If detected_features would be empty, you CANNOT choose manual.

## Strategy selection (in priority order)
1. "translate"              — fully automated, high confidence expected.
2. "translate_with_review"  — translated but a human should verify; use for:
     - SAS date/time semantics (INTNX, INTCK, SAS date literals, date origins)
     - SAS format/informat conversions (PICTURE, INFORMATs)
     - SAS std() = sample std (ddof=1) — note this in assumptions
     - SAS missing-value propagation (special missing ., .A-.Z)
     - CALL SYMPUT/SYMPUTX with dynamic dataset names
     - PROC IML matrix arithmetic mapped to NumPy
     - PROC FCMP function definitions
3. "manual_ingestion"       — PROC IMPORT / PROC EXPORT file I/O only.
     Emit a pandas read/write shell with TODO comments.
4. "manual"                 — ONLY when detected_features is non-empty AND features have
     no reasonable Python equivalent. Example: PROC OPTMODEL LP/NLP solver calls where
     the model structure cannot be mechanically translated to scipy.optimize or pyomo.
     Emit a justified stub with suggested Python library in a comment.
5. "skip"                   — PROC PRINT, PROC CONTENTS, PROC DATASETS, standalone
     title/footnote statements. Emit an empty string.

## PROC-specific guidance

PROC MEANS / PROC SUMMARY:
→ Use pandas .groupby().agg() or .describe(). Map CLASS → groupby, VAR → columns.
  Map N/MEAN/STD/MIN/MAX/MEDIAN to the corresponding pandas/numpy aggregators.
  SAS STD is sample std (ddof=1, pandas default).

PROC FREQ:
→ Use pd.crosstab() for two-way tables; .value_counts() for one-way.
  TABLES a*b / CHISQ → scipy.stats.chi2_contingency(pd.crosstab(df.a, df.b)).

PROC TRANSPOSE:
→ Use df.pivot() or df.melt(). Map ID → index, VAR → columns.

PROC IML:
→ Use NumPy for matrix arithmetic. Map IML matrix syntax to np.array / np.linalg.
  Note: SAS IML uses column-major storage; NumPy defaults to row-major — transpose
  when order matters. Note SAS STD = sample std (ddof=1).
  If the block computes z-scores: use scipy.stats.zscore(ddof=1).

PROC FCMP:
→ Emit as a standalone Python function with a docstring noting the SAS original.
  Map SAS function signatures to Python def. Preserve argument order.

PROC OPTMODEL with solver call:
→ If the objective/constraints are linear, suggest scipy.optimize.linprog or PuLP.
  If non-linear, suggest scipy.optimize.minimize. Emit a scaffold with TODOs.
  detected_features must list: solver_type, variable_count (if known), constraint_types.
  strategy = "manual" only if the solver structure is so complex that no scaffold
  is meaningful.

PROC UNKNOWN (unfamiliar PROC):
→ Attempt translation. If you have domain knowledge, use it. If not, emit a
  translate_with_review scaffold with uncertainty_notes explaining what you assumed.
  Never emit a silent TODO — always include your best-effort attempt.

## Output schema — ALL fields REQUIRED
{
  "python_code": "<translated Python — never an empty string for translate/translate_with_review>",
  "strategy_used": "translate|translate_with_review|manual_ingestion|manual|skip",
  "confidence_score": <float 0.0–1.0>,
  "confidence_band": "high|medium|low|very_low",
  "uncertainty_notes": ["<one sentence per uncertain construct>"],
  "assumptions": ["<SAS semantic quirk this translation relies on>"],
  "detected_features": ["<required non-empty when strategy_used=manual>"]
}

Confidence score guidelines:
  1.0–0.85  high        trivial/well-known pattern, reconciliation expected to pass
  0.84–0.65 medium      pattern applied but output may differ in edge cases
  0.64–0.40 low         ambiguous semantics; human review mandatory
  0.39–0.0  very_low    best-effort; significant manual work expected

Add # SAS: <source_file>:<line_number> after each logical section.
Preserve SAS column names exactly, lowercased.
Do NOT invent datasets or columns not present in the SAS source.
```

Max tokens: 8000.

- [ ] done

---

### S-D: Update `MigrationPlannerAgent` prompt — `src/worker/engine/agents/migration_planner.py`
**Depends on:** S-A
**Done when:** planner emits `confidence_score`, `confidence_band`, `detected_features` per block;
validator rejects `manual` with empty `detected_features`.

Changes to system prompt:
1. Replace the hard "PROC X ⇒ manual" rules with the graded feature-driven policy:
   - Default is `translate`. Only use `manual` when `detected_features` is non-empty.
   - For known PROCs (IML, FCMP, MEANS, FREQ, TRANSPOSE) default to `translate_with_review`.
   - `manual` requires listing the exact SAS features that have no Python equivalent.
2. Add `confidence_score` (0.0–1.0) and `confidence_band` to each `block_plan` in output JSON.
3. Add `detected_features: []` to each `block_plan`.
4. Update `PlannerResult` and `BlockPlan` construction in `_build_migration_plan()` to pass
   the new fields through.
5. Update `BlockPlan` validator to enforce non-empty `detected_features` for `manual`.

JSON output addition per block:
```json
{
  ...,
  "confidence_score": 0.75,
  "confidence_band": "medium",
  "detected_features": []
}
```

- [ ] done

---

### S-E: Update `DataStepAgent` prompt — `src/worker/engine/agents/data_step.py`
**Depends on:** S-A
**Done when:** prompt mentions modern target platform; output model gains `confidence_score`,
`confidence_band`, `assumptions`, `strategy_used`.

Changes:
1. Expand target platform: *"Use numpy, pandas, pyarrow, scipy, statsmodels as needed — not
   pandas-only. The target is Python 3.12 on Databricks or plain Python."*
2. Add SAS semantic preservation notes:
   - SAS std() = sample std (ddof=1 — pandas default, NumPy default is 0; use ddof=1 explicitly)
   - SAS date origin = 1 January 1960 (convert to pd.Timestamp('1960-01-01') + pd.to_timedelta)
   - SAS missing numeric = `.` (propagates as NaN in pandas — this is correct by default)
   - SAS special missings `.A`–`.Z` are not representable in float64 — note in uncertainty_notes
3. Update `DataStepResult` to include `confidence_score: float`, `confidence_band: str`,
   `assumptions: list[str]`, `strategy_used: str`.
4. Update the `translate()` method to pass new fields into `GeneratedBlock`.

- [ ] done

---

### S-F: Update `ProcAgent` prompt — `src/worker/engine/agents/proc.py`
**Depends on:** S-A
**Done when:** PROC SQL prompt expands platform; removes hard "PROC IML → TODO" rules (those now
live in GenericProcAgent); output model gains same new fields as DataStepAgent.

Changes:
1. Remove the inline rules that map PROC IML/FCMP/OPTMODEL to manual TODOs — the router now
   sends those to GenericProcAgent, not ProcAgent.
2. Add modern platform note to prompt (same as S-E).
3. For complex PROC SQL, allow duckdb as an alternative to pure pandas when the query is too
   complex to translate idiomatically (WINDOW FUNCTION chains, recursive CTEs).
4. Update `ProcResult` model with `confidence_score`, `confidence_band`, `assumptions`,
   `strategy_used`. Update `translate()` accordingly.

- [ ] done

---

### S-G: Update `TranslationRouter` — `src/worker/engine/router.py`
**Depends on:** S-C (GenericProcAgent must exist)
**Done when:** every block type reaches a real translation agent; no `_` catch-all routes to stub.

Changes:
1. Accept `generic_proc_agent` as constructor argument.
2. Route `PROC_IML`, `PROC_FCMP`, `PROC_MEANS`, `PROC_FREQ`, `PROC_TRANSPOSE`, `PROC_UNKNOWN`,
   and any other `PROC_*` type to `generic_proc_agent`.
3. Route `PROC_IMPORT`, `PROC_EXPORT` to `generic_proc_agent` (it handles `manual_ingestion`).
4. Route `PROC_PRINT`, `PROC_CONTENTS`, `PROC_DATASETS` to `generic_proc_agent` (it handles `skip`).
5. Route `PROC_OPTMODEL` to `generic_proc_agent`.
6. Keep `UNTRANSLATABLE` → stub (only reached for genuinely unparsable SAS).
7. Remove the `raise ValueError` catch-all; replace with `generic_proc_agent` as default.
8. Update `main.py` to construct and inject `GenericProcAgent`.

- [ ] done

---

### S-H: Update `main.py` — `src/worker/main.py`
**Depends on:** S-G
**Done when:** `JobOrchestrator` constructs `GenericProcAgent` and passes it to `TranslationRouter`.

Also: update `_translate_blocks` to pass `strategy_used`, `confidence_score`, `confidence_band`,
`assumptions` from the agent result into `GeneratedBlock`.

- [ ] done

---

### S-I: Block revision model + Alembic migration
**Depends on:** S-H
**Done when:** `BlockRevision` ORM model exists; migration created; revision appended on every
translation attempt (initial, refine, auto-retry Phase 2).

New ORM model `BlockRevision` in `src/backend/db/models.py`:
```python
class BlockRevision(Base):
    __tablename__ = "block_revisions"
    id: str  # UUID
    job_id: str  # FK → jobs.id
    block_id: str  # "source_file:start_line"
    revision: int  # auto-incrementing per (job_id, block_id)
    strategy: str
    confidence_score: float
    confidence_band: str
    reconciliation_passed: bool | None
    verified_confidence: float | None
    python_code: str
    diff_vs_previous: str | None  # unified diff vs revision-1, null for rev 0
    trigger: str  # "agent-initial" | "agent-retry" | "human-refine"
    actor: str    # "system" | user ID (future)
    created_at: datetime
```

Alembic migration: `alembic revision --autogenerate -m "add block_revisions table"`.

Worker: append a `BlockRevision` row in `_translate_blocks` for each block after translation.

- [ ] done

---

### S-J: Reconciliation → verified confidence — `src/worker/validation/reconciliation.py`
**Depends on:** S-H
**Done when:** reconciliation result upgrades/downgrades `verified_confidence` on each
`GeneratedBlock` and populates `BlockRevision.verified_confidence` / `reconciliation_passed`.

Rule:
- If reconciliation passes + block's `confidence_score >= 0.85` → `verified_confidence = confidence_score`
- If reconciliation passes + block's `confidence_score < 0.85` → `verified_confidence = confidence_score + 0.1` (capped at 1.0)
- If reconciliation fails → `verified_confidence = confidence_score * 0.5` (floor 0.1)

Store `verified_confidence` on `GeneratedBlock.verified_confidence`.
Update `BlockRevision.verified_confidence` and `reconciliation_passed` after the run.

- [ ] done

---

### S-K: LineageEnricher — risk propagation — `src/worker/engine/agents/lineage_enricher.py`
**Depends on:** S-J
**Done when:** blocks downstream of a low-confidence or failed block carry `risk_propagated=true`
in `block_status`; enricher system prompt updated to propagate risk.

In `BlockStatus` model, add `risk_propagated: bool = False`.
In LineageEnricherAgent system prompt, add task:
> "8. For each block in block_status, if any upstream block in the lineage graph has
>    confidence_band = 'low' or 'very_low', or reconciliation_passed = false, set
>    risk_propagated = true on all downstream blocks in that data flow."

- [ ] done

---

### S-L: API schemas + new endpoint — `src/backend/api/schemas.py` + `routes/jobs.py`
**Depends on:** S-I
**Done when:** `GET /jobs/{id}/blocks/{block_id}/revisions` returns the full revision history;
`POST /jobs/{id}/blocks/{block_id}/rollback` reverts to a prior revision.

New response models:
```python
class BlockRevisionResponse(BaseModel):
    id: str
    block_id: str
    revision: int
    strategy: str
    confidence_score: float
    confidence_band: str
    reconciliation_passed: bool | None
    verified_confidence: float | None
    python_code: str
    diff_vs_previous: str | None
    trigger: str
    actor: str
    created_at: datetime

class BlockRevisionsResponse(BaseModel):
    job_id: UUID
    block_id: str
    revisions: list[BlockRevisionResponse]
```

Endpoints:
- `GET /jobs/{id}/blocks/{block_id}/revisions` → `BlockRevisionsResponse`
- `POST /jobs/{id}/blocks/{block_id}/rollback` with body `{ "revision": int }` →
  updates `job.generated_files` for that block + appends a new revision with
  `trigger="human-rollback"`.

- [ ] done

---

### S-M: Fixture + tests — `tests/`
**Depends on:** S-A through S-L
**Done when:** all new tests pass; existing tests updated for new field signatures.

1. Add `samples/sas_project/05_risk_scoring_iml.sas` — a PROC IML block computing mean, std,
   z-scores across a matrix. Expected: `translate_with_review`, real NumPy code, confidence ~0.6–0.8.
2. Add `tests/test_generic_proc_agent.py` — unit tests for GenericProcAgent:
   - PROC IML → real code, confidence_band in {"medium","low"}, no TODO stub
   - PROC FCMP → Python function emitted
   - PROC OPTMODEL LP → scaffold with scipy.optimize suggestion, detected_features non-empty
   - PROC MEANS → pandas groupby/describe code
3. Add `tests/test_parser_proc_types.py` — verify each known PROC maps to correct BlockType.
4. Update `tests/test_analysis_agent.py`, `test_data_step_agent.py`, `test_codegen.py` for
   new model fields.
5. Update router tests to verify `GenericProcAgent` is reached for PROC_IML blocks.

- [ ] done

---

### S-N: `make test` + ruff + mypy full pass
**Depends on:** S-M
**Done when:** `make test` exits 0; `ruff check` exits 0; `mypy` exits 0.

- [ ] done

---

## Acceptance checklist

- [ ] No block is silently stubbed (is_untranslatable=False unless genuinely unparsable)
- [ ] Every PROC IML/FCMP block produces real Python code
- [ ] Every `manual` decision has non-empty `detected_features`
- [ ] Every block has `confidence_score` (float) + `confidence_band` + `assumptions`
- [ ] `BlockRevision` rows appended for every translation attempt
- [ ] Reconciliation updates `verified_confidence` on `GeneratedBlock`
- [ ] Downstream risk propagated in `BlockStatus.risk_propagated`
- [ ] `GET /jobs/{id}/blocks/{block_id}/revisions` returns full history
- [ ] `POST /jobs/{id}/blocks/{block_id}/rollback` reverts to prior revision
- [ ] `make test` exits 0

---

## Files to create / modify

| File | Action |
|------|--------|
| `src/worker/engine/models.py` | extend BlockType, GeneratedBlock, BlockPlan |
| `src/worker/engine/parser.py` | preserve actual PROC type |
| `src/worker/engine/agents/generic_proc.py` | **new** |
| `src/worker/engine/agents/migration_planner.py` | update prompt + models |
| `src/worker/engine/agents/data_step.py` | update prompt + models |
| `src/worker/engine/agents/proc.py` | update prompt + models |
| `src/worker/engine/router.py` | inject GenericProcAgent |
| `src/worker/main.py` | construct GenericProcAgent, pass new fields |
| `src/worker/validation/reconciliation.py` | verified confidence |
| `src/worker/engine/agents/lineage_enricher.py` | risk propagation |
| `src/backend/db/models.py` | BlockRevision ORM |
| `src/backend/api/schemas.py` | new response models |
| `src/backend/api/routes/jobs.py` | 2 new endpoints |
| `alembic/versions/` | new migration |
| `tests/test_generic_proc_agent.py` | **new** |
| `tests/test_parser_proc_types.py` | **new** |
| `tests/test_analysis_agent.py` | update fixtures |
| `tests/test_data_step_agent.py` | update fixtures |
| `tests/test_codegen.py` | update fixtures |
| `samples/sas_project/05_risk_scoring_iml.sas` | **new** |
