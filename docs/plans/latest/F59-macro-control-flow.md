# F59 — Macro Control-Flow & Variable Evaluation (%if/%do/%let/%global)

**Phase:** 2
**Area:** Backend / Worker
**Status:** done

## Goal

F57 expands control-flow-free macro calls but deliberately leaves macros whose body
contains `%if`/`%do`/`%while`/`%let`/`%global`/`%return` unexpanded — so the datasets and
macro variables they produce never materialise and downstream steps crash
(`NameError: name 'adsl_age' is not defined`). F59 adds **deterministic evaluation of
macro control flow and macro-variable assignment** at expansion time: bind the call args,
evaluate `%if/%then/%else` conditions against the bound values, unwrap the selected
`%do`/`%end` branch, honour `%return`, apply `%let`/`%global` assignments (with `%global NAME=VALUE`
recorded and substituted into the remainder of the same source), unroll bounded `%do i=a %to b`
loops, and drop `%put`. Anything that cannot be evaluated deterministically is left unexpanded
(the current safe behaviour — no partial or guessed output). Done = `%m_derive_age_group(in=work.adsl_pre, out=work.adsl_age, ...)`
expands to its DATA step (producing `work.adsl_age`), `%global NAME=VALUE` propagates to downstream
`&NAME` within the same file, and the `adsl_age` NameError class is gone.

## Acceptance Criteria

- [x] `%if <cond> %then X; %else Y;` and the `%do; … %end;` block forms are evaluated; the taken branch is inlined, the other dropped
- [x] `%return` truncates the remaining macro body
- [x] `%let`/`%global NAME = VALUE;` assignments are applied; `%global NAME=VALUE` is recorded and the resulting `&NAME` references substituted in the rest of the same source
- [x] `%put` statements are dropped (no SAS equivalent)
- [x] Condition evaluation supports `%length(x)`, string/numeric `=`, `ne`/`^=`, `<`/`>`/`<=`/`>=`, `and`/`or`, parentheses against bound params and literals; unsupported conditions → macro left unexpanded
- [x] Bounded `%do i=a %to b [%by s]` loops are unrolled (cap `MAX_UNROLL`); `%do %while`/`%until` left unexpanded
- [x] `%m_derive_age_group(in=work.adsl_pre, out=work.adsl_age, ...)` expands to a DATA step whose output dataset is `work.adsl_age`
- [x] Expansion is deterministic: identical SAS input → identical output (no LLM)
- [x] `make test` exits 0
- [x] ruff and mypy pass

## Design

Regex alone cannot handle nested `%do/%end` or `%else` pairing (balanced-bracket problem). Use a
two-layer pure module `src/worker/engine/macro_logic.py`: a single-pass **tokenizer** feeding a
**recursive-descent resolver**. `evaluate_condition` is a pure leaf (no `eval()`). Integration into
`expand_macro_calls` is the only edit to existing code; the legacy `MacroExpander` is untouched.

**Pinned correctness/determinism rules:**
- `%end` matched by a depth counter over `%do*`/`%end`; `%else` paired via nearest open `%if` on the recursion stack — never textual regex.
- All-or-nothing: any `CannotResolveMacroLogic` raised in `resolve_macro_body` discards all partial output and skips the `assigned_globals` merge → call left verbatim (F57 safe behaviour).
- Numeric compare iff both operands match `^-?\d+$`, else case-sensitive string compare.
- Bounded: `MAX_UNROLL = 1000` per expansion; `_max_rounds = 10` fixed-point backstop.
- Resolved SAS text is emitted INSIDE F57's existing `/* SAS-MACRO-EXPANDED … */` provenance wrapper.

## Subtasks

### S-A0: tokenizer
**File:** `src/worker/engine/macro_logic.py` (new)
**Depends on:** none
**Done when:** `_tokenize(body) -> list[Token]` plus `Token` and `CannotResolveMacroLogic` exist; strips `/* */` and `%* …;` comments; emits ordered tokens `MIF, MTHEN, MELSE, MDO_BLOCK, MDO_ITER, MDO_WHILE, MDO_UNTIL, MEND, MLET, MGLOBAL, MRETURN, MPUT, SAS_TEXT`; `%do %while`/`%do %until` recognised only as reject-markers. Only layer that touches raw text.
- [x] done

### S-A: macro condition evaluator
**File:** `src/worker/engine/macro_logic.py`
**Depends on:** S-A0
**Done when:** `evaluate_condition(expr: str, env: dict[str, str]) -> bool | None` exists — substitutes `&var` (reuse `_substitute_let_vars`) and `%length(x)`, precedence-climbing parse (comparisons > `and` > `or`, parentheses), operator aliases `eq/ne/^=/~=/lt/gt/le/ge` ↔ symbols, numeric/string type rule; returns `None` on any unresolved `&ref` or unsupported function; never raises.
- [x] done

### S-B: macro body logic resolver (branches/assign/return/put)
**File:** `src/worker/engine/macro_logic.py`
**Depends on:** S-A
**Done when:** `resolve_macro_body(body: str, env: dict[str, str]) -> MacroLogicResult` (`.sas_text`, `.assigned_globals`) exists via recursive descent — `%if/%then/%else` in both `%then stmt;` and `%then %do;…%end;` forms (taken branch emitted, untaken walked/consumed), `%let`/`%global` mutate env in order + record globals, `%return` stops the taken path, `%put` dropped; `&param` refs left intact for downstream substitution; all-or-nothing on `CannotResolveMacroLogic`.
- [x] done

### S-B2: iterative loop unrolling
**File:** `src/worker/engine/macro_logic.py`
**Depends on:** S-B
**Done when:** `resolve_macro_body` handles `%do i=START %to END [%by STEP]; … %end;` — integer bounds resolved from env, body unrolled with per-iteration `&i`, matching `%end` via depth counter, `MAX_UNROLL` cap (raise on exceed); non-integer bounds or `%do %while`/`%until` → `CannotResolveMacroLogic`.
- [x] done

### S-C: unit tests for tokenizer + evaluator + resolver
**File:** `tests/test_macro_logic.py` (new)
**Depends on:** S-B2
**Done when:** tests cover the tokenizer; `evaluate_condition` (true/false/None, `%length`, each operator, `01`-vs-`1` type rule, parentheses, `and`/`or`); and `resolve_macro_body` Tier-1 cases — `m_derive_age_group` guard (false → only DATA step; true → truncated at `%return`), nested `%if` inside `%do`, `%else` binds to inner `%if`, chained `%let`, loop unroll, `%global` recorded in `assigned_globals`, `%do %while`→reject, malformed `%else`→reject, comments/`%*` ignored, and all-or-nothing (partial body + later `%do %until` → raises, emits nothing).
- [x] done

### S-D: integrate logic resolution into `expand_macro_calls`
**File:** `src/worker/engine/macro_call_expander.py`
**Depends on:** S-B2
**Done when:** when a macro body is not control-flow-free, `expand_macro_calls` calls `resolve_macro_body`; on success the resolved `sas_text` is inlined inside the existing provenance wrapper and `assigned_globals` merged (only on success) into a `global_env` substituted across the whole source after each fixed-point round; on `CannotResolveMacroLogic` the call is left untouched. Termination compares source after both expansion and global substitution, backed by `_max_rounds`.
- [x] done

### S-E: unit tests for integrated expansion
**File:** `tests/test_macro_call_expander.py` (extend)
**Depends on:** S-D
**Done when:** tests assert `%m_derive_age_group(...)` expands to a DATA step creating `work.adsl_age` (no `%if`/`%do`/`%put`/`&` left); cross-call within-file `%global` (set by call #1 → consumed by later plain-SAS `&G`); all-or-nothing fallback (unsupported macro left verbatim); and idempotence (running twice on its own output is stable).
- [x] done

### S-F: reconciliation test through the parser
**File:** `tests/reconciliation/test_macro_control_flow.py` (new)
**Depends on:** S-D
**Done when:** a minimal multi-statement fixture (`%m_derive_age_group` def + a caller invoking it then `proc sort data=work.adsl_age`) parsed via `SASParser.parse` yields a block whose `output_datasets` contains `work.adsl_age`, ordered before the consumer — asserting the `adsl_age` NameError class is resolved.
- [x] done

### S-G: full suite green
**File:** n/a
**Depends on:** S-E, S-F
**Done when:** `make test` exits 0 with all gates green.
- [x] done

## Dependencies on other features

- F57 (macro call expansion) — reuses `parse_macro_params`/`parse_call_args`/`bind_args` for argument binding and the `expand_macro_calls` fixed-point loop, and `_substitute_let_vars` from `macro_expander.py`

## Existing architecture considered

- Legacy `MacroExpander` (`main.py:297,466`) runs per-block after parse (only `%LET` + zero-arg inlining); F59 enhances only the parse-time `expand_macro_calls` path — no consolidation, no double-processing, legacy `CannotExpand` tests stay valid.
- Expanding a previously-skipped macro call turns a silently-dropped line into a real DATA step block, so `MigrationPlannerAgent` assigns `translate` instead of the dataset never materialising. Non-breaking: the `&`-param "manual" messaging (DECISIONS 2026-06-13 F35; `runbook_templates.py`; `models.py:241`) applies to `macros/*.sas` definition blocks, untouched here.

## Out of scope for this feature

- Cross-FILE `%global` propagation — `parser.parse` expands each file independently; within-file propagation only (documented limitation)
- `%do %while` / `%do %until` (condition-driven; termination not cheaply guaranteed)
- `%sysfunc`/`%eval` and macro functions beyond `%length`
- `CALL SYMPUT`/`CALL SYMPUTX` runtime macro-variable assignment (separate Tier-1 backlog item)
- Wiring the existing LLM `MacroResolverAgent` as a fallback — determinism is the locked constraint
- `%sysfunc`/`%eval` and other macro functions beyond `%length`
