# Confidence Metric

This document defines what the confidence score means, how it is computed, and what it does and does not guarantee.

---

## User-facing explanation

The confidence score is an estimate of how reliably a SAS block was translated to Python. It is shown as a percentage (e.g. "83%") or a band (High / Medium / Low / Very Low).

**What it tells you:**
- **High (≥ 85%)** — The translation agent was confident and, where a reference output was available, the Python output matched the SAS output exactly. Safe to treat as verified.
- **Medium (65–84%)** — The translation is likely correct but has not been fully verified, or the agent had some uncertainty. Worth a quick review.
- **Low (40–64%)** — The agent flagged uncertainty, or the output did not match the reference. Requires human review before the block can be trusted.
- **Very Low (< 40%)** — The agent had very low confidence, or the block failed reconciliation and was already low confidence. Likely needs manual rewrite.

**What it does not guarantee:**
- A High confidence score does not mean the output is semantically correct in all edge cases — it means the automated checks passed and the LLM was confident. A human reviewer should still check any block that is business-critical.
- Confidence is computed per block (DATA step, PROC, etc.), not per column or per row. A block can pass with High confidence while producing a subtle rounding difference on one column.
- If no reference CSV was uploaded, there is no reconciliation to validate against — the score reflects LLM self-assessment only.

---

## Technical reference

### Per-block confidence

Each block carries three confidence fields:

| Field | Source | Description |
|---|---|---|
| `confidence_score` | LLM (`MigrationPlannerAgent`) | Self-reported float 0.0–1.0 at plan time. Default 0.5 if LLM omits it. |
| `confidence_band` | Derived from `confidence_score` at write time | `high` ≥ 0.85 · `medium` ≥ 0.65 · `low` ≥ 0.40 · `very_low` < 0.40 · `unknown` if no score |
| `effective_confidence_band` | Computed post-reconciliation at read time | Adjusts the LLM band using reconciliation outcome (see table below) |

**`effective_confidence_band` rules** (`src/backend/api/routes/jobs.py:_effective_confidence`):

| LLM band | Recon result | Effective band |
|---|---|---|
| high / medium | pass | unchanged (minimum: medium) |
| low / very_low | pass | unchanged |
| high / medium | fail | low |
| low / very_low | fail | very_low |
| any | no recon | unchanged (LLM band) |

### Overall job confidence

`overall_confidence_score` = arithmetic mean of all block `confidence_score` values.

`overall_confidence` label:

| Score | Label |
|---|---|
| ≥ 0.85 | `high` |
| ≥ 0.65 | `medium` |
| ≥ 0.40 | `low` |
| < 0.40 | `very_low` |
| no blocks | `unknown` |

### Blocks requiring attention

A block is flagged `needs_attention = true` when any of the following are true:
- `strategy == "manual"` (no automated translation attempted)
- `reconciliation_status == "fail"`
- `confidence_band` is `low`, `very_low`, or `unknown`

### Auto-verified count

A block counts as `auto_verified` when all three hold:
- `strategy != "manual"`
- `reconciliation_status == "pass"`
- `confidence_band` is `high` or `medium`

### Non-translated blocks

Blocks with strategy `manual`, `skip`, or `manual_ingestion` always receive `confidence_score = 0.0` and `confidence_band = "unknown"` or `"very_low"`. They are excluded from the auto-verified count and always appear in the needs-attention list.

### Where confidence comes from

The LLM (`MigrationPlannerAgent`) is asked to self-assess confidence for each block when building the migration plan. The prompt provides guidance thresholds (0.9 = straightforward DATA step; 0.5 = unfamiliar PROC; 0.2 = complex matrix logic). The score is an estimate — not a proven correctness measure — and is always superseded by reconciliation results where available.

---

## Limitations

- **No SAS execution**: The tool never runs the original SAS code. Confidence is relative to the reference CSV the user uploads, not to a live SAS environment.
- **Aggregate checks only**: Reconciliation checks schema parity, row count, and aggregate parity. Row-level hash diff and column-level diff are post-MVP (F15).
- **LLM calibration**: The confidence score reflects the model's self-reported uncertainty, which may not be well-calibrated for all SAS constructs. Treat Very Low and Low bands as signals to review, not as proof of incorrectness.
