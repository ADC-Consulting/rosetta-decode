"""LLM pricing lookup with LiteLLM JSON fetch and static fallback."""

import time
from dataclasses import dataclass
from typing import Any

import httpx

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
_CACHE_TTL = 86400  # 24 hours

# module-level cache
_cache: dict[str, Any] | None = None
_cache_ts: float = 0.0

# static fallback: (input_usd_per_mtok, output_usd_per_mtok)
_STATIC: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}


@dataclass
class PriceInfo:
    """Pricing data for a model."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    source: str  # "litellm" | "static"


def _strip_prefix(model: str) -> str:
    """Strip provider prefix like 'anthropic:' or 'openai/'."""
    for sep in (":", "/"):
        if sep in model:
            model = model.split(sep, 1)[1]
    return model


def _fetch_litellm_sync() -> dict[str, Any] | None:
    """Fetch LiteLLM pricing JSON synchronously with 5s timeout."""
    try:
        resp = httpx.get(LITELLM_PRICING_URL, timeout=5.0)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
    except Exception:
        return None


def _get_litellm_data() -> dict[str, Any] | None:
    """Return cached LiteLLM pricing data, refreshing if stale."""
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache
    data = _fetch_litellm_sync()
    if data is not None:
        _cache = data
        _cache_ts = now
    return _cache


def get_price(model: str) -> PriceInfo | None:
    """Return PriceInfo for a model, or None if unknown/unpriced."""
    key = _strip_prefix(model)

    # try LiteLLM
    data = _get_litellm_data()
    if data:
        entry = data.get(key)
        if entry and "input_cost_per_token" in entry and "output_cost_per_token" in entry:
            return PriceInfo(
                input_usd_per_mtok=entry["input_cost_per_token"] * 1_000_000,
                output_usd_per_mtok=entry["output_cost_per_token"] * 1_000_000,
                source="litellm",
            )

    # fallback to static table
    if key in _STATIC:
        inp, out = _STATIC[key]
        return PriceInfo(input_usd_per_mtok=inp, output_usd_per_mtok=out, source="static")

    return None


def compute_cost(
    model: str,
    phases: dict[str, dict[str, int]],
    total: dict[str, int],
) -> dict[str, Any] | None:
    """Compute cost estimate given raw token counts.

    Args:
        model: Model identifier, optionally prefixed (e.g. 'anthropic:claude-sonnet-4-6').
        phases: Per-phase token dicts keyed by phase name.
        total: Aggregate token dict across all phases.

    Returns:
        None if the model is unpriced. Otherwise a dict with keys:
        total_usd, per_phase_usd, prices, price_source.
    """
    price = get_price(model)
    if price is None:
        return None

    def _usd(tokens: dict[str, int]) -> float:
        inp = (tokens.get("input_tokens", 0) + tokens.get("cache_write_tokens", 0)) / 1_000_000
        out = tokens.get("output_tokens", 0) / 1_000_000
        # cache_read is charged at reduced rate; approximate as 0.1x input price
        cache_read = tokens.get("cache_read_tokens", 0) / 1_000_000
        return (
            inp * price.input_usd_per_mtok
            + out * price.output_usd_per_mtok
            + cache_read * price.input_usd_per_mtok * 0.1
        )

    per_phase = {phase: round(_usd(t), 6) for phase, t in phases.items()}
    total_usd = round(_usd(total), 6)

    return {
        "total_usd": total_usd,
        "per_phase_usd": per_phase,
        "prices": {
            "input_usd_per_mtok": price.input_usd_per_mtok,
            "output_usd_per_mtok": price.output_usd_per_mtok,
        },
        "price_source": price.source,
    }
