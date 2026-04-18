"""Unit test for src/backend/db/session.py — get_async_session generator."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.backend.db.session import get_async_session


@pytest.mark.asyncio
async def test_get_async_session_yields_session() -> None:
    mock_session = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mock_factory = MagicMock(return_value=mock_cm)

    with patch("src.backend.db.session.AsyncSessionLocal", mock_factory):
        gen = get_async_session()
        session = await gen.__anext__()
        assert session is mock_session
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()
