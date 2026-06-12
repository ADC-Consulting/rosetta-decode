"""Unit tests for src/backend/core/pricing.py."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
import src.backend.core.pricing as pricing
from src.backend.core.pricing import PriceInfo, compute_cost, get_price


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level LiteLLM cache before each test."""
    monkeypatch.setattr(pricing, "_cache", None)
    monkeypatch.setattr(pricing, "_cache_ts", 0.0)


# ---------------------------------------------------------------------------
# 1. Prefix stripping
# ---------------------------------------------------------------------------


def test_strip_prefix_colon() -> None:
    """anthropic:claude-sonnet-4-6 resolves to claude-sonnet-4-6 static entry."""
    with patch("httpx.get", side_effect=Exception("no network")):
        result = get_price("anthropic:claude-sonnet-4-6")
    assert result is not None
    assert result.source == "static"
    assert result.input_usd_per_mtok == 3.0


def test_strip_prefix_slash() -> None:
    """openai/claude-sonnet-4-6 also strips to claude-sonnet-4-6."""
    with patch("httpx.get", side_effect=Exception("no network")):
        result = get_price("openai/claude-sonnet-4-6")
    assert result is not None
    assert result.source == "static"


# ---------------------------------------------------------------------------
# 2. Static fallback when LiteLLM fetch fails
# ---------------------------------------------------------------------------


def test_static_fallback_on_fetch_failure() -> None:
    """When httpx.get raises, get_price falls back to static table."""
    with patch("httpx.get", side_effect=ConnectionError("offline")):
        result = get_price("claude-haiku-4-5")
    assert isinstance(result, PriceInfo)
    assert result.source == "static"
    assert result.input_usd_per_mtok == 1.0
    assert result.output_usd_per_mtok == 5.0


# ---------------------------------------------------------------------------
# 3. LiteLLM hit
# ---------------------------------------------------------------------------


def test_litellm_hit() -> None:
    """When LiteLLM fetch succeeds with valid entry, source is 'litellm'."""
    mock_data = {
        "claude-sonnet-4-6": {
            "input_cost_per_token": 0.000002,
            "output_cost_per_token": 0.000010,
        }
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = mock_data

    with patch("httpx.get", return_value=mock_resp):
        result = get_price("claude-sonnet-4-6")

    assert result is not None
    assert result.source == "litellm"
    assert result.input_usd_per_mtok == pytest.approx(2.0)
    assert result.output_usd_per_mtok == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# 4. Timeout fallback
# ---------------------------------------------------------------------------


def test_timeout_falls_back_to_static() -> None:
    """httpx.TimeoutException causes fallback to static pricing."""
    with patch(
        "httpx.get",
        side_effect=httpx.TimeoutException("timed out"),
    ):
        result = get_price("claude-opus-4-8")
    assert result is not None
    assert result.source == "static"
    assert result.input_usd_per_mtok == 5.0


# ---------------------------------------------------------------------------
# 5. Unknown model
# ---------------------------------------------------------------------------


def test_unknown_model_returns_none() -> None:
    """get_price returns None for an unrecognised model."""
    with patch("httpx.get", side_effect=Exception("no network")):
        result = get_price("some-unknown-model")
    assert result is None


# ---------------------------------------------------------------------------
# 6. Cache hit — second call does not re-fetch
# ---------------------------------------------------------------------------


def test_cache_hit_single_fetch() -> None:
    """After the first successful fetch, a second call reuses cached data."""
    mock_data: dict[str, object] = {}
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = mock_data

    with patch("httpx.get", return_value=mock_resp) as mock_get:
        get_price("claude-sonnet-4-6")
        get_price("claude-sonnet-4-6")

    mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# 7. compute_cost returns None for unknown model
# ---------------------------------------------------------------------------


def test_compute_cost_unknown_model() -> None:
    """compute_cost returns None when the model has no pricing data."""
    with patch("httpx.get", side_effect=Exception("no network")):
        result = compute_cost("unknown-model-xyz", {}, {})
    assert result is None


# ---------------------------------------------------------------------------
# 8. compute_cost happy path
# ---------------------------------------------------------------------------


def test_compute_cost_happy_path() -> None:
    """compute_cost returns expected dict shape and correct USD values."""
    with patch("httpx.get", side_effect=Exception("no network")):
        # claude-sonnet-4-6 static: input=3.0, output=15.0 per M tokens
        phases = {
            "parse": {"input_tokens": 1_000_000, "output_tokens": 500_000},
            "codegen": {"input_tokens": 2_000_000, "output_tokens": 1_000_000},
        }
        total = {"input_tokens": 3_000_000, "output_tokens": 1_500_000}
        result = compute_cost("claude-sonnet-4-6", phases, total)

    assert result is not None
    assert "total_usd" in result
    assert "per_phase_usd" in result
    assert "prices" in result
    assert "price_source" in result

    assert result["price_source"] == "static"
    assert result["prices"]["input_usd_per_mtok"] == 3.0
    assert result["prices"]["output_usd_per_mtok"] == 15.0

    # parse: 1*3 + 0.5*15 = 3 + 7.5 = 10.5
    assert result["per_phase_usd"]["parse"] == pytest.approx(10.5, rel=1e-5)
    # codegen: 2*3 + 1*15 = 6 + 15 = 21.0
    assert result["per_phase_usd"]["codegen"] == pytest.approx(21.0, rel=1e-5)
    # total: 3*3 + 1.5*15 = 9 + 22.5 = 31.5
    assert result["total_usd"] == pytest.approx(31.5, rel=1e-5)
