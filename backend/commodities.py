"""Commodity routes: crude oil spot prices from EIA (backend/eia.py).

Gold and silver are stored daily futures bars (see src/data/update_equities.py),
served through /api/assets and /api/instruments like the stocks and indices.
"""
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend import config, eia
from backend.schemas.market import SourceMeta

router = APIRouter(prefix="/api/commodities", tags=["commodities"])

NOT_COVERED = (
    "Gold and silver are not from EIA: they are stored end-of-day COMEX futures prices from Yahoo Finance "
    "(personal use)."
)


class PricePoint(BaseModel):
    date: str
    value: Optional[float]  # None: EIA reported no price for this date


class CommoditySummary(BaseModel):
    id: str
    label: str
    units: Optional[str] = None
    currency: str = "USD"
    unit: str = "per barrel"
    latest: Optional[PricePoint] = None
    previous: Optional[PricePoint] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    missing: int = 0
    status: str
    error: Optional[str] = None
    meta: Optional[SourceMeta] = None


class CommodityList(BaseModel):
    configured: bool
    citation: str
    source_url: str
    release_note: str
    not_covered: str
    count: int
    commodities: list[CommoditySummary]


class CommodityHistory(CommoditySummary):
    observations: list[PricePoint]


RELEASE_NOTE = (
    "Daily spot prices that EIA releases once a week, so the newest value can be several days old."
)


def _citation(prices: Optional[eia.OilPrices]) -> str:
    when = datetime.fromtimestamp(prices.fetched_wall, tz=timezone.utc) if prices else datetime.now(timezone.utc)
    return f"{eia.CITATION} ({when:%b %Y})."


def _summary(series_id: str, prices: eia.OilPrices) -> dict:
    observations = prices.series.get(series_id, [])
    latest, previous = eia.latest_two(observations)
    return {
        "id": series_id,
        "label": eia.SERIES[series_id],
        "units": prices.units.get(series_id),
        "latest": latest,
        "previous": previous,
        "change": round(latest["value"] - previous["value"], 6) if latest and previous else None,
        "change_pct": round((latest["value"] / previous["value"] - 1) * 100, 6) if latest and previous else None,
        "missing": prices.missing.get(series_id, 0),
        "status": "historical" if latest else "unavailable",
        "error": None if latest else "EIA returned no prices for this series",
        "meta": SourceMeta(
            provider=eia.PROVIDER,
            endpoint=urlparse(config.EIA_BASE_URL).netloc or None,
            status="cached" if any(n.startswith("EIA unavailable") for n in prices.notes) else "historical",
            retrieved_at=datetime.fromtimestamp(prices.fetched_wall, tz=timezone.utc),
            source_timestamp=datetime.fromisoformat(latest["date"]).replace(tzinfo=timezone.utc) if latest else None,
            cache_age_seconds=round(eia._monotonic() - prices.fetched_mono, 1),
            notes=prices.notes,
        ),
    }


def _unavailable(series_id: str, error: str) -> dict:
    return {"id": series_id, "label": eia.SERIES[series_id], "status": "unavailable", "error": error}


@router.get("", response_model=CommodityList)
async def list_commodities():
    """Latest WTI and Brent spot prices. Without a key, both are unavailable and nothing is sent."""
    prices = None
    if not eia.configured():
        items = [_unavailable(sid, "EIA_API_KEY is not set") for sid in eia.SERIES]
    else:
        try:
            prices = await eia.oil_prices()
        except eia.EiaError as exc:
            items = [_unavailable(sid, str(exc)) for sid in eia.SERIES]
        else:
            items = [_summary(sid, prices) for sid in eia.SERIES]

    return {
        "configured": eia.configured(),
        "citation": _citation(prices),
        "source_url": eia.SOURCE_URL,
        "release_note": RELEASE_NOTE,
        "not_covered": NOT_COVERED,
        "count": len(items),
        "commodities": items,
    }


@router.get("/history", response_model=CommodityHistory)
async def commodity_history(series: str = Query(..., min_length=1, max_length=16)):
    """Daily spot prices (last ten years, oldest first; missing values are null)."""
    if series not in eia.SERIES:
        raise HTTPException(status_code=404, detail=f"Unknown series: {series}. Available: {', '.join(eia.SERIES)}")
    if not eia.configured():
        raise HTTPException(status_code=503, detail="Oil prices are not configured: set EIA_API_KEY on the server.")
    try:
        prices = await eia.oil_prices()
    except eia.EiaError as exc:
        if exc.retry_after is not None:
            raise HTTPException(
                status_code=503, detail=str(exc),
                headers={"Retry-After": str(max(1, round(exc.retry_after)))},
            ) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {**_summary(series, prices), "observations": prices.series.get(series, [])}
