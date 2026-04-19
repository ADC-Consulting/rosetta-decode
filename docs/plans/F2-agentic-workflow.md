# F2 — Agentic Workflow

**Phase:** 2
**Area:** Worker / Infrastructure
**Status:** in-progress

## Goal

Replace the current single-prompt, stateless-per-block translation loop with a
structured agentic pipeline. The pipeline adds shared job context (so all agents
understand the full codebase before translating individual blocks), specialist LLM
agents per SAS construct, a reconciliation feedback loop, and an explicit stub path
for genuinely untranslatable blocks. Cost and rate-limiting are externalized to a
TensorZero gateway container so budget controls are decoupled from application code.

Done looks like: a migrated job is processed by the new pipeline end-to-end; tests
pass; per-job circuit breaker fires correctly when the call cap is hit; all existing
reconciliation tests remain green.

---

## Acceptance Criteria

- [ ] TensorZero gateway runs as a 5th Docker service; worker routes all LLM calls through it
- [ ] `AnalysisAgent` produces a `JobContext` (resolved macros, dependency order, risk flags) before any translation begins
- [ ] `TranslationRouter` dispatches blocks deterministically by `BlockType` — no LLM involvement in routing
- [ ] `DataStepAgent` translates DATA step blocks using `JobContext` for cross-block awareness
- [ ] `ProcAgent` translates PROC SQL blocks using `JobContext`
- [ ] PROC_SORT blocks are handled inline by a non-LLM helper (no specialist agent needed)
- [ ] Genuinely untranslatable blocks pass through `StubGenerator` producing an explicit `# SAS-UNTRANSLATABLE` + `# TODO: manual review` stub with a `human_review_required` flag on the job
- [ ] `FailureInterpreterAgent` fires only on reconciliation failure; produces a `retry_hint` string pointing at the offending block
- [ ] `RefinementLoop` re-invokes the relevant specialist with the `retry_hint`; max 2 rounds
- [ ] When TensorZero returns HTTP 429 (circuit breaker), worker sets `status=failed`, `error_detail="circuit_breaker_tripped"`, persists partial output
- [ ] `DocumentationAgent` receives full `JobContext` + generated Python + `ValidationResult` (not just raw SAS source)
- [ ] All existing tests pass (`make test` exits 0)
- [ ] ruff and mypy pass

---

## Architecture Changes

### New 5th service: TensorZero gateway

- Container: `tensorzero/gateway:latest`
- Config: `config/tensorzero.toml`
- Postgres backend: same `rosetta` database (no ClickHouse needed)
- Worker routes all LLM calls to `http://tensorzero:3000/openai/v1`
- Azure API key lives in `tensorzero.toml` `api_key_location`, not in the worker

### Non-LLM components (no agent, deterministic)

| Component | Where | Role |
|---|---|---|
| `SASParser` | `src/worker/engine/parser.py` | Unchanged |
| `MacroExpander` | `src/worker/engine/macro_expander.py` | Deterministic `%LET` + simple `%MACRO/%MEND` inlining; raises `CannotExpand` for complex cases |
| `TranslationRouter` | `src/worker/engine/router.py` | `match block.block_type → agent` — pure dispatch |
| `StubGenerator` | `src/worker/engine/stub_generator.py` | Emits explicit untranslatable stub; sets `human_review_required=True` on job |
| `ReconciliationRunner` | `src/worker/validation/reconciliation.py` | Unchanged |
| `CodeGenerator` | `src/worker/engine/codegen.py` | Unchanged |
| `RefinementLoop` | Inside `JobOrchestrator` | Loop control: if fail and `retry_count < 2`, re-invoke specialist with `retry_hint` |

### LLM agents (6)

| Agent | File | Receives | Produces |
|---|---|---|---|
| `AnalysisAgent` | `src/worker/engine/agents/analysis.py` | All source files + macro list | `JobContext` |
| `MacroResolverAgent` | `src/worker/engine/agents/macro_resolver.py` | Failing macro + `JobContext` | Expanded SAS text or `CannotExpand` — **gated**: only called on `CannotExpand` from `MacroExpander` |
| `DataStepAgent` | `src/worker/engine/agents/data_step.py` | Block + `JobContext` slice | `GeneratedBlock` |
| `ProcAgent` | `src/worker/engine/agents/proc.py` | PROC SQL block + `JobContext` slice | `GeneratedBlock` |
| `FailureInterpreterAgent` | `src/worker/engine/agents/failure_interpreter.py` | Reconciliation diff + generated code | `retry_hint: str`, `affected_block_id: str` |
| `DocumentationAgent` | `src/worker/engine/agents/documentation.py` | `JobContext` + `GeneratedCode` + `ValidationResult` | Markdown doc |

### Shared `JobContext` object

```python
class JobContext(BaseModel):
    source_files: dict[str, str]            # filename → SAS text (full, for AnalysisAgent/DocAgent)
    resolved_macros: list[MacroVar]         # from MacroExpander + MacroResolverAgent
    dependency_order: list[str]             # dataset names in topo order
    risk_flags: list[str]                   # e.g. ["nested macro at etl.sas:42"]
    blocks: list[SASBlock]                  # parsed blocks (unchanged)
    generated: list[GeneratedBlock]         # filled during translation
    reconciliation: ReconciliationReport | None
    retry_count: int
    llm_call_count: int                     # tracked for observability; hard limit enforced by TensorZero
```

Translation agents receive a **windowed view** of `JobContext` — only their block plus
the `resolved_macros` list and the subset of `dependency_order` relevant to their block's
inputs/outputs. `AnalysisAgent` and `DocumentationAgent` receive the full `source_files`.

### Orchestration sequence

```
1.  SASParser.parse()                    → blocks, macro_vars         (no LLM)
2.  MacroExpander.expand()               → inlined blocks              (no LLM)
    └─ on CannotExpand: MacroResolverAgent  (LLM call #1, gated)
3.  AnalysisAgent.analyse()              → JobContext                  (LLM call)
4.  for block in blocks:
      TranslationRouter.route(block)     → deterministic dispatch      (no LLM)
      ├─ DATA_STEP     → DataStepAgent                                 (LLM call per block)
      ├─ PROC_SQL      → ProcAgent                                     (LLM call per block)
      ├─ PROC_SORT     → inline sort helper (df.sort_values, no LLM)
      └─ UNTRANSLATABLE → StubGenerator                                (no LLM)
5.  CodeGenerator.assemble()             → pipeline.py                 (no LLM)
6.  ReconciliationRunner.run()           → ReconciliationReport        (no LLM)
7.  if fail and retry_count < 2:
      FailureInterpreterAgent.interpret()                               (LLM call)
      RefinementLoop: re-invoke specialist with retry_hint
      retry_count += 1 → go to step 4 (affected block only)
8.  DocumentationAgent.generate()                                       (LLM call)
9.  Persist → status=done
    on TensorZero 429 at any step → status=failed, error_detail="circuit_breaker_tripped"
```

### Budget controls (enforced by TensorZero, not application code)

```toml
# config/tensorzero.toml

# Per-job circuit breaker: max 40 LLM calls per migration job
[[rate_limiting.rules]]
model_inferences_per_hour = 40
scope = [{ tag_key = "job_id", tag_value = "tensorzero::each" }]
priority = 1

# Global daily safety net
[[rate_limiting.rules]]
always = true
model_inferences_per_day = 1000
tokens_per_minute = { capacity = 750000, refill_rate = 150000 }
```

Every worker LLM call tags `job_id` + `agent` — enables per-agent observability in TensorZero UI.

Token budgets enforced at call site via `max_tokens`:
- `AnalysisAgent`: 8 000 (sees full source)
- `DataStepAgent` / `ProcAgent`: 4 000 (windowed context)
- `FailureInterpreterAgent`: 2 000
- `DocumentationAgent`: 6 000

---

## Subtasks

### S00: TensorZero infra — config + docker-compose
**File:** `config/tensorzero.toml`, `docker-compose.yml`, `.env.example`
**Depends on:** none
**Done when:** `docker compose up tensorzero` starts without error; `curl http://localhost:3000/health` returns 200; existing worker still works (gateway is additive, not yet wired)
- [ ] done

---

### S01: `JobContext` model
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** `JobContext` Pydantic model exists with all fields; `windowed_context(block)` method returns the correct subset; unit test covers windowing logic
- [ ] done

---

### S02: `MacroExpander` (deterministic, non-LLM)
**File:** `src/worker/engine/macro_expander.py`
**Depends on:** none
**Done when:** `MacroExpander.expand(blocks, macro_vars)` resolves `%LET` substitutions and simple `%MACRO/%MEND` inlining; raises `CannotExpand` for complex cases (nested macro calls, `%IF/%ELSE` within macros); unit tests cover both paths
- [ ] done

---

### S03: `AnalysisAgent`
**File:** `src/worker/engine/agents/analysis.py`
**Depends on:** S01
**Done when:** `AnalysisAgent.analyse(source_files, macro_vars)` makes one LLM call (tagged `agent=AnalysisAgent`); returns a populated `JobContext` with `resolved_macros`, `dependency_order`, `risk_flags`; unit test mocks the LLM call and validates output shape
- [ ] done

---

### S04: `TranslationRouter` + `StubGenerator`
**File:** `src/worker/engine/router.py`, `src/worker/engine/stub_generator.py`
**Depends on:** S01
**Done when:** `TranslationRouter.route(block)` returns the correct agent class by `BlockType` with no LLM call; `StubGenerator.generate(block)` returns a `GeneratedBlock` with `# SAS-UNTRANSLATABLE` + `# TODO` comment and `is_untranslatable=True`; unit tests cover all `BlockType` values
- [ ] done

---

### S05: `DataStepAgent`
**File:** `src/worker/engine/agents/data_step.py`
**Depends on:** S03, S04
**Done when:** `DataStepAgent.translate(block, context)` makes one LLM call with a DATA step-specific system prompt, passes windowed `JobContext`, tags `agent=DataStepAgent`; returns `GeneratedBlock`; unit test with mocked LLM validates context windowing and output shape
- [ ] done

---

### S06: `ProcAgent`
**File:** `src/worker/engine/agents/proc.py`
**Depends on:** S03, S04
**Done when:** `ProcAgent.translate(block, context)` handles PROC SQL with a PROC-specific system prompt; tags `agent=ProcAgent`; PROC_SORT falls through to inline helper (not this agent); unit test confirms PROC_SORT is rejected by this agent
- [ ] done

---

### S07: `MacroResolverAgent` (gated LLM fallback)
**File:** `src/worker/engine/agents/macro_resolver.py`
**Depends on:** S02
**Done when:** `MacroResolverAgent.resolve(macro_text, context)` is only called from `MacroExpander` on `CannotExpand`; makes one LLM call tagged `agent=MacroResolverAgent`; if LLM also cannot resolve, re-raises `CannotExpand` (block eventually goes to `StubGenerator`); unit test verifies gating: agent is never called on a block `MacroExpander` can handle
- [ ] done

---

### S08: `FailureInterpreterAgent` + `RefinementLoop`
**File:** `src/worker/engine/agents/failure_interpreter.py`, updated `src/worker/main.py`
**Depends on:** S05, S06
**Done when:** `FailureInterpreterAgent.interpret(diff, generated_code)` produces `retry_hint` and `affected_block_id`; `RefinementLoop` in `JobOrchestrator` re-invokes only the affected specialist with the hint; `retry_count` is incremented and capped at 2; test simulates a reconciliation failure and verifies the loop fires exactly once on the first failure and stops after 2
- [ ] done

---

### S09: `DocumentationAgent` upgrade
**File:** `src/worker/engine/agents/documentation.py` (replaces `doc_generator.py`)
**Depends on:** S03, S08
**Done when:** `DocumentationAgent.generate(context, generated_code, validation_result)` receives full `JobContext` + Python output + reconciliation result; produces richer Markdown than the current prompt; tagged `agent=DocumentationAgent`; existing `test_doc_generator.py` updated to test new interface; old `doc_generator.py` removed
- [ ] done

---

### S10: Wire `JobOrchestrator` — replace `_process_job`
**File:** `src/worker/main.py`
**Depends on:** S02, S03, S04, S05, S06, S07, S08, S09
**Done when:** `_process_job` replaced by `JobOrchestrator.run(job, session)` that executes the full sequence (steps 1–9 in the orchestration diagram); catches TensorZero 429 and writes `status=failed, error_detail="circuit_breaker_tripped"`; all existing worker tests pass unchanged
- [ ] done

---

### S11: Worker `config.py` + env wiring
**File:** `src/worker/core/config.py`, `.env.example`
**Depends on:** S00
**Done when:** `WorkerSettings` has `tensorzero_gateway_url: str | None`; when set, `LLMClient` (or each agent) uses it as `base_url`; when unset, falls back to direct provider (preserves local dev without TensorZero); `.env.example` documents the new var; unit test checks both code paths in config
- [ ] done

---

### S12: Reconciliation tests for new pipeline
**File:** `tests/reconciliation/test_agentic_pipeline.py`
**Depends on:** S10
**Done when:** End-to-end reconciliation test (using `samples/basic_etl.sas` + `samples/basic_etl_ref.csv`) passes through the full new pipeline with mocked LLM agents; verifies `JobContext` is populated, `TranslationRouter` dispatches correctly, reconciliation report is attached to the job; `make test` exits 0
- [ ] done

---

## Implementation Priority

Build in this order — each phase is independently releasable:

**Phase A — Foundation (unblocks everything)**
S00 → S01 → S02 → S03

**Phase B — Translation layer**
S04 → S05 → S06 (parallel after S04)

**Phase C — Edge cases + feedback**
S07 → S08

**Phase D — Wiring + cleanup**
S09 → S11 → S10 → S12

---

## Dependencies on other features

- `F-backend-postmvp` S-BE5 (re-reconciliation) should be implemented after this feature stabilises — the `RefinementLoop` here covers in-job retries; S-BE5 covers user-triggered re-runs

## Out of scope for this feature

- ClickHouse / full TensorZero observability UI — Postgres backend is sufficient for rate limiting; ClickHouse deferred
- Fine-tuning or prompt optimisation via TensorZero Autopilot
- `PROC MEANS`, `PROC FREQ`, `PROC TRANSPOSE` specialist agents — routed to `StubGenerator` until a dedicated agent is justified by data
- `DatabricksBackend` / `CLOUD=true` — agentic pipeline runs local only for now
- Frontend changes — no UI changes in this feature
