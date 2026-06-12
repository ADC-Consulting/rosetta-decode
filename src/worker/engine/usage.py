"""Contextvar-based LLM usage tracking for the worker engine.

Provides a lightweight, async-safe mechanism for accumulating token usage
across all pydantic-ai agent calls within a single migration job, broken
down by pipeline phase.

Typical usage::

    tracker = UsageTracker()
    activate(tracker)
    set_phase("translation")
    # ... agent calls record_usage() internally ...
    snapshot = tracker.snapshot()
"""

# SAS: src/worker/engine/usage.py:1

import logging
from contextvars import ContextVar
from typing import Any

from pydantic_ai.usage import RunUsage

log = logging.getLogger(__name__)

_tracker: ContextVar["UsageTracker | None"] = ContextVar("usage_tracker", default=None)
_phase: ContextVar[str] = ContextVar("usage_phase", default="other")

PHASES = (
    "parse_analysis",
    "migration_planning",
    "translation",
    "assembly_recon",
    "enrichment",
)

_BUCKET_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "requests",
)


class UsageTracker:
    """Accumulates LLM token usage per pipeline phase for a single job.

    Thread- and async-safe via Python contextvars — each concurrent task
    that calls :func:`activate` with its own tracker instance gets isolated
    accounting.
    """

    def __init__(self) -> None:
        """Initialise empty phase buckets."""
        self._phases: dict[str, dict[str, int]] = {}

    def add(self, phase: str, usage: RunUsage) -> None:
        """Add a single :class:`~pydantic_ai.usage.RunUsage` reading to *phase*.

        Args:
            phase: Pipeline phase label (e.g. ``"translation"``).
            usage: Token counts returned by a pydantic-ai agent run.
        """
        if phase not in self._phases:
            self._phases[phase] = {k: 0 for k in _BUCKET_KEYS}
        bucket = self._phases[phase]
        bucket["input_tokens"] += usage.input_tokens or 0
        bucket["output_tokens"] += usage.output_tokens or 0
        bucket["cache_read_tokens"] += usage.cache_read_tokens or 0
        bucket["cache_write_tokens"] += usage.cache_write_tokens or 0
        bucket["requests"] += usage.requests or 0
        log.debug(
            "usage recorded phase=%s input=%d output=%d cache_r=%d cache_w=%d req=%d",
            phase,
            usage.input_tokens or 0,
            usage.output_tokens or 0,
            usage.cache_read_tokens or 0,
            usage.cache_write_tokens or 0,
            usage.requests or 0,
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of accumulated usage keyed by phase plus a grand total.

        Returns:
            Mapping with ``"phases"`` (per-phase dicts) and ``"total"`` (summed).
        """
        total: dict[str, int] = {k: 0 for k in _BUCKET_KEYS}
        phases_copy: dict[str, dict[str, int]] = {}
        for phase, bucket in self._phases.items():
            phases_copy[phase] = dict(bucket)
            for k in _BUCKET_KEYS:
                total[k] += bucket[k]
        return {"phases": phases_copy, "total": total}


def activate(tracker: UsageTracker) -> None:
    """Bind *tracker* to the current async context.

    Args:
        tracker: The :class:`UsageTracker` instance that subsequent
            :func:`record_usage` calls will write to.
    """
    _tracker.set(tracker)


def set_phase(name: str) -> None:
    """Set the current pipeline phase label in the async context.

    Args:
        name: Phase name — should be one of :data:`PHASES` but is not
            strictly enforced so callers can use ad-hoc labels.
    """
    _phase.set(name)


def record_usage(usage: RunUsage) -> None:
    """Record *usage* against the active tracker and current phase.

    No-op when no tracker is active in the current context (e.g. tests or
    code paths that have not called :func:`activate`).

    Args:
        usage: Token counts from a completed pydantic-ai agent run.
    """
    tracker = _tracker.get()
    if tracker is not None:
        tracker.add(_phase.get(), usage)
