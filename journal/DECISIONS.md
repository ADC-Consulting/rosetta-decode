```markdown
# Decisions Log

Append-only. For larger decisions, also create a full ADR in `docs/adr/`.
Format: date · decision · rationale · revisit?

---

## 2026-09-02 — F90 Manifest rollout: branch stacking, mockup durability, audit heuristic

- **New feature branches may stack on an unmerged branch rather than wait for merge:** F90 branched
  off `feat/F89-manifest-color-fidelity` (itself stacked on F88 on F87, none merged, PRs #136-#138
  open) instead of waiting · user's explicit choice when asked — unblocks work immediately at the
  cost of a deeper stack that must merge in order · revisit if the stack depth becomes unwieldy
- **Design mockups approved via a Claude Artifact must be preserved in-repo:** the "Manifest"
  mockup existed only as a published Artifact link with no local source; re-extracted the
  `.dc.html` via the design skill's `--extract` flow and committed it to `docs/design/` · an
  external link is not a durable reference for a design system the team keeps fidelity-checking
  against · revisit: apply the same treatment to any future approved design-canvas mockup
- **Status-color audit heuristic, locked in for future Manifest-rollout work:** when auditing a
  surface for hand-rolled color duplication, route a color through the shared tone system only if
  it represents a health/confidence/outcome signal (migrated/changed/added/dropped/estimated,
  success/warning/danger) — leave alone anything representing a structural/categorical role (PK/FK
  badges, file-type badges, schema-kind labels) even if the hue happens to overlap · misusing the
  tone system for non-status meaning would be a regression, not a fix · revisit never

---

## 2026-08-27 — F89 color-fidelity fixes: tone cleanup + a locked Tailwind v4 scoping pattern

- **`caution` tone (orange) merged into `warning` (amber):** criticality tier "high" previously
  rendered as its own orange hue, visually redundant next to `warning`'s amber for tier "medium" —
  the two read as noise rather than a distinct signal at chip size. Collapsed to 5 semantic tones
  total (`success`/`warning`/`danger`/`danger-strong`/`neutral`); the tier label text still
  distinguishes "high" from "medium" · rationale: user evaluated the tradeoff and chose to merge
  rather than pick a more distinct orange · revisit if a client explicitly needs a 4th visual
  severity tier
- **Chevron/arrow tab bar shape kept, not replaced with the Manifest mockup's plain pill tabs:**
  the mockups (this session) happened to use a plain rounded-pill tab bar as a stylistic choice
  when built, but `ChevronTabBar` is shared across all 5 tabs and was a deliberate earlier design
  decision (see 2026-06-02 entry, "aligns UI with migration pipeline stages") · rationale: the
  user was never asked to sign off on replacing the chevron interaction specifically, only the
  color/type/radius/density direction; changing it is a bigger, more visible interaction change
  than the rest of F88/F89's scope · revisit only if the chevron shape itself gets explicitly
  reconsidered in a future session
- **LOCKED PATTERN — scoping a CSS custom property override inside `.brand-manifest` must
  redeclare the *derived* Tailwind token, not just the primitive:** Tailwind v4's `@theme` block
  derives tokens like `--color-primary: var(--primary)` and `--radius-lg: var(--radius)` **once,
  at `:root` only**. A `var()` reference inside a custom-property's OWN declared value resolves
  using the cascade at the element where THAT property is declared — so overriding just the
  primitive (`--primary`, `--radius`) in a nested scope does NOT retroactively change what the
  derived token (`--color-primary`, `--radius-lg`) already resolved to at `:root`; utility classes
  built on the derived token (`bg-primary`, `rounded-lg`) silently keep rendering the old value.
  Hit and fixed twice this session (once for `--color-primary`/teal accent in F88, once for
  `--radius-lg`/`--radius-md`/`--radius-sm`/6px-radius in F89) before the pattern was recognized
  and named. **The fix, and the pattern to follow for any future scoped token:** either (a)
  redeclare the derived token directly in the scope too (simplest — one extra line per token,
  used for the radius fix), or (b) reference the raw primitive directly via a Tailwind
  arbitrary-value class (`bg-[var(--primary)]` instead of `bg-primary`), bypassing the derived
  token's indirection entirely (used for color, since dozens of consuming classes existed) ·
  rationale: burned real time twice on the same root cause; recording it so it's not
  re-discovered a third time · revisit never — applies to any future `.brand-manifest`-style
  scoped override

---

## 2026-08-26 — "Manifest" design direction chosen to address "vibe coded" feedback

- **Design direction "Manifest" selected over "Ledger" (dense/plain-text) and "Dossier" (editorial/serif):** three concrete visual-direction mockups of the Plan tab were built and published as a design canvas Artifact (see session journal) after F87's structural-consistency fix did not resolve the underlying "vibe coded" perception. Manifest — Archivo + Space Mono type pairing, a teal brand accent (distinct from the existing semantic red/amber/green), a consistent 6px radius scale, and one unified summary card in place of five stacked boxes — was chosen as the best fit for a compliance/audit B2B tool: enough structure (badges, one card) for reviewers to scan a dense steps table quickly, without the plain-color-only scan risk of Ledger or the editorial/content-site tone of Dossier · rationale: user explicitly evaluated all three and confirmed Manifest · revisit if user feedback after rollout says otherwise
- **Rollout scoped to Plan tab + `BlockPlanTable` first, not the whole app:** shared theme tokens (fonts, accent color, radius) update globally in `index.css`, but only `PlanTab.tsx`, `BlockPlanTable.tsx`, `StatusChip.tsx`/`status-colors.ts`, and `StatusBadge.tsx` — the same surfaces F87 touched — are migrated to the new visual language in this pass. Other tabs (Data Storage, ETL graph, Lineage, Docs, Explain, sidebar) keep the old shadcn-default look until a follow-up · rationale: smaller diff, faster to ship, validates the direction on real usage before an app-wide commitment · revisit: plan a follow-up rollout to remaining tabs once this lands
- **New brand accent color is separate from semantic status colors:** teal is the primary/accent brand color (buttons, active tab, links, focus); the existing semantic red/amber/green for risk/confidence/reconciliation status is unchanged and must not be conflated with the brand accent · rationale: preserves recognizable status semantics while giving the app a considered, non-generic identity · revisit never

## 2026-07-02 — Report section removed from Plan tab

- **Report not surfaced in the job detail UI:** The plain-English report section has been removed from PlanTab. The standalone Report tab in JobDetailPage is also commented out. The feature has no current UX home. · rationale: the Plan tab should focus on the migration assessment (verdict, stat cards, attention queue); a prose report belongs in a dedicated export or document flow that hasn't been designed yet. · revisit when planning a decision-ready report export (issue #32/#24) or a dedicated Report tab
- **Backend report generation remains intact:** `POST /jobs/{id}/doc`, `PlainEnglishAgent`, and the `report` / `non_technical_doc` fields on the Job model are untouched. The capability can be reactivated without backend changes. · revisit never (backend)

---

## 2026-06-29 — DataStorage Source/Target toggle + PK/FK visualisation

- **DataStorageTab toggle label is "Target" not "Migration":** Aligns terminology with the ETL tab (Source / Target). "Migration" was the original plan label but was renamed during implementation for consistency. · revisit never
- **DataFlowDiagram intermediate node clicks produce no sidebar navigation:** Intermediate (amber) nodes have no schema entry in the sidebar — `onTableSelect` returns early when no matching table is found. Silently ignored is correct UX here (no toast, no navigation). · revisit never
- **DataModelERD status bar is always visible (not conditional on edges):** Even with zero inferred relationships, the table count provides value and the absence of a relationship line is itself meaningful — users should know the ERD is intentional, not empty. · revisit never
- **PK/FK matching in `schema_utils.py` uses `.lower()` on column name:** `infer_pk_fk()` returns lowercased column sets; SAS column names are uppercase. The comparison was always `False` for real SAS data. Fixed at all three lookup sites (`is_pk`, `is_fk`, `fk_ref`). · revisit never

---

## 2026-06-25 — DataFlowDiagram two-tier ETL view

- **Data flow diagram shows all ETL-produced tables with two visual tiers:** Source nodes and step nodes removed — the diagram is a pure data lineage view. All datasets emitted by any pipeline step are nodes; `outputTableNames` prop (fed from DataStorageTab's registered schema tables where `libname === null`) drives classification: "output" (green) vs "intermediate" (amber). `pureInputs`/`pureOutputs` logic replaced by `producedByAnyStep` set. · revisit never
- **`outputTableNames` prop drives tier classification, not inclusion:** Every produced dataset appears; only the visual tier differs. "Final output" = registered in `data_schema` with `libname === null`. Everything else produced by ETL steps is "intermediate". This is the authoritative distinction. · revisit never
- **`_normalise_pipeline_step_names._resolve()` detects file extensions before splitting:** `split(".")[-1]` was returning the extension ("csv", "xlsx") not the dataset stem. Fixed: right side used for SAS `libname.table` notation, left side for file references; detected via `_file_exts` frozenset. · revisit never
- **Intermediate ETL tables are not deployed to Unity Catalog:** They exist as PySpark steps in the migration bundle but get no DDL or registered schema entries. Recommendation: materialise intermediates in a `staging` schema for migration validation — tracked as future feature `F-staging-materialise`. · revisit when planning migration validation workflow

---

## 2026-06-24 — ETL tab Target Blocks redesign

- **Target Blocks graph nodes show compact status cards, not inline block rows:** SAS construct names (PROC_IMPORT, DATA_STEP) displayed inside a Python-target graph confuse users unfamiliar with SAS. Block-level detail belongs in a side panel, not in graph nodes. Nodes now show only filename + block count + segmented green/amber/red bar. · revisit never
- **FileBlockListPanel uses rationale as primary label with `[SAS]` chip as secondary:** The LLM-generated rationale ("Import vital signs data") is meaningful to any user; the SAS construct type is traceability info only. Explicit `[SAS]` chip prevents the construct name from being mistaken for Python code. · revisit never
- **FileBlockListPanel sorts by urgency (Manual → Review → Pass):** Users opening a file's block list are most likely investigating a problem. Showing attention-requiring blocks first reduces scroll-to-find. · revisit never

---

## 2026-06-19 — DBX bundle fold + modularization

- **Same-table fold localized to bundle layer:** mutating `migration_plan` upstream would break the ETL/Plan/Lineage tabs which use it as the comparison baseline; fold is a bundle-rendering concern only. · revisit never
- **Fold order = `(source_file, start_line)`, not list position:** topo sort adds no edge between co-writers of the same table so positional order is unsafe; explicit sort by source location is the invariant. · revisit never
- **Multi-output block inside a fold chain emits NotImplementedError stub:** `result` is ambiguous when one block produces multiple tables and also participates in a fold chain; wrong code is worse than an honest stub with per-stage `# MANUAL:` comments. · revisit never
- **DLT modularized to one file per SAS source file:** mirrors the pipeline-steps view in the ETL tab; `dlt.read()` resolves globally across files within the same DLT pipeline so cross-file references are valid. · revisit never
- **Spark Job modules grouped by source-file subfolder `jobs/<stem>/<table>.py`:** cosmetic parity with DLT modularization; Databricks Jobs has no multi-library concept so grouping is directory-only. · revisit never

---

## 2026-06-18 — F76 intentional one-time rebaseline of the DLT bundle golden bytes

- **The F74/F75 DLT regression-lock golden bytes were never deploy-correct and are intentionally rebaselined in F76 (S-0):** the old `@dlt.table` functions bound inputs to `<var>_df` (the bare stem the portable code actually uses was never defined → NameError), read root inputs from a hardcoded `DATABRICKS_DATA_ROOT`/`/workspace/data` path, and never `return`ed (so `@dlt.table` materialised `None`). S-0 binds inter-block inputs by bare stem via `bind_inter_block_inputs(..., "dlt")` (`<stem> = dlt.read("<stem>")`), lets the portable block code read root inputs via its own `DATA_ROOT` (resolved from `ROSETTA_DATA_ROOT`, set in the pipeline `configuration`), and appends `return result`. The bundle YAML now also carries a `rosetta_data_root` variable + `ROSETTA_DATA_ROOT` pipeline config. The regression-lock tests were updated to the corrected bytes; the F74/F75 "byte-identical" assertions are a deliberate one-time break. · revisit never

---

## 2026-06-15 — F35 Data Storage tab design decisions

- **Data Model ERD shows output tables only:** Source SAS tables are input artefacts, not migration deliverables. Mixing them into the ERD dilutes the diagram's purpose. A notice strip explains the filter when source tables were removed. · revisit never
- **Data Flow keeps source nodes:** Unlike the ERD, Data Flow is a lineage view — hiding source nodes would make it meaningless. Source tables correctly appear as "SAS input" nodes showing where data originates. · revisit never
- **Dataset name normalisation at both write time and read time:** Worker normalises SAS logical names (work.dm) to file-basename equivalents (dm_raw) via _dataset_matches_file() after lineage is built. Backend applies the same pass at GET /jobs/{id}/lineage read time so existing jobs also benefit where data_schema is populated. Jobs with empty data_schema (pre-F34 jobs) cannot be normalised without re-running. · revisit never
- **Right panel differentiated by table type:** Source SAS tables show SAS metadata read-only (no migration state). Output tables in "not run" state show a proposed schema (column name + inferred type). Output tables post-migration show the source-vs-target diff view. · revisit never

---

## 2026-06-15 — F15 deterministic zero-pad / concat KEY derivation in codegen

- **Mechanical zero-pad/concat KEY derivation is now enforced deterministically from the SAS source, overriding the LLM output when cleanly parsed:** `parse_padded_concat_keys` recognises single-statement `target = catx('-', ...)` / `cats(...)`/`catt(...)` / `a || b || ...` assignments whose components are string literals, bare columns, or `put(var, zW.)` zero-pads; `render_padded_key_expr` builds the canonical PySpark (`F.concat_ws`/`F.concat` + `F.lpad(F.col("c").cast("string"), W, "0")`); `enforce_padded_concat_keys` APPENDS `<outvar> = <outvar>.withColumn("<target>", <expr>)` (Spark `withColumn` replaces, so append-override supersedes the LLM expression without a fragile nested-edit). Wired in all three agents immediately after `inject_declared_casts` and before `apply_mechanical_drift_guard`. Fixes the usubjid regression where `catx('-', studyid, put(siteid,z3.), put(subjid,z4.))` → `ADC-XYZ-001-003-0001` but the LLM emitted unpadded `...-3-1` · revisit never
- **Source-driven, never reference-driven — faithful translation, not golden-gaming:** pad widths come from the SAS `z3./z4.` source, never the reference data, consistent with the locked "never cast/shape to match ref" stance. The parser is conservative: ANY nested function beyond `put`, macro token (`&`/`%`), multi-statement RHS, or unbalanced parens/quotes skips that assignment entirely · revisit never
- **§20 prompt rule + mechanical drift guard remain the fallback for unparseable cases:** complex/multi-line/macro-laden concat expressions still fall back to the prompt + `apply_mechanical_drift_guard` confidence downgrade (no regression). For cleanly-parsed cases the appended `lpad`/`concat_ws` is present, so `check_mechanical_format_drift` no longer flags a deterministically-fixed block. Idempotent (identical override skipped) and no-op when the output var is unresolved. This is the durable form of "mechanical invariants belong in deterministic code, not prompt rules" · revisit never

---

## 2026-06-15 — F15 LLM join-key resolution for row_hash_diff (per-block)

- **An LLM may resolve the row_hash_diff comparison KEY, never the output:** when every non-`row_hash_diff` check passes but `row_hash_diff` fails, the inferred key is unique-but-wrong (the AE `(subjid,aestdtc)` swapped-pair case). `ReconKeyResolverAgent` proposes the correct business key from the failure detail + both schemas + raw SAS + deterministic per-column stats; the worker re-compares IN-PROCESS using the executor's already-returned `result_json` (pipeline NEVER re-executed, no translation attempt spent). The LLM only changes `ReconConfig.join_keys` — it cannot touch generated pipeline code, so golden-gaming is impossible. This is distinct from and consistent with the 2026-06-15 "NEVER auto-fix recon parity mismatches" rule: a key is a comparison lens, not a value · revisit never
- **This makes the recon VERDICT non-reproducible across runs — accepted tradeoff:** different LLM proposals could in principle yield different pass/fail, which sits against "same input → same output". It is compliant ONLY because (a) the LLM touches the key, not the code, (b) LLM-proposed keys are deterministically validated at EXACT uniqueness (==1.0) + zero nulls in BOTH frames before use (stricter than the 0.95 inference gate), and (c) the resolved key is PERSISTED so a given job's verdict is stable and inspectable. On exhaustion the failure is KEPT (human review) — the closest near-unique key is fed back as an LLM hint but NEVER auto-accepted (that would reintroduce the swapped-pair bug) · revisit never
- **Resolved key persisted via whole-dict merge into `job.files['__recon_config__']`:** `job.files` is an un-tracked JSON column, so in-place mutation is silently lost; persistence uses `update(Job).values(files={**job.files, "__recon_config__": json.dumps(...)})` preserving all other `__ref_*__` sentinels. This is a NEW mid-run `files`-mutation pattern (the `__refine_context__` precedent is a new-row insert, not a mutation). The refine child inherits the key because `POST /refine` copies parent `files` · revisit never
- **`BlockRevision.recon_checks` revived for ALL checks:** the column existed but was dead (only the disabled `_reconcile_initial_blocks` wrote it; live `_persist_initial_revisions` left it NULL). `GeneratedBlock` gains `recon_checks`; the F19 loop stores the final (possibly key-resolved) checks on `gb`; `_persist_initial_revisions` persists it. A key-resolved `row_hash_diff` pass carries `resolved_join_key`. No DB migration (column present). This also closes the latent gap where per-block check detail was never persisted for ordinary blocks · revisit never
- **`_execute_rereconcile` (skip_llm / human re-recon) is intentionally NOT wired to the resolver:** it uses the in-process `ReconciliationService` with no agent, so it will NOT resolve a new key — but it reads `recon_config` from `files`, so it BENEFITS from a previously persisted resolved key. Full-pipeline recon also stays on plain inference (per-block scope only for now) · revisit if full-pipeline key resolution is requested

---

## 2026-06-15 — F61 type-aware schema contract + full-pipeline recon hardening

- **Declared `.sas7bdat` types are baked in via a deterministic injector, not the LLM (F61):** `inject_declared_casts` post-processes generated code, adding `.withColumn(col, F.col(col).cast(...))` after each `toDF(lower)` line, sourced from `meta.readstat_variable_types` (string→`string`, else→`double`). The prompt section is *informational only* — the LLM never hand-writes the load cast (single deterministic author = byte-reproducible). Cast to the **source's** declared type, never the reference schema · revisit never
- **Recon type detection uses `not is_numeric_dtype`, not `is_object_dtype`:** pandas ≥2 / 3.0 infers a dedicated `StringDtype` for text columns, for which `is_object_dtype` is `False` — the original guard silently never fired. `is_numeric_dtype` negation is the version-robust discriminator. Date/ID coercion is gated by a parseable-fraction threshold over *non-blank* cells (sparse clinical date columns like first-AE-date are legitimately mostly null) · revisit never
- **Executor serializes result dates as ISO strings (`date_format='iso'`):** the pandas `to_json` default encodes `DateType` as epoch-millis, which recon misread as numeric SAS-days and overflowed. ISO matches the golden CSV and is the deprecation-recommended format. This was the true root cause of the `firstaedt` object-vs-numeric mismatch — every prior recon-side fix was treating corrupted serialized data · revisit never
- **NEVER auto-fix reconciliation *parity* mismatches with an LLM agent:** when the pipeline runs but numbers differ, agentic "fix until recon passes" rewards gaming the golden and can falsify correct translations. `trtdurd` this session proved it — the code was right, the golden fixture was stale. Agentic full-pipeline retry is acceptable ONLY for runtime crashes (attribute traceback → block, re-run that block's refine). Parity mismatches are surfaced for human review, not auto-repaired · revisit never
- **AMBIGUOUS_REFERENCE is self-healed deterministically in both exec paths:** prompt §5 sharpened to mandate `on=[...]` equi-joins (collapses duplicate keys at the source); as the guarantee, a bare→alias-qualified `F.col` rewrite runs in the worker `_safe_exec` retry loop AND a new bounded (3×) retry in the executor subprocess runner (executor must not import from `src/worker`, so the helper is duplicated). Converges naturally — once qualified, the same error finds nothing to rewrite · revisit never
- **Golden fixtures are regenerated from current raw inputs when stale:** test data is synthetic, so `adsl_expected.csv` TRTEDT/TRTDURD were rebuilt from the current `ex_raw.csv` via the exact `%m_first_dose` semantics rather than altering correct code to match drifted expectations · revisit never

---

## 2026-06-14 — F57/F59 macro expansion + SET/MERGE option parsing

- **Macro CALLS are expanded deterministically at parse time, before block extraction (F57):** `expand_macro_calls` runs inside `SASParser.parse` (two-pass: collect all defs across files, then expand each file) so datasets produced inside a macro body become real blocks. No LLM — reproducibility constraint. The legacy per-block `MacroExpander` (main.py) is left untouched; F57/F59 enhance only the parse-time path (no consolidation, no double-processing) · revisit never
- **Macro control flow is evaluated by a tokenizer + recursive-descent resolver, not regex (F59):** nested `%do/%end` and `%else` pairing are a balanced-bracket problem regex cannot solve; `%end` matched by depth counter, `%else` by recursion stack. `evaluate_condition` is a pure leaf (no `eval()`); numeric comparison iff both operands match `^-?\d+$` else case-sensitive string · revisit never
- **All-or-nothing macro resolution:** any construct that is not deterministically evaluable (`%do %while`/`%until`, `%sysfunc`/`%eval`, unresolved `&ref`, non-integer loop bound) raises `CannotResolveMacroLogic` and the macro is left unexpanded — never emit partial or guessed output (guards against wrong-but-runnable SAS). Bounded by `MAX_UNROLL=1000` and `_max_rounds=10` · revisit never
- **Cross-FILE `%global` propagation is out of scope:** `parse()` expands each file's source independently; threading a shared env across files raises file-ordering determinism concerns. Within-file `%global NAME=VALUE` propagation is supported (substituted across the source each fixed-point round) · revisit if a real pipeline needs cross-file macro globals
- **SET/MERGE/DATA dataset options break the input parser:** the `[\w\s.]` character class could not span `(in=indm)` options so `merge sdtm.dm(in=indm) ...` matched nothing → empty `input_datasets` → input-var normaliser never ran → `NameError`. Fixed by widening the regexes (non-greedy + DOTALL) and stripping balanced option parens in `_extract_names` · revisit never
- **PROC FORMAT user formats — FIXED (F60):** `value` maps are now extracted into a deterministic catalog (`format_catalog.py`), carried on `ParseResult`/`JobContext` like `libname_map`, and the referenced definitions are injected into the translation agents' prompts so the LLM renders `put(var, fmt.)` as `when/otherwise`. Extraction is deterministic + unit-tested; LLM application is consistent with the locked LLM-primary decision · revisit never
- **Router `_SimpleCopyHelper.is_simple` is a strict allowlist (F60):** a DATA step takes the no-LLM copy path ONLY if every statement is `DATA`/`SET`/`KEEP`/`DROP`/`RUN`. The prior blocklist (absence of `IF/DO/MERGE/RETAIN/ARRAY/OUTPUT`) misclassified `x = put(...)` assignments as simple and dropped them. Any assignment/`put()` now routes to the LLM agent · revisit never
- **Mechanical translation invariants belong in deterministic code, not just prompt rules — open principle:** the column-lifecycle bug (`UNRESOLVED_COLUMN: studyid`) and the join-key cast-back drift (`subjid/siteid` numeric→string) both stem from the LLM dropping a soft `SHARED_TRANSLATION_RULES` rule under load. Added a column-lifecycle/ordering rule this session as a stopgap; the durable fix (type-aware schema contract from authoritative `.sas7bdat` metadata, enforced as auditable casts baked into delivered code) was scoped then deferred by the user. Cast to the **source's** declared type, never to the reference schema (respects "never cast to match ref") · revisit when prompt-only hardening proves insufficient again

---

## 2026-06-13 — F35 remediation runbook design

- **Remediation guidance is rule-based, not LLM-generated:** `runbook_templates.py` maps block_type + strategy + detected_features to curated step lists; no new agent or token cost; honors the "same SAS input → same output" reproducibility rule · revisit if clients need block-specific tailored guidance (hybrid LLM option documented in plan)
- **Runbook placed as a collapsible panel in Plan tab:** Follows the locked "Plan tab is the single decision surface" decision; mirrors the F34 ScopingSummaryPanel pattern (lazy-loaded, Copy-as-Markdown) · revisit never
- **Runbook inclusion filter = criticality in (critical, high):** Equivalent to existing `human_review_required` flag; targets the ~20% that can't be safely auto-migrated; excludes translated_with_review and unknown-confidence blocks that are merely flagged for review · revisit if clients want a broader export
- **detected_features with `&`-prefixed items are macro variable refs, not pattern names:** The MigrationPlannerAgent is instructed to put macro parameter names (e.g. `&in`, `&out`) into detected_features for manual-strategy blocks; `why_risky()` now detects the `&` prefix and renders "Block uses macro parameters as dataset/library names" rather than dumping raw identifiers · revisit never

---

## 2026-06-12 — F34 Phase 2 column schema

- **Phase 2 must include SAS source parsing for column schema:** pyreadstat covers uploaded `.sas7bdat` files; derived datasets (sdtm_dm, adsl_output) only get column types from SAS source declarations (LENGTH, FORMAT, ATTRIB statements); without this, derived tables show no column data at all · revisit never
- **CSV columns must show "Unknown" not "Number":** Defaulting to "Number" when `sas_type` is empty string is wrong — USUBJID, ARM, SEX etc. are clearly strings; "Unknown" is the honest fallback when no SAS metadata is available · revisit never

---

## 2026-06-12 — F34 Data Storage tab design

- **Data Storage tab is a single feature covering all 3 phases:** Schema browser + column type extraction + ERD + DDL are one feature with 3 internal dev phases — not separate features; coherent design from the start · revisit never
- **Target-agnostic ANSI SQL DDL first:** DDL generation uses generic SQL types (TEXT, DATE, TIMESTAMP, DECIMAL, DOUBLE PRECISION, BIGINT); user-selectable platform (Databricks Delta, Snowflake) deferred to backlog · revisit after first client feedback
- **Schema overrides in user_overrides, machine data in migration_plan:** `libname_map` and `data_schema` are worker-generated and stored in `migration_plan`; user edits (target schema names, column type overrides) stored under `schema_overrides` key in `user_overrides` — consistent with existing human/machine data separation · revisit never
- **DATETIME format checked before DATE in semantic type mapping:** SAS `DATETIME` format starts with `DATE`, so DATETIME regex must be tested first to prevent false Date matches · revisit never

---

## 2026-06-11 — F33 ETL tab design

- **ETL tab is review-only, no execution controls:** Run migration / pipeline stages are execution concepts; the ETL tab shows the proposed migration state for human review only — mixing execution and review would confuse users about what they're doing · revisit never
- **ETL graph filters to .sas nodes:** Data/CSV files belong on the Data Storage tab; ETL orchestration view shows only SAS source files · revisit never
- **Sticky accept footer removed from Plan tab:** Two accept buttons with different labels ("Accept migration" in header vs "Accept (not recommended)" in footer) caused confusion — removed the footer, single CTA in header · revisit never
- **Accept gating deferred:** No programmatic gate preventing accept before all blocks reviewed — deferred until real client usage data shows whether the Mark as verified workflow is actually used before acceptance · revisit after first client feedback

---

## 2026-06-11 — F30/F31/F32 implementation approach

- **PII scanner uses token-based word-boundary matching (not substring):** Column names split on underscore and CamelCase boundaries then matched token-by-token against a PII signal frozenset — prevents `TOPZIP` → `zip`, `DOBERMAN` → `dob` false positives that substring matching produces · revisit if real client data surfaces false negatives or positives
- **Missing dependency detection uses allowlist (not blocklist):** Extract all `%word` tokens, filter out a comprehensive SAS built-in frozenset; what remains is assumed user-defined macro — allowlist is safer because the SAS built-in set is finite and enumerable, while user macro names are unknown · revisit never
- **No Alembic migrations for F30/F31/F32:** All three features store new data in the existing `job.migration_plan` JSON column — no schema change needed; old jobs silently return empty lists/arrays via Pydantic defaults · revisit if performance at scale becomes a concern

---

## 2026-06-08 — F29 Plan tab layout and PR #34 repurposing

- **PR #34 not merged; design repurposed into F29:** MigrationPreviewPage (pre-migration assessment) is superseded; verdict strip, attention cards, scope summary, and sticky accept footer are absorbed into Plan tab (F29) using only existing API data · revisit never
- **Reads/produces, missing deps, PII deferred:** All three require backend schema additions not in F29 scope; deferred to a follow-on backend feature · revisit when sprint capacity allows
- **Single "Needs attention" section with Cards/Table toggle:** Replaces separate attention card list + review queue table — serves PM (card view) and tech lead (table view) without redundancy · revisit never
- **Sticky accept footer:** Accept button pinned to bottom of Plan tab content area — always accessible while user reviews evidence; verdict strip at top states the recommendation, sticky footer closes the loop · revisit never

---

## 2026-06-05 — Plan tab as single decision surface (F29)

- **EvaluationTab content absorbed into Plan tab:** Summary cards, full review queue columns (source file, self-confidence, verified confidence, reconciliation, human review required, blast radius), per-file breakdown, and confidence info dialog all move into Plan tab — EvaluationTab becomes a deletion candidate in #46 · rationale: the user must be able to make a confident accept/reject migration decision without navigating away from the Plan tab · revisit never
- **GitHub issue queue is the priority source over local backlog:** When GitHub issues and local backlog conflict, GitHub wins · rationale: issues are visible to the whole team; backlog is Claude-internal · revisit never

---

## 2026-06-03 — No Co-Authored-By in commits

- **Never add `Co-Authored-By: Claude` to any commit:** The default system instruction appends it; the git-committer skill explicitly blocks it. The skill rule is the project-level override and always wins. One commit (c3b6ad2, feat(F25)) slipped through when the skill was not enforced — it is merged to main and not worth rewriting. All commits from 2026-06-03 onward must be clean · rationale: user does not want Claude appearing as a GitHub contributor · revisit never

---

## 2026-06-02 — 5-tab chevron UI restructure (issues #40–47)

- **New tab structure: Plan → ETL → Data Storage → BI → AI:** Replaces current Plan / Editor / Report / Lineage / History / Evaluation tabs; chevron shape from wireframe (pending on #40) · rationale: aligns UI with the migration pipeline stages rather than tool functions · revisit if wireframe changes scope
- **Plan tab absorbs Evaluation + Report:** Block table (with Criticality column) is primary content; Criticality review queue sits above as a collapsible panel expanded by default; Report is a collapsible panel collapsed by default; EvaluationTab summary cards fold into the existing job summary header · revisit never
- **ETL tab repurposes Lineage as primary canvas:** Lineage DAG is the main view; clicking a node opens the block's SAS↔Python code editor in a slide-in panel; standalone Editor tab is retired · rationale: keeps spatial/dependency context visible while editing; unifies "where does this block fit" with "what does it do" · revisit if DAG performance is poor on large jobs
- **BI and AI tabs are placeholders:** No functional content until scope is defined; empty state only · revisit when stakeholder requirements land
- **Implementation blocked on wireframes:** #40 (chevron shell), #41 (Plan tab), #42 (ETL tab) must not be started until wireframes are attached to the issues · revisit when dev X uploads wireframes

## 2026-06-02 — 5-tab chevron implementation approach

- **Tab routing uses query params (`/jobs/:id?tab=plan`):** One route handles all 5 tabs; deep-linking and back-button work without defining 5 path segments; syncs shadcn Tabs `value` with `useSearchParams` · rationale: path segments require router restructure; in-memory loses deep-linking entirely; query params are minimal change with full capability · revisit never
- **Migration strategy: additive then remove:** New chevron shell (#40–45) is built and verified first; legacy tab bar is hidden (not deleted) once shell is wired; legacy components removed in #46 as a separate PR · rationale: issues are already sequenced this way; keeps rollback to a one-line change if the shell breaks; avoids a single enormous PR · revisit never
- **History tab folds into Plan tab as a collapsed panel:** Job-level audit timeline moves to a collapsible "Migration history" panel at the bottom of Plan tab (collapsed by default), consistent with the Report panel pattern; per-block revision history (clock icon in BlockPlanTable) remains in place · rationale: history is most relevant alongside the plan it reflects; dropping it loses audit trail visibility important for regulated enterprise migrations · revisit never
- **#39 audit gates #43 scope:** Data Storage tab (#43) must not be planned until #39 (SAS metadata audit) confirms what the parser already extracts; avoids writing a frontend plan that depends on non-existent backend data · revisit never
- **#39 audit complete — #43 now unblocked (2026-06-02):** Audit confirmed partial extraction: LIBNAME path mapping, block boundaries, %LET/%MACRO, and column names from `.sas7bdat` are present; column labels/formats/types, PROC FORMAT value mappings, INFILE/INPUT layouts, CALL SYMPUT, and LIBNAME engine type are absent. Gaps documented as Tier 1/2/3 items in backlog and `docs/input-prerequisites.md`. #43 may be planned against what is currently available with explicit placeholders for unextracted fields · revisit never
- **Tab key strings are kebab-case:** `plan`, `etl`, `data-storage`, `bi`, `ai` — used as `?tab=` query param values; kebab-case is the URL convention; `data-storage` preferred over `datastorage` (readability) and `data_storage` (underscore unconventional in query params); strings do not conflict with legacy tab keys during the additive migration phase · revisit never
- **Full-page editor route `/jobs/:id/editor` is kept, not retired in #47:** Slide-in panel in ETL tab serves spatial context (DAG + code together); full-page route serves focus mode (distraction-free editing of dense blocks); these are distinct use cases. Entry point moves from Plan tab View Code dialog → ETL tab slide-in panel maximize button; return `?tab=` parameter updated to `etl`; route itself is unchanged. #47 removes the legacy tab bar, not this page · revisit never

---

## 2026-06-01 — F25 criticality design

- **`_blast_radius_map` bug fixed — source_block_id not source_file:** `cross_file_edges` dicts produced by the lineage enricher use `source_block_id` / `target_block_id` / `shared_dataset` keys; the old function read `source_file` so blast_radius was always `None`; fixed to key on `source_block_id` giving block-level counts · revisit never
- **Criticality is mixed signal (strategy + confidence + blast_radius), not pure blast_radius:** `critical` when strategy==manual OR effective_band==very_low; `high` when band==low OR recon==fail OR blast_radius≥3; `normal` for medium/unknown band; `low` for high band · rationale: pure blast_radius would give 0 to all single-file jobs; mixing translation quality into criticality is the most actionable signal for reviewers · revisit if users request a purely impact-based tier
- **Criticality computed at read time, not stored:** no DB migration needed; always reflects current blast_radius and recon state · revisit if read-time computation becomes a performance concern at scale

---

## 2026-05-18 — SAS editor tokenizer design

- **sasFunctions require `(` lookahead:** Monarch rule split into two — `(?=\s*\()` rule checks `sasFunctions` first (only fires when token is immediately followed by `(`); second rule checks `keywords` only; prevents `sum`, `mean`, `n`, `min`, `max`, `count` etc. from highlighting blue when used as variable names · revisit if stateful per-PROC tokenizer is ever implemented
- **PROC options as global flat keywords:** common PROC options (`NOPRINT`, `NODUPKEY`, `NWAY`, etc.) added to the keyword array rather than a stateful per-PROC tokenizer; false positive risk is negligible in practice (these tokens are never used as variable names); stateful approach left as future Option B if anyone raises a false positive · revisit never unless false positives reported
- **Function color = keyword color in SAS themes:** `keyword.function` uses same blue as `keyword` (`#0070C0` light / `#569CD6` dark); SAS Studio Enhanced Editor does not visually distinguish function calls from statement keywords · revisit never

---

## 2026-05-04 — cumulative execution, planner correctness, post-run risk design

- **Cumulative code over Parquet session cache:** each block is executed with all prior blocks' code prepended; Parquet cache silently left gaps when upstream blocks crashed mid-execution leaving no save; cumulative code is always correct regardless of upstream crash · revisit never
- **Parser `block_type` is authoritative in `_build_migration_plan`:** LLM's returned `block_type` is overridden by the parsed `SASBlock.block_type` keyed by `block_id`; the prompt enum was incomplete (missing PROC_IML etc.) causing UNTRANSLATABLE misclassification · revisit never
- **Post-run risk+rationale enrichment (design agreed, not yet implemented):** `risk` and `rationale` on `BlockPlan` to be recomputed after translation using recon results + confidence band; rule-based, no LLM call; re-persists `job.migration_plan`; pre-run planner values are initial estimates only — recon pass + high conf → low; recon fail → high; no recon + low conf → high · revisit never

---

## 2026-06-15 — F56 post-run risk enrichment implemented (extends 2026-05-04 design)

- **Two-column storage, not in-place re-persist:** pre-run planner estimate stays untouched in `migration_plan`; enriched plan goes to a new `migration_plan_post_run` JSON column (Alembic 019). Consumers read via `effective_migration_plan(job)` = post-run when present, else pre-run (fallback for older jobs). Rationale: preserves the audit trail of the original estimate vs. the post-run revision · revisit never
- **Enrichment also overwrites `confidence_band` (post-run band) and recomputes `MigrationPlan.overall_risk`:** extends the 2026-05-04 rule set (which only covered per-block `risk`/`rationale`) so the displayed confidence agrees with the rationale text, and the summary risk stays consistent with the upgraded per-block risks (HIGH if any block HIGH, else MEDIUM if any, else LOW) · revisit never
- **Enrichment is best-effort (Step 10d, try/except):** a cosmetic post-run enrichment must never fail an already-successful job; on exception it logs and continues · revisit never
- **Trust-report / criticality (`needs_attention`, `_criticality`) deliberately NOT swapped to post-run:** they already compute from `strategy` + `confidence_band` + `reconciliation_status`, so they are post-run-aware without reading `bp["risk"]`. `recommended_review_blocks` / `risk_explanation` also not recomputed (no signal change warrants it) · revisit if those signals diverge from post-run risk

---

## 2026-05-03 (session 3 — recon grouping fixes, retry loop, session cache, parser enhancements)

- **`_build_recon_groups` direct-match only:** strip libname prefix from `output_datasets` before stem match; no BFS backward traversal — upstream blocks produce different shapes and must not be reconciled against the terminal output ref · revisit never
- **`_reconcile_initial_blocks` (step 11) disabled:** was redundant and harmful — ran job-level ref against every intermediate block post-translation; per-block recon in `_translate_blocks` handles this correctly · revisit never
- **Session cache uses `/tmp`:** `/workspace/data` is mounted read-only in executor; session Parquet cache lives at `/tmp/rosetta_cache/<id>/`; Spark init always included when session_dir set so `spark.read/write.parquet` available · revisit never
- **Translation exception retries:** `except Exception` in retry loop now `continue`s (not `break`s) on attempts 1–2, injecting error as risk_flag; `block_done status=error` emitted so popup shows red immediately · revisit never
- **PySpark-only prompt rule:** `SHARED_TRANSLATION_RULES` explicitly forbids pandas and casting columns to match ref schema — PySpark types are authoritative · revisit never
- **SAS parser enhancements:** MacroDef, filename_map, PROC IML/FORMAT dedicated extractors, DROP/KEEP/WHERE/OUTPUT/ARRAY fields on SASBlock — provides richer context to translation agents · revisit never

## 2026-05-03 (session 2 — per-block recon cache, popup UX overhaul, column casing)

- **Executor DataFrame session cache via Parquet:** per-block recon passes `session_dir` to executor; after each successful run, all non-private DataFrames saved to `session_dir/<name>.parquet`; next block's code gets a load-snippet prepended — avoids re-running N-1 blocks for block N; cache cleaned up after translation loop · revisit when blocks produce large DataFrames (100k+ rows) or PySpark DataFrames (can't `.to_parquet` without `.toPandas()`)
- **`_build_recon_groups` fallback removed:** per-block recon now ONLY fires when a block's output_dataset specifically matches an uploaded data file stem; job-level ref applies only to `pipeline:full` final run — prevents comparing intermediate blocks against the wrong (final output) reference · revisit never
- **Column name normalization: two-layer defence:** (1) LLM prompt `SHARED_TRANSLATION_RULES` Rule 2 mandates `toDF(*[c.lower() for c in df.columns])` after every file read — fixes at source; (2) `recon.py` normalizes both ref and actual to lowercase before checks — defensive guard for user-uploaded uppercase ref CSVs · revisit never
- **`pipeline:full` final recon run in `_translate_blocks`:** after all blocks complete, a fresh full-pipeline execution (no session cache) runs against the job-level ref and emits `block_start`/`recon_result`/`block_done` SSE events; displayed as `PipelineSummaryBanner` in LiveTraceDialog · revisit never
- **LiveTraceDialog toggle UX:** `expanded` state uses `userToggled: boolean | null` — `null` means "follow data" (auto-expand when recon arrives), non-null means "user chose" (override); prevents auto-expand from permanently locking the row open · revisit never

## 2026-05-03 (session — recon popup, UNRECOGNIZED rename, per-block recon wiring)

- **Per-block recon uses `_build_recon_groups`:** single final-output ref file must NOT be used for intermediate blocks — each block maps to its own uploaded reference file via output_datasets → context.data_files stem match; fall back to job-level ref for terminal blocks; blocks with no outputs skipped · revisit never
- **`_reconcile_initial_blocks` emits `recon_result` + corrective `block_done` trace events:** step 11 runs post-translation while SSE stream still open; second `block_done` overwrites first optimistic "pass" in frontend groupMap · revisit never
- **UNTRANSLATABLE → UNRECOGNIZED everywhere:** enum value, frontend types, generated comments, test assertions — consistent signal that a block was not recognised, not that translation was attempted and failed · revisit never
- **Amber attention strip removed from PlanTab:** replaced by per-block strategy badge coloring (pass=green, fail=amber, manual=red, pending=blue) · revisit never
- **`docker-compose.override.yml` bind-mounts `src/worker`:** rebuilds are never needed for worker code changes; `docker compose restart worker` is sufficient · revisit never

## 2026-05-03 (session — join fixes, confidence/status overhaul, SAS highlight)

- **Join key type-save/restore:** save `_type = df.schema[col].dataType` before normalising to string, restore with `.cast(_type)` after join — generic, works for all Spark types, no hardcoded `cast("long")`; scoped to identifier/key columns only · revisit never
- **`effective_confidence_band` in trust report read layer:** planner's `confidence_score` is audit-trail; `effective_confidence_band` computed at read time — `pass` upgrades to at least `medium`, `fail` downgrades, no recon keeps LLM estimate · revisit never
- **Two-phase job DB commit (10a/10b):** status + code written immediately after recon; doc + lineage after best-effort enrichment — eliminates 30–60s UI lag · revisit never
- **Baseline recon status from `exec_ok`:** `_persist_initial_revisions` writes `"pass"`/`"fail"` from translation loop — every translated block gets a status immediately; ref-based recon upgrades it when available · revisit never
- **MigrationPlannerAgent must output `confidence_score`:** was defaulting to 1.0 silently; now in JSON schema with guidance thresholds; default 0.5/"unknown" · revisit never

---

## 2026-05-01 (session — F20 Stream A: live trace popup)

- **JobTrace as append-only audit table:** trace events written by worker via `TraceEmitter` (independent short-lived sessions, never raises); SSE endpoint polls `job_traces` by `(job_id, id)` composite index at 0.5s interval — keeps backend stateless and avoids WebSocket complexity · revisit never
- **Cancel check uses fresh session:** `_translate_blocks` cancel check opens a new session via `session_factory` instead of calling `session.refresh(job)` on the outer long-lived session — the Job object becomes detached/expired after LLM calls; fresh `get()` by PK is safe · revisit never
- **Agent thinking stream deferred:** real LLM reasoning tokens are Claude-only (extended thinking); model-agnostic structured `thinking` events (agent name, block type, attempt context) chosen instead — deferred to next session · revisit never

---

## 2026-04-28 (session — rawdir_customers root-cause fix + F19 plan)

- **`block_output_stems` uses full `context.blocks` (not `windowed.blocks`):** `windowed_context` correctly narrows the context to a single block for LLM prompt scoping, but the upstream output variable name map must see all job blocks — these two concerns are now separated in all three `_build_prompt` functions · revisit never
- **Debugging discipline:** when a bug persists across multiple fix attempts, add targeted DEBUG logging at every pipeline stage (prompt construction → LLM output → post-normalise → assembly) before changing any logic; confirm root cause via log evidence before patching · revisit never

---

## 2026-04-27 (session — Executor runtime fixes: data_dir, xlsx, output_var, file_count)

- **Per-job upload subdir:** non-SAS files now saved to `/uploads/<job_id>/<basename>` instead of `/uploads/<job_id>_<basename>`; enables a single `data_dir` param to resolve all file paths without per-job volume magic · revisit never
- **`data_dir` executor param:** executor rewrites `/workspace/data/` at execution time using the job-specific directory; generated code stays portable (always `/workspace/data/<basename>`); rewrite happens in `runner.py` before subprocess · revisit never
- **`normalise_output_var` / `normalise_output_var_in_code` in `agents/shared.py`:** single source of truth for libname→stem normalisation; handles both dot form (`rawdir.customers`) and underscore form (`rawdir_customers`); all three translation agents delegate both the code-body rewrite and the `output_var` field correction here · revisit never
- **PROC IMPORT included in `all_block_outputs`:** removed the `_file_io_types` exclusion — PROC IMPORT outputs are renamed to stem-only by the agent renamer, so downstream prompts must show stem-only names to match the runtime variable · revisit never

---

## 2026-04-27 (session — Executor NameError root-cause fix)

- **Inter-block vs external-source variable naming in prompts:** transform block outputs (DATA_STEP, PROC_SQL, PROC_IML, etc.) are named stem-only in agent prompts; PROC_IMPORT/PROC_EXPORT outputs keep `libname_table` underscore form — applied consistently across all three agents · revisit never
- **Topo sort tiebreaker (Kahn's + min-heap):** `_topological_sort` uses Kahn's algorithm with a `(source_file, start_line)` priority queue instead of `nx.topological_sort`; ensures unconnected blocks (PROC_IML has no `DATA=`/`OUT=`) retain natural SAS file order. `nx.lexicographic_topological_sort` not available in networkx 3.6.1 · revisit if networkx upgraded
- **PROC IMPORT path convention:** generated code always uses `/workspace/data/<basename>` — basename extracted from SAS `DATAFILE=` value, macro-expanded prefix stripped. Executor volume mounts uploads at `/workspace/data/` · revisit never

---

## 2026-04-26 (session — Codegen/executor fixes)

- **Output variable naming convention:** output dataset variables use TABLE STEM ONLY (no libname prefix) — `DATA outdir.foo` → Python var `foo`; input datasets keep full `libname_table` form since they are pre-loaded. Rationale: prevents agents from referencing the output as if it were an input. · revisit never
- **`build_context_section()` removed:** was dead code (never called by any agent); log context now injected inline in each agent's `_build_prompt()` · revisit never
- **`result` as canonical executor output variable:** `assemble_flat()` appends `result = <output_var>` so the executor result-capture snippet can find it reliably via `globals().get('result')` · revisit never

---

## 2026-04-25 (session — Agentic pipeline context + Editor UX polish)

- **`manual_ingestion` is not untranslatable:** PROC IMPORT and similar I/O blocks have clear Python equivalents (`pd.read_csv`); they get `is_untranslatable=False`, `confidence_score=0.7`, and a `# TODO: verify delimiter and encoding` comment · revisit never
- **Absolute disk path in `manual_ingestion` stub:** the uploaded file's absolute path (sentinel `disk_path`) is used so the generated code is immediately runnable locally; relative project path is a post-migration concern · revisit when executor sandbox path mapping is clarified
- **`build_context_section()` shared utility:** a single function in `shared_context.py` renders the project context prompt section from `JobContext.data_files` and `libname_map`; all agents call it identically; adding a new context field requires changing only this one function · revisit never
- **DATA_FILE lineage nodes use `inferred: True` edges:** consistent with existing cross-file inferred-edge convention; frontend uses the `inferred` flag to style edges differently · revisit never
- **`_translate_blocks()` must pass `block_plan` per block:** migration planner strategy was being computed but discarded — root cause of PROC IMPORT staying UNTRANSLATABLE despite correct plan; fixed via `block_plan_map` dict keyed on `"{source_file}:{start_line}"` · revisit never

---

## 2026-04-24 (session — SAS EG editor UX + executor microservice)

- **`executor` microservice (new Docker service, port 8001):** generated Python runs in a subprocess sandbox inside a separate container rather than `exec()` in-process; isolates execution, enables cloud scaling, and exposes a `POST /execute` HTTP endpoint reusable by worker and backend · revisit when adding SAS execution support
- **Shared `uploads` volume between `backend` and `executor`:** reference files (.csv, .sas7bdat) uploaded by the user must be readable by the executor at the same absolute path; named Docker volume `uploads` mounted at `/uploads` in both services · revisit never
- **`RemoteReconciliationService` with graceful fallback:** worker delegates recon to executor over HTTP; `ConnectError`/`TimeoutException` return `{"checks": []}` and log a warning rather than failing the job — executor unavailability is non-fatal · revisit never
- **Bottom panel always-visible split (SAS Studio layout):** execution output, log, output data, and history are shown in a persistent resizable bottom panel (vertical `ResizablePanelGroup`) instead of a slide-in overlay; matches SAS Studio UX familiar to SAS users · revisit never
- **`translate_best_effort` strategy is dead:** defined in the enum but absent from the migration planner prompt — LLM never assigns it; needs to be either added to the prompt with a definition or removed · revisit next session
- **`manual_ingestion` stub is identical to `manual`:** `StubGenerator` ignores strategy — both produce `# SAS-UNTRANSLATABLE`; `manual_ingestion` was supposed to emit a `pd.read_csv()` scaffold · fix next session
- **`auto_verified` counter always 0:** `verified_confidence` field is never written by any agent; `auto_verified` should derive from `reconciliation_status == "pass" AND confidence in (high, medium)` · fix next session

## 2026-04-24 (session — Explain overhaul)

- **ExplainAgent 3-layer prompt composition:** base + mode-specific + audience-specific sections composed at construction time into a 4-agent cache; adding a new mode or audience requires only a new dict entry — revisit never
- **`_persist_messages` must own its own DB session:** FastAPI SSE request-scoped sessions are closed before `asyncio.create_task` fire-and-forget tasks complete; all future background persistence tasks must open their own `AsyncSessionLocal()` — revisit never
- **Worktree agents must not be used for implementation on branches with uncommitted work:** worktree agents clone a clean HEAD, losing all uncommitted changes in the working tree; always commit staged work before delegating to a worktree agent, or use the main tree agent with explicit file paths — revisit never (process change)
- **`mode='sas_general'` replaces `'upload'`:** "upload" described the mechanism, not the intent; migration 013 backfills all existing rows; frontend and backend literals updated atomically — revisit never

---

## 2026-04-19 (session 18 — F3 proposed/accepted, S-BE5/BE6, UI fixes)

- **`jobs_status_check` constraint expanded to include `proposed`/`accepted`:** migration 008 drops and recreates the constraint to allow new statuses before running the UPDATE · revisit never
- **`done` rows migrate to `proposed` (not `accepted`):** `done` was implicit acceptance but with no review performed; landing in `proposed` gives the user a chance to explicitly accept or refine · revisit if historical data needs different treatment
- **`"done"` kept as a frontend legacy `JobStatusValue`:** old worker images still write `"done"` between deploys; frontend maps it to amber "Under Review" and treats it as clickable/navigable · revisit when all environments rebuild
- **ReconciliationService skips execution when no reference data supplied:** running generated code in a sandbox with no input data was always failing and reporting a false `execution: fail` check · revisit never
- **`skip_llm` flag + `trigger` column for versioning:** `PUT /python_code` sets `skip_llm=True` and `trigger="human-rereconcile"`; `POST /refine` spawns a child job with `trigger="human-refine"`; allows the History tab to distinguish agent vs human changes · revisit never
- **History tab walks `parent_job_id` chain:** linear parent chain enables full version history without a separate events table; siblings (branches) are collected via a second query on parent IDs · revisit if branching history is needed
- **Refine context injected as `__refine_context__` sentinel in `job.files`:** avoids adding more DB columns while keeping prior code and hint available to the worker prompt; sentinel is stripped from sources display · revisit never

---

## 2026-04-23 (session 23 — Plan tab UX overhaul)

- **View Code dialog layout:** unified full-width toolbar row + identical-height panel header row (grid-cols-2) above the editors — eliminates SAS/Python vertical misalignment without JS measurement; `border-border` used throughout for theme-agnostic separators · revisit never
- **Confidence default fix location:** applied at StubGenerator and migration_planner (the two write paths) rather than at the API read/serialisation layer — ensures DB values are correct for all new jobs from the point of the fix · revisit never

---

## 2026-04-22 (session 21 — F4 confidence-refine-history)

- **`TranslationStrategy.TRANSLATE_BEST_EFFORT` added to StrEnum:** was referenced in F4 plan but missing from the model; added alongside TRANSLATE, TRANSLATE_WITH_REVIEW, MANUAL_INGESTION, MANUAL, SKIP · revisit never
- **block_id format normalised to basename-only (`"file.sas:12"`):** avoids URL path encoding issues with directory separators; client always `encodeURIComponent()` before URL interpolation · revisit never
- **Block revisions created only on explicit refine (not on job completion):** initial agent output is already captured by `job_versions[tab=editor]`; first refine inserts revision 1 (prior) + revision 2 (new) · revisit never
- **Trust report returns 200 with partial data when lineage unavailable:** `blast_radius: null` per block + `lineage_available: false` flag; no 202 polling — degrades gracefully · revisit never
- **409 Conflict on refine when job is accepted:** both whole-job (`POST /jobs/{id}/refine`) and block-level (`POST /jobs/{id}/blocks/{block_id}/refine`) return 409 when `accepted_at IS NOT NULL` · revisit never
- **`diff_vs_previous` computed in FastAPI route handler:** both old and new code available at insert time; uses `difflib.unified_diff`; worker has no access to prior revision · revisit never
- **`verified_confidence` stored under `job.lineage["block_confidence"]`:** piggybacks on existing schemaless JSON column; no DB migration needed; backward-compatible (old jobs lack the key) · revisit never
- **Refine dialog: user notes are primary input, injected first into LLM context:** user-authored instructions take precedence over auto-generated hints; injected as leading `risk_flags` entry · revisit never

---

## 2026-04-23 (session 22 — UI polish, View Code dialog, Upload→Dialog, PATCH /python)

- **Upload page promoted to Dialog on JobsPage:** reduces nav clutter; upload is a sub-action of "Migrations", not a top-level destination · revisit never
- **`PATCH /jobs/{id}/blocks/{block_id:path}/python` creates revision 1 when no prior revision exists:** uses defaults (`strategy="translate"`, `confidence="medium"`) rather than 404; any block is editable regardless of agent history · revisit never
- **SAS source in View Code dialog via `getJobSources`:** reuses existing endpoint mapping `source_file` → full SAS content; no new DB columns · revisit never
- **`revisions[0]` is the latest revision (backend returns `revision_number DESC`):** fixed bug where code was reading `revisions[length-1]` (oldest) instead of `revisions[0]` (newest) · revisit never

---

## 2026-04-22 (session 22 — FE9 ExplainPage)

- **ExplainPage backend is stateless:** frontend owns the accumulated `messages` array and sends it on each request; avoids session storage for an ephemeral chat feature · revisit if multi-turn context management becomes complex
- **LLM called inline in backend process (not worker queue):** explain questions need to feel synchronous; worker queue polling latency is inappropriate for chat; backend already imports worker agents · revisit if LLM calls become slow enough to time out the HTTP request
- **Separate `/explain` and `/explain/job` endpoints (not one unified endpoint):** multipart form data and JSON body cannot be cleanly unified; different validation and auth requirements; keeps route logic simple · revisit never
- **Code blocks in chat rendered as read-only Monaco editors:** user preference over styled `<pre>` blocks; consistent with editor components used elsewhere in the app · revisit never

---

## 2026-04-21 (session 20 — LineageEnricher pipeline-level extension)

- **`LineageEnricherAgent` max_tokens raised 8k → 16k:** 9-field JSON output (5 new fields) can exceed 8k for multi-file SAS projects; conservative doubling; revisit if latency becomes a concern
- **New lineage fields stored in existing schemaless JSON column — no migration:** `Job.lineage` is PostgreSQL JSON (nullable); new fields merge in via `{**lineage_data, **enriched.model_dump()}`; backward-compatible (old jobs simply lack the new keys) · revisit never
- **React Flow `NODE_TYPES` must be module-level constant:** if defined inside a component, React Flow remounts all nodes on every parent re-render; all custom node type registrations are at module scope · revisit never

---

## 2026-04-21 (session 19 — F5 bug-fix sweep)

- **TipTap switches to native HTML mode, `tiptap-markdown` dropped:** `@tailwindcss/typography` is absent so `prose` classes did nothing; extension's `html: false` mode mangled headings. Native HTML + `marked` for load + `getHTML()` for save is simpler and fully functional. Stored `content.doc` in versions saved after this session will be HTML, not raw markdown · revisit if markdown round-trip fidelity becomes a requirement.
- **`Tabs` component now supports controlled mode (`value`/`onValueChange`):** the original component was uncontrolled-only; `JobDetailPage` was passing controlled props that were silently ignored, disconnecting `activeTab` state from the visible tab entirely · revisit never.
- **Shadcn `Select` (Base UI variant) replaces native `<select>`:** `@base-ui/react/select` is already in the dependency tree; provides consistent styling and accessible keyboard behaviour · revisit never.

---

## 2026-04-19 (session 17 — F2-improvements backend: models, agents, codegen, API)

- **Two-phase refinement replaces `_MAX_RETRIES` while-loop:** explicit two phases (translate all → reconcile → if fail: re-translate affected block only) is predictable and equivalent to the old max-2-retry limit; easier to reason about and test · revisit never
- **`MigrationPlannerAgent` and `LineageEnricherAgent` are best-effort:** wrapped in try/except in orchestrator; failure logs warning but does not abort the job. Core migration correctness must not depend on enrichment agents · revisit never
- **`CodeGenerator.assemble()` returns `dict[str, str]`; `assemble_flat()` returns str:** multi-file output needed for S-M (1:1 SAS↔Python editor); flat string still needed for reconciliation execution and `python_code` DB column · revisit never

---

## 2026-04-19 (session 16 — UI polish, zip folder tree, lineage node styling)

- **Zip upload stores full relative path as key:** `os.path.basename` was stripping directory structure; full path required for VSCode-style file tree; path traversal guard updated to check `".." in path.split("/")` instead of basename equality · revisit never

---

## 2026-04-19 (session 15 — LineageGraph UX, toasts, file_count, undo/redo)

- **LineageGraph hover-to-focus replaces click-to-focus:** hover is more discoverable and natural for a graph; 80ms debounce prevents flicker when crossing node boundaries · revisit never
- **Undo/Redo history stores `{id→{x,y}}` position snapshots, not full Node objects:** full Node refs are mutated in place by ReactFlow; deep-copying only x/y is safe and minimal · revisit never
- **Undo/Redo uses `setNodes` from `useNodesState` (controlled-mode setter):** ReactFlow in controlled mode overwrites its internal store from the nodes prop on every render; `rfSetNodes` (instance method) gets clobbered; controlled setter is the only correct path · revisit never
- **`file_count` counts all keys in `job.files` (not just non-sentinel):** reference files (CSV/log/xlsx) stored as `__ref_*__` sentinels are still user-uploaded files; count should reflect total accepted files · revisit never
- **Sonner (shadcn) used for all error toasts:** shadcn's official toast recommendation; no `next-themes` dependency — hardcoded `theme="light"` since project is Vite SPA with no theme switching · revisit if dark mode is added
- **Human-readable error copy everywhere:** raw `{detail: ...}` JSON never shown to user; `extractApiError` strips FastAPI envelope; fallback strings written for humans not developers · revisit never

---

## 2026-04-19 (session 14 — UI polish, lineage DAG, Makefile fixes)

- **Editor tab merges Comparison + Edit:** single tab with SAS read-only left, editable Python right; users naturally want the source visible while editing; avoids context-switching between tabs · revisit never
- **`._` zip entries skipped silently:** macOS resource fork files are OS artefacts, not user content; no rejection entry added · revisit never
- **`file_count` counts non-sentinel keys:** keys matching `__…__` pattern are internal sentinels (reference files); plain keys are SAS sources; count reflects user-uploaded SAS files only · revisit if supporting file count needs to be shown separately
- **Makefile: NPM_FLAGS not passed to ESLint/Vite:** ESLint v9 flat config and Vite CLI reject `--silent`; lint and build targets now invoke `npm run lint` / `npm run build` without extra flags · revisit never

---

## 2026-04-18 (session 13 — JobDetailPage, UploadPage workspace, name/file_count)

- **UploadPage as persistent workspace:** state lifted into `UploadStateProvider` (React context at App root) so it survives sidebar navigation; never auto-navigates away; "Start another" keeps result visible, "Accept & clear" is the explicit reset · revisit never
- **Zip preview client-side with jszip:** zip contents parsed in browser on drop, filtered of `__MACOSX`/hidden entries, displayed as a tree; full zip still sent to server unchanged (server handles extraction) · revisit never
- **Tabs component hand-rolled:** shadcn `base-nova` style tabs depend on `@base-ui-components/react` which is not installed and had a circular import; replaced with a self-contained React state-based tabs component · revisit if `@base-ui-components/react` is installed project-wide
- **Markdown doc rendered via `marked` + prose:** `TiptapEditor` receives HTML but LLM doc is raw Markdown; using `marked.parse()` + `dangerouslySetInnerHTML` + Tailwind `prose` class instead of a Tiptap instance · revisit never
- **`name` field on Job:** optional human-readable label submitted as a form field on `POST /migrate`; stored in `jobs.name` (migration 005); surfaced in `GET /jobs` list and result card · revisit never
- **`file_count` derived at query time:** computed in `list_jobs` as count of non-`__`-prefixed keys in `job.files`; not stored as a column · revisit if query performance degrades at scale

---

## 2026-04-18 (session 12 — post-MVP UI planning)

- **Zone-based editor architecture:** each UI content type gets the right primitive — Monaco DiffEditor for SAS vs Python diff, Monaco Editor for inline editing, Tiptap for rich-text notes/reports, React Flow for lineage graph · revisit never
- **Sidebar nav replaces top nav:** persistent collapsible sidebar scales to 6+ pages; top nav does not · revisit never
- **JobDetailPage at /jobs/:id (full page, 4 tabs):** replaces inline expansion in JobsPage; Comparison / Edit / Report / Lineage tabs; deep-linkable · revisit never
- **Zip upload: partial acceptance, no file count limit:** unknown extensions collected into rejection manifest rather than hard 400; caller sees accepted + rejected list · revisit never
- **Zip accepted extensions:** `.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls` — covers SAS source, binary datasets, reference data, execution logs, and Excel inputs · revisit if new SAS-adjacent formats surface
- **Lineage serialised to `job.lineage` JSON column at parse time:** worker writes lineage after parse step; not computed on demand at API request time · revisit never
- **DocGenerator does not crash worker on LLM failure:** catch exception, log warning, leave `job.doc = None`; doc is optional enrichment, not a required pipeline step · revisit never
- **`skip_llm` boolean column for re-reconciliation:** cleaner than adding a new status value to the FSM; worker branches on flag, skips parser+LLM, runs ReconciliationService only · revisit never
- **`parent_job_id` FK on Job for refine action:** enables UI to show refinement history without a separate table · revisit never

---

## 2026-04-18 (session 11 — F-UI + Docker runtime + Azure OpenAI)

- **`CORS_ORIGINS` as plain string, split internally:** `list[str]` pydantic-settings field fails when env var is `*`; switched to `str` field with `@property` that splits on comma · revisit never
- **Migration 001 id column as String(36):** ORM uses `String(36)` for cross-dialect compatibility; migration was incorrectly using `postgresql.UUID` causing type mismatch on INSERT · revisit never
- **Backend entrypoint runs migrations on startup:** `alembic upgrade head` in `entrypoint.sh` before uvicorn ensures schema is always current · revisit if migration time becomes a startup concern
- **Azure deployment name stripped of provider prefix:** `LLM_MODEL=openai:gpt-5.4` → deployment `gpt-5.4` via `split(":", 1)[-1]`; handles both bare and prefixed values · revisit never
- **Frontend volume mount for HMR:** `./src/frontend:/app` + `/app/node_modules` anonymous volume; Vite picks up file changes without container rebuild · revisit never

---

## 2026-04-18 (session 10 — F-LLM + F-sas7bdat + tooling)

- **`make test` now includes mypy:** mypy was only running in `make check` and pre-commit; added to `make test` so type errors surface before commit time · revisit never
- **git-branch-setup always pulls main before branching:** new feature branches start from latest main, not stale local HEAD · revisit never
- **No Co-Authored-By attribution in commits:** user preference; removed from all commit messages · revisit never
- **LLMTranslationError classifies transient vs permanent:** HTTP 429 / 5xx / network errors are transient (retry); 4xx / validation errors are permanent (fail immediately); partial codegen results are saved on failure with `error_detail.resumable=true` for transient cases · revisit if retry policy needs tuning

---

## 2026-04-18 (session 9 — F1-ext + MVP scope alignment)

- **F-number collision resolved:** PROC SORT + %LET are F1 extensions (Phase 2), not a new feature. `docs/plans/F2-proc-sort.md` renamed to `F1-ext-proc-sort-macro.md`. F2 is reserved for the Code Explanation Assistant UI (Phase 3 frontend) per `docs/features.md` · revisit never
- **MVP requires a frontend:** Upload & Results page (F-UI) added to MVP scope — product cannot be demoed or handed to a user without UI · revisit never
- **LLM is the primary and mandatory translation engine:** no rule-based fallback path. LLM system prompt must be upgraded to establish agent as SAS migration expert targeting Python/PySpark. Worker resilience (graceful job failure on API unreachable) is error handling only, not a translation fallback · revisit never
- **sas7bdat reading is MVP-required:** `pyreadstat` already declared in `pyproject.toml` but never wired. `LocalBackend` must implement `read_sas7bdat()` before MVP is complete · revisit never
- **make test is the only allowed test invocation:** `uv run pytest` forbidden everywhere including agent verification steps — all test runs go through make targets. Enforced in memory and CLAUDE.md · revisit never

---

## 2026-04-17

- **Language & runtime:** Python 3.11+ · modern typing, match statements, broad lib support · revisit if Databricks default changes
- **Execution backends:** pandas/PostgreSQL (local) and PySpark (Databricks), toggled by `CLOUD` env var · keeps MVP runnable on a laptop · DuckDB was removed in favour of PostgreSQL (same engine as job state store, one less service) · revisit if PostgreSQL local performance becomes a bottleneck
- **Frontend for MVP:** React + Vite + TypeScript, Tailwind CSS, shadcn/ui · modern component library, accessible primitives, fast DX · revisit never (core stack)
- **LLM tooling:** Claude Code with skills + slash commands + journal-based memory · maximizes context continuity between sessions · revisit never (this is the setup)
- **Provenance:** every generated Python line group carries `# SAS: <file>:<line>` comments · required for audit/compliance user story · non-negotiable
- **Validation strategy:** schema parity + row hash diff + aggregate parity + distribution checks · covers financial reporting confidence · may add more checks per customer

---

## 2026-04-17 (session 2 — foundation setup)

- **Migration approach:** LLM-assisted conversion (approach 3 of 4) — structured prompting with pattern catalog, provenance, and reconciliation as safety net · rationale in `docs/context/migration-approaches.md` · revisit if LLM accuracy proves insufficient at scale
- **Skills vs subagents:** skills only (no specialized subagents) · simpler, compose naturally, avoid duplicated context overhead · revisit if a task requires deep specialization that skills can't capture
- **Backlog as build tracker:** `journal/BACKLOG.md` is the single source of truth for what to build and in what order · read by `/session-start`, updated by `/session-end`
- **Feature-first planning:** when asked to build a feature, Claude invokes `feature-planner` — break into subtasks, update backlog, plan mode, wait for approval before writing code
- **MVP cut:** F1 (DATA step + PROC SQL) + F3 (schema + row count + aggregate parity), local only (CLOUD=false) · all other features are post-MVP
- **Agent framework:** Pydantic AI (`pydantic-ai`) for all LLM interactions — agents, tool definitions, structured outputs · gives type-safe LLM responses via `BaseModel` result types, keeps LLM calls testable and model-agnostic · revisit never (locked in)
- **Pre-commit hooks:** enforced via `pre-commit` library; hooks run ruff format, ruff lint, mypy on every commit · Claude must never use `--no-verify`; hooks are the quality gate, not optional

---

## 2026-04-17 (session 3 — architecture revision)

- **Microservices:** each service is a separate Docker image (backend, worker, frontend, postgres) · separation of concerns; worker decouples heavy processing from API latency · revisit never (core architecture)
- **Worker service:** async job runner as a dedicated container polling Postgres · allows independent scaling and restart of the processing layer without touching the API · revisit if queue volume demands a real message broker (RabbitMQ, SQS)
- **Job state in PostgreSQL:** jobs table stores status, input hash, files JSONB, output, and audit fields · already in the Docker stack; cloud-ready (managed Postgres later); avoids an extra service · revisit never for MVP, may add Redis for pub/sub in Phase 2
- **Async job flow:** POST /migrate → job_id → poll GET /jobs/{id} · keeps API response fast; client controls polling interval · revisit if real-time progress is needed (WebSocket, Phase 2)
- **Reconciliation inline in worker:** F3 runs automatically after codegen, not a separate endpoint · removes manual step; every migration always has a reconciliation result · revisit never
- **Provider-agnostic LLM via LLM_MODEL env var:** Pydantic AI resolves provider from model string (e.g. anthropic:claude-sonnet-4-6) · no custom routing code; swap provider by changing one env var · revisit never
- **Multi-file upload in MVP:** SAS projects are inherently multi-file; single-file MVP was not realistic · parser must order blocks by dependency across files · revisit scope if dependency resolution proves too complex for Phase 1
- **F8 and F9 bumped to MVP:** compliance audit traceability and downloadable output are mandatory for regulated (pharma/finance) first customers · data already in jobs table; no new architecture required · revisit never
- **Databricks paused:** DatabricksBackend stub remains in architecture but out of scope until Phase 4 · no Databricks workspace available for testing · revisit when workspace is confirmed

---

## 2026-04-17 (session 4 — DuckDB removal, skill hardening)

- **DuckDB removed from local backend:** LocalBackend now uses pandas + PostgreSQL instead of pandas + DuckDB · PostgreSQL is already a required service in Docker Compose; removing DuckDB eliminates one dependency and one moving part · revisit never (PostgreSQL is the standard)
- **Skills must not hard-code file paths:** skills and commands must derive service paths from `docs/architecture.md` — Directory Structure section — not embed them directly · prevents stale path refs when architecture evolves · applies to all future skill edits

---

## 2026-04-17 (session 5 — Databricks output target decision)

- **DatabricksBackend generates PySpark only:** three targets were evaluated — Databricks SQL, PySpark, and Delta Live Tables (DLT). PySpark confirmed as the sole output target for `DatabricksBackend`. Rationale: (1) PySpark is symmetric with `LocalBackend` — same Python, same `ComputeBackend` abstraction; (2) DATA steps map cleanly to DataFrame transformations or UDFs; (3) PROC SQL maps to `spark.sql(...)` strings naturally inside PySpark — no separate SQL output mode needed; (4) this is what enterprise clients mean by "Databricks migration" · revisit if a client explicitly requires SQL Warehouse or DLT output
- **Databricks SQL deferred:** SQL cannot handle DATA step logic (RETAIN, array, LAG, conditional multi-dataset output) — it would only cover PROC SQL-heavy codebases; a mixed SQL-in-PySpark approach (`spark.sql()` for PROC SQL blocks) achieves the readability benefit without a separate output mode · revisit in Phase 4+ if a client requires SQL Warehouse target
- **DLT (Delta Live Tables) deferred:** architecturally attractive (native lineage, declarative step model matches SAS) but cannot run locally — breaks the local/cloud symmetry that is a hard design constraint; LLM training data for DLT is thin · revisit Phase 4+ if local parity constraint is relaxed
- **Codegen constraint — no pandas-only idioms:** `CodeGenerator` must not emit pandas-specific calls; use parameterized DataFrame operations so `LocalBackend` and `DatabricksBackend` swap APIs without changing structure · enforced in Phase 1 codegen design

---

## 2026-04-18 (session 7 — F1 completion S10–S16 + multi-agent setup)

- **Multi-agent architecture adopted:** orchestrator + backend-builder + frontend-builder + fullstack-planner + tester agents defined in `.claude/agents/` · separates planning, implementation, and quality gating into distinct roles; orchestrator owns session lifecycle and commit gating · revisit if agent boundaries prove too rigid in practice
- **Orchestrator delegation is mandatory:** orchestrator must spawn specialist agents via Agent tool — never write implementation code directly · discovered this was being bypassed in first pass; enforced in orchestrator.md guardrails and saved to memory · revisit never
- **test-runner skill added:** dedicated `/test-runner` slash command for running `make test`, interpreting results, and reporting GREEN/RED verdict · prevents ad-hoc pytest invocations and centralises test output interpretation · revisit never
- **Coverage concurrency = thread + greenlet:** `[tool.coverage.run] concurrency = ["thread", "greenlet"]` required to trace async FastAPI route bodies via httpx/aiosqlite — without it, route handler lines showed 0% despite tests passing · revisit if coverage tooling changes
- **Makefile output suppressed globally:** PYTEST_FLAGS, NPM_FLAGS, DOCKER_BUILD_FLAGS variables added; all targets use `@` prefix and `--quiet`/`--silent` flags · saves tokens in CI and Claude sessions · revisit never
- **mypy tests.* exemption removed:** the blanket `ignore_errors = true` on `tests.*` was a shortcut; removed so mypy checks test files under strict mode · required fixing `dict` → `dict[str, Any]`, `type: ignore` cleanup, and N806 naming violations · revisit never

---

## 2026-04-18 (session 8 — CI hardening + Tailwind v4 migration)

- **tsc --noEmit is the correct type-check command:** `tsc -b` (project references build mode) requires `composite: true` which conflicts with `noEmit: true`; `tsc --noEmit` reads `tsconfig.app.json` directly and resolves paths correctly · revisit never
- **baseUrl required in tsconfig.app.json:** `pathsBasePath` is not propagated when a config is loaded as a referenced project via `tsc -b`; `baseUrl: "."` + `ignoreDeprecations: "6.0"` is the TS 6 migration path · revisit when TS 7 ships a `baseUrl` replacement
- **Tailwind v4 with Vite plugin:** shadcn v4 generates CSS for Tailwind v4; keeping v3 caused `@apply` errors on every new component; switched to `@tailwindcss/vite`, removed PostCSS config and JS theme config · revisit never
- **Docker job independent of test:** Dockerfile correctness is unrelated to Python logic; running in parallel reduces wall-clock CI time · revisit never
- **Reconciliation coverage scoped separately:** `src/worker/validation` measured in isolation via `.coveragerc-reconciliation` at 80% gate; main suite covers all of `src` at 90% · raise to 90% when missing lines covered
- **astral-sh/setup-uv pinned to full semver:** `v8` floating tag does not exist; must use `v8.1.0` · update when new minor released

---

## 2026-04-23 (session — Plan tab UX + BlockRevisionDrawer + PlainEnglishAgent)

- **block_id URL encoding uses `.replace(/:/g, '%3A')` not `encodeURIComponent`:** FastAPI `block_id:path` params decode `%2F` back to `/` before route matching, causing 404 when slash is encoded; colons must be encoded but slashes must be preserved as literal path segments · revisit never
- **BlockRevisionDrawer diff uses MonacoDiffViewer with `previousCode` prop:** instead of parsing unified diff strings (fragile, misaligned columns), each revision receives the prior revision's `python_code` directly; Monaco handles all diffing natively · revisit never
- **PlainEnglishAgent output field was `"markdown"` in prompt vs `"non_technical_doc"` in Pydantic model:** mismatch silently produced empty docs; corrected to match model field · revisit never
- **PlainEnglishAgent restructured to 5 sections with explicit list formatting:** Purpose (prose) + Source Data (bullets) + How It Works (numbered) + Outputs (bold bullets) + Migration Status (one sentence); "8-12 sentences, no bullet points" rule removed as it forced unstructured output · revisit never

---

## 2026-04-18 (session 6 — F1 engine implementation S00–S09)

- **LocalBackend.run_sql uses stdlib sqlite3, not PostgreSQL:** three options were evaluated — pandasql (SQLite wrapper, extra dep), live PostgreSQL (requires running service), stdlib sqlite3 (zero dep, self-contained). sqlite3 chosen: no extra dep, no service required for local tests, result fidelity is what matters not the SQL engine · revisit if PROC SQL edge cases (window functions, ANSI-only syntax) hit SQLite limits
- **Dockerfile README.md copy required before uv sync:** hatchling validates `readme = "README.md"` at package build time; both backend and worker Dockerfiles now copy README.md alongside pyproject.toml and uv.lock before running `uv sync --no-dev --frozen` · revisit never
- **make docker-build added as mandatory step for Dockerfile changes:** any commit touching a Dockerfile or docker-compose.yml must pass `make docker-build` in addition to `make test` · enforced in CLAUDE.md Critical Rules · revisit never
- **make test is a Critical Rule in CLAUDE.md:** `uv run pytest` and bare `pytest` are forbidden everywhere; only `make test` is allowed · previously only in skills; now in CLAUDE.md to cover all contexts · revisit never
- **pydantic-ai v1 API:** `result_type` → `output_type`; `result.data` → `result.output`; Agent overloads typed for `str` output only — BaseModel `output_type` works at runtime but mypy requires `ignore_errors = true` on `llm_client.py` · revisit if pydantic-ai adds typed overloads for structured output
- **backend-builder skill must be invoked when writing engine code:** discovered that running without the skill led to ruff/mypy violations in the first pass; backend-builder enforces the checklist that catches these · revisit never
- **BlockType uses StrEnum (Python 3.11+):** `class BlockType(str, Enum)` replaced with `class BlockType(StrEnum)` per ruff UP042 · no behaviour change · revisit never

---
```
