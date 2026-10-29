"""US macroeconomic data routes (FRED). See backend/fred.py for the adapter."""
import asyncio
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import config, fred
from backend.schemas.market import SourceMeta

router = APIRouter(prefix="/api/macro", tags=["macro"])


class Observation(BaseModel):
    date: str
    value: Optional[float]  # None: FRED had no value for this date


class SeriesSummary(BaseModel):
    id: str
    category: str
    label: str
    title: Optional[str] = None
    units: Optional[str] = None
    units_short: Optional[str] = None
    frequency: Optional[str] = None
    seasonal_adjustment: Optional[str] = None
    latest: Optional[Observation] = None
    previous: Optional[Observation] = None
    change: Optional[float] = None
    last_updated: Optional[datetime] = None
    missing: int = 0
    status: str
    error: Optional[str] = None
    meta: Optional[SourceMeta] = None


class SeriesList(BaseModel):
    configured: bool
    notice: str
    terms_url: str
    count: int
    series: list[SeriesSummary]


class SeriesDetail(SeriesSummary):
    notes: Optional[str] = None
    observations: list[Observation]


def _meta(data: fred.SeriesData) -> SourceMeta:
    latest, _ = fred.latest_two(data.observations)
    stale = any(note.startswith("FRED unavailable") for note in data.notes)
    return SourceMeta(
        provider=fred.PROVIDER,
        endpoint=urlparse(config.FRED_BASE_URL).netloc or None,
        status="cached" if stale else "historical",
        retrieved_at=datetime.fromtimestamp(data.fetched_wall, tz=timezone.utc),
        source_timestamp=datetime.fromisoformat(latest["date"]).replace(tzinfo=timezone.utc) if latest else None,
        cache_age_seconds=round(fred._monotonic() - data.fetched_mono, 1),
        notes=data.notes,
    )


def _summary(series_id: str, data: fred.SeriesData) -> dict:
    info = data.info
    latest, previous = fred.latest_two(data.observations)
    return {
        "id": series_id,
        "category": fred.SERIES[series_id],
        "label": fred.LABELS[series_id],
        "title": info.get("title"),
        "units": info.get("units"),
        "units_short": info.get("units_short"),
        "frequency": info.get("frequency"),
        "seasonal_adjustment": info.get("seasonal_adjustment_short"),
        "latest": latest,
        "previous": previous,
        "change": round(latest["value"] - previous["value"], 6) if latest and previous else None,
        "last_updated": fred.parse_last_updated(info.get("last_updated")),
        "missing": data.missing,
        "status": "historical" if latest else "unavailable",
        "meta": _meta(data),
    }


def _http_error(exc: fred.FredError) -> HTTPException:
    if exc.retry_after is not None:
        return HTTPException(
            status_code=503, detail=str(exc),
            headers={"Retry-After": str(max(1, round(exc.retry_after)))},
        )
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/series", response_model=SeriesList)
async def list_series():
    """Latest value of each curated series. Without a key, every series is unavailable."""
    if not fred.configured():
        series = [
            {"id": sid, "category": category, "label": fred.LABELS[sid], "status": "unavailable",
             "error": "FRED_API_KEY is not set"}
            for sid, category in fred.SERIES.items()
        ]
    else:
        ids = list(fred.SERIES)
        results = await asyncio.gather(*(fred.fetch_series(sid) for sid in ids), return_exceptions=True)
        series = []
        for sid, result in zip(ids, results):
            if isinstance(result, fred.FredError):
                series.append({
                    "id": sid, "category": fred.SERIES[sid], "label": fred.LABELS[sid],
                    "status": "unavailable", "error": str(result),
                })
            elif isinstance(result, Exception):
                raise result
            else:
                series.append(_summary(sid, result))

    return {
        "configured": fred.configured(),
        "notice": fred.NOTICE,
        "terms_url": fred.TERMS_URL,
        "count": len(series),
        "series": series,
    }


@router.get("/series/{series_id}", response_model=SeriesDetail)
async def series_detail(series_id: str):
    """One series with its observations (last ten years, oldest first; missing values are null)."""
    if series_id not in fred.SERIES:
        raise HTTPException(status_code=404, detail=f"Unknown series: {series_id}. Available: {', '.join(fred.SERIES)}")
    if not fred.configured():
        raise HTTPException(status_code=503, detail="Macro data is not configured: set FRED_API_KEY on the server.")
    try:
        data = await fred.fetch_series(series_id)
    except fred.FredError as exc:
        raise _http_error(exc) from exc

    return {**_summary(series_id, data), "notes": data.info.get("notes"), "observations": data.observations}
