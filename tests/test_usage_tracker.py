"""Unit tests for src/worker/engine/usage.py.

Covers:
- No-op behaviour when no tracker is active
- Phase attribution
- Phase accumulation (multiple calls to same phase)
- Total computation
- asyncio.to_thread contextvar propagation
- asyncio.gather contextvar propagation
"""

# SAS: tests/test_usage_tracker.py:1

import asyncio

from pydantic_ai.usage import Usage
from src.worker.engine.usage import (
    UsageTracker,
    _phase,
    _tracker,
    activate,
    record_usage,
    set_phase,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    requests: int = 1,
) -> Usage:
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        requests=requests,
    )


def _reset_context() -> None:
    """Clear contextvars between tests."""
    _tracker.set(None)
    _phase.set("other")


# ---------------------------------------------------------------------------
# 1. No-op when no tracker is active
# ---------------------------------------------------------------------------


def test_record_usage_no_tracker_does_not_raise() -> None:
    _reset_context()
    # Should not raise even with no active tracker
    record_usage(_make_usage(input_tokens=10, output_tokens=5))


def test_record_usage_no_tracker_stores_nothing() -> None:
    _reset_context()
    tracker = UsageTracker()
    # Intentionally do NOT call activate() — record_usage should be a no-op
    record_usage(_make_usage(input_tokens=10))
    assert tracker.snapshot()["phases"] == {}


# ---------------------------------------------------------------------------
# 2. Phase attribution
# ---------------------------------------------------------------------------


def test_phase_attribution() -> None:
    _reset_context()
    tracker = UsageTracker()
    activate(tracker)
    set_phase("parse_analysis")
    record_usage(_make_usage(input_tokens=100, output_tokens=50, requests=1))

    snap = tracker.snapshot()
    assert "parse_analysis" in snap["phases"]
    bucket = snap["phases"]["parse_analysis"]
    assert bucket["input_tokens"] == 100
    assert bucket["output_tokens"] == 50
    assert bucket["requests"] == 1


# ---------------------------------------------------------------------------
# 3. Phase accumulation
# ---------------------------------------------------------------------------


def test_phase_accumulation() -> None:
    _reset_context()
    tracker = UsageTracker()
    activate(tracker)
    set_phase("translation")

    record_usage(_make_usage(input_tokens=200, output_tokens=80, requests=1))
    record_usage(_make_usage(input_tokens=150, output_tokens=60, requests=1))

    snap = tracker.snapshot()
    bucket = snap["phases"]["translation"]
    assert bucket["input_tokens"] == 350
    assert bucket["output_tokens"] == 140
    assert bucket["requests"] == 2


# ---------------------------------------------------------------------------
# 4. Total computation
# ---------------------------------------------------------------------------


def test_total_equals_sum_of_phases() -> None:
    _reset_context()
    tracker = UsageTracker()
    activate(tracker)

    set_phase("parse_analysis")
    record_usage(_make_usage(input_tokens=100, output_tokens=40, requests=1))

    set_phase("translation")
    record_usage(_make_usage(input_tokens=200, output_tokens=80, requests=2))

    snap = tracker.snapshot()
    total = snap["total"]
    assert total["input_tokens"] == 300
    assert total["output_tokens"] == 120
    assert total["requests"] == 3


def test_total_includes_cache_tokens() -> None:
    _reset_context()
    tracker = UsageTracker()
    activate(tracker)
    set_phase("enrichment")
    record_usage(_make_usage(cache_read_tokens=50, cache_write_tokens=20, requests=1))

    snap = tracker.snapshot()
    assert snap["total"]["cache_read_tokens"] == 50
    assert snap["total"]["cache_write_tokens"] == 20


# ---------------------------------------------------------------------------
# 5. asyncio.to_thread propagation
# ---------------------------------------------------------------------------


async def test_contextvar_propagates_into_to_thread() -> None:
    _reset_context()
    tracker = UsageTracker()
    activate(tracker)
    set_phase("migration_planning")

    def sync_work() -> None:
        # Contextvar values are copied into threads by asyncio.to_thread
        record_usage(_make_usage(input_tokens=77, requests=1))

    await asyncio.to_thread(sync_work)

    snap = tracker.snapshot()
    assert snap["phases"].get("migration_planning", {}).get("input_tokens") == 77


# ---------------------------------------------------------------------------
# 6. asyncio.gather propagation
# ---------------------------------------------------------------------------


async def test_contextvar_propagates_across_gather() -> None:
    _reset_context()
    tracker = UsageTracker()
    activate(tracker)

    async def task_a() -> None:
        set_phase("assembly_recon")
        record_usage(_make_usage(input_tokens=30, requests=1))

    async def task_b() -> None:
        set_phase("assembly_recon")
        record_usage(_make_usage(input_tokens=70, requests=1))

    await asyncio.gather(task_a(), task_b())

    snap = tracker.snapshot()
    # Both coroutines share the same tracker (same context copy) and both
    # write to the same phase, so the sum must be 100.
    assert snap["phases"]["assembly_recon"]["input_tokens"] == 100
    assert snap["total"]["requests"] == 2
