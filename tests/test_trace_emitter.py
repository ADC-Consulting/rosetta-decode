"""Unit tests for TraceEmitter and JobCancelledError.

Covers:
- TraceEmitter.emit() inserts a JobTrace row with a ts key.
- TraceEmitter.emit() never raises even when the session factory is broken.
- JobCancelledError is a plain Exception subclass.
"""

# SAS: tests/test_trace_emitter.py:1

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.trace import JobCancelledError, TraceEmitter


class TestJobCancelledError:
    """JobCancelledError must be a plain Exception."""

    def test_is_exception_subclass(self) -> None:
        exc = JobCancelledError("cancelled")
        assert isinstance(exc, Exception)
        assert str(exc) == "cancelled"


class TestTraceEmitterEmit:
    """TraceEmitter.emit() inserts a JobTrace row with a ts key."""

    @pytest.mark.asyncio
    async def test_emit_inserts_trace_row(self) -> None:
        """emit() opens a session, adds a JobTrace, and commits."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        emitter = TraceEmitter(job_id="job-123", session_factory=mock_factory)
        await emitter.emit("block_start", {"block_id": "foo.sas:10", "attempt": 1})

        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        # The added object is a JobTrace
        assert added_obj.job_id == "job-123"
        assert added_obj.event_type == "block_start"
        assert "ts" in added_obj.payload
        assert added_obj.payload["block_id"] == "foo.sas:10"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_never_raises_on_session_error(self) -> None:
        """emit() must swallow exceptions from the session factory."""
        mock_factory = MagicMock(side_effect=RuntimeError("DB down"))

        emitter = TraceEmitter(job_id="job-err", session_factory=mock_factory)
        # Should not raise
        await emitter.emit("job_done", {"final_status": "proposed"})

    @pytest.mark.asyncio
    async def test_emit_never_raises_on_commit_error(self) -> None:
        """emit() must swallow commit failures."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock(side_effect=OSError("disk full"))

        mock_factory = MagicMock(return_value=mock_session)

        emitter = TraceEmitter(job_id="job-disk", session_factory=mock_factory)
        await emitter.emit("error", {"msg": "oops"})  # must not raise

    @pytest.mark.asyncio
    async def test_emit_adds_ts_to_payload(self) -> None:
        """emit() enriches payload with a 'ts' key before storing."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        emitter = TraceEmitter(job_id="job-ts", session_factory=mock_factory)
        await emitter.emit("recon_result", {"all_passed": True})

        added_obj = mock_session.add.call_args[0][0]
        assert "ts" in added_obj.payload
        # ts must be an ISO 8601 string
        ts = added_obj.payload["ts"]
        assert "T" in ts  # basic ISO datetime check
