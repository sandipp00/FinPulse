"""FX routes: ECB euro reference rates and cross rates derived from them (backend/fx.py)."""
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend import config, fx
from backend.schemas.market import SourceMeta

router = APIRouter(prefix="/api/fx", tags=["fx"])


class RatePoint(BaseModel):
    date: str
    rate: float


class PairSummary(BaseModel):
    pair: str
    base: str
    quote: str
    derived: bool
    method: str
    latest: Optional[RatePoint] = None
    previous: Optional[RatePoint] = None
    change_pct: Optional[float] = None
    status: str
    error: Optional[str] = None
    meta: Optional[SourceMeta] = None


class PairList(BaseModel):
    notice: str
    source_url: str
    count: int
    pairs: list[PairSummary]


class PairHistory(PairSummary):
    observations: list[RatePoint]


def _method(pair: str) -> str:
    base, quote = fx.PAIRS[pair]
    if not fx.is_derived(pair):
        return f"ECB reference rate: {quote} per 1 EUR, as published."
    return (
        f"Cross rate derived by FinPulse: (EUR/{quote}) ÷ (EUR/{base}) from the same day's ECB rates. "
        "Not published by the ECB."
    )


def _meta(rates: fx.EuroRates, latest: Optional[dict]) -> SourceMeta:
    return SourceMeta(
        provider=fx.PROVIDER,
        endpoint=urlparse(config.FX_BASE_URL).netloc or None,
        status="cached" if rates.notes else "historical",
        retrieved_at=datetime.fromtimestamp(rates.fetched_wall, tz=timezone.utc),
        # The ECB stamps a rate with its publication day only (around 16:00 CET).
        source_timestamp=datetime.fromisoformat(latest["date"]).replace(tzinfo=timezone.utc) if latest else None,
        cache_age_seconds=round(fx._monotonic() - rates.fetched_mono, 1),
        notes=rates.notes,
    )


def _summary(pair: str, rates: fx.EuroRates) -> tuple[dict, list[dict]]:
    base, quote = fx.PAIRS[pair]
    series = fx.pair_series(rates, pair)
    latest = series[-1] if series else None
    previous = series[-2] if len(series) > 1 else None
    summary = {
        "pair": pair,
        "base": base,
        "quote": quote,
        "derived": fx.is_derived(pair),
        "method": _method(pair),
        "latest": latest,
        "previous": previous,
        "change_pct": round((latest["rate"] / previous["rate"] - 1) * 100, 6) if latest and previous else None,
        "status": "historical" if latest else "unavailable",
        "error": None if latest else "The source returned no rates for this pair",
        "meta": _meta(rates, latest),
    }
    return summary, series


def _http_error(exc: fx.FxError) -> HTTPException:
    if exc.retry_after is not None:
        return HTTPException(
            status_code=503, detail=str(exc),
            headers={"Retry-After": str(max(1, round(exc.retry_after)))},
        )
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/pairs", response_model=PairList)
async def list_pairs():
    """Latest ECB-based rate for each tracked pair, with the change from the previous publication."""
    try:
        rates = await fx.euro_rates()
    except fx.FxError as exc:
        pairs = [
            {
                "pair": pair, "base": base, "quote": quote, "derived": fx.is_derived(pair),
                "method": _method(pair), "status": "unavailable", "error": str(exc),
            }
            for pair, (base, quote) in fx.PAIRS.items()
        ]
    else:
        pairs = [_summary(pair, rates)[0] for pair in fx.PAIRS]

    return {"notice": fx.SOURCE_NOTE, "source_url": fx.ECB_URL, "count": len(pairs), "pairs": pairs}


@router.get("/history", response_model=PairHistory)
async def pair_history(pair: str = Query(..., min_length=7, max_length=7)):
    """Daily history (last ten years, oldest first) for one pair, e.g. ?pair=USD/INR."""
    if pair not in fx.PAIRS:
        raise HTTPException(status_code=404, detail=f"Unknown pair: {pair}. Available: {', '.join(fx.PAIRS)}")
    try:
        rates = await fx.euro_rates()
    except fx.FxError as exc:
        raise _http_error(exc) from exc

    summary, series = _summary(pair, rates)
    return {**summary, "observations": series}
