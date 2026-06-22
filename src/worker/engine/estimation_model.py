"""Provisional effort-estimation model for the F77 scoping report.

This module turns a per-file complexity inventory into a low/mid/high
consultant-day estimate. The rate table below is a **PROVISIONAL placeholder**
pending the dedicated estimation-model doc (``docs/context/estimation-model.md``)
and calibration against real engagements. Numbers are intentionally
conservative round figures and MUST NOT be treated as committed estimates;
the returned :class:`EffortEstimate` always carries ``provisional=True``.

The computation is fully deterministic: the same file inventory + the same
``RATE_TABLE`` always yields a byte-identical estimate (no LLM, no I/O, no
clock). Honors DECISIONS.md "no silent caps".
"""

# SAS: src/worker/engine/estimation_model.py:1
from .models import ComplexityTier, EffortEstimate, FileInventoryItem

# PROVISIONAL placeholder rates — consultant-days *per file* by complexity tier.
# Each tier maps to (low, mid, high) day multipliers. These are first-pass round
# numbers to make the report structurally complete; calibrate later.
# TODO(business-review): replace with calibrated rates from estimation-model doc.
RATE_TABLE: dict[ComplexityTier, tuple[float, float, float]] = {
    "simple": (0.25, 0.5, 1.0),
    "moderate": (1.0, 2.0, 3.5),
    "complex": (3.0, 5.0, 8.0),
}


def estimate_effort(file_inventory: list[FileInventoryItem]) -> EffortEstimate:
    """Estimate migration effort by summing per-file tier rates.

    Args:
        file_inventory: Per-file complexity summaries from the scoping engine.

    Returns:
        An :class:`EffortEstimate` with low/mid/high consultant-days,
        ``provisional=True``, and a ``basis`` string describing the formula.
        For an empty inventory all totals are ``0.0``.
    """
    low = mid = high = 0.0
    for item in file_inventory:
        rate_low, rate_mid, rate_high = RATE_TABLE[item.complexity_tier]
        low += rate_low
        mid += rate_mid
        high += rate_high

    # Round to avoid float drift while keeping determinism.
    low, mid, high = round(low, 4), round(mid, 4), round(high, 4)

    basis = (
        "PROVISIONAL: sum of per-file consultant-day rates by complexity tier "
        f"(simple={RATE_TABLE['simple']}, moderate={RATE_TABLE['moderate']}, "
        f"complex={RATE_TABLE['complex']} as (low, mid, high) days). "
        "Rates are placeholders pending calibration."
    )
    return EffortEstimate(
        low_days=low,
        mid_days=mid,
        high_days=high,
        provisional=True,
        basis=basis,
    )
