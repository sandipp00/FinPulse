"""Crude oil spot prices from the U.S. Energy Information Administration (API v2).

Two daily series from the petroleum spot-price dataset: WTI at Cushing, OK
(RWTC) and Brent, Europe (RBRTE). EIA releases these daily prices once a week,
so the newest value can be several days old; responses carry the observation
date and never call it live.

One request asks for both series over the history window, paging through
EIA's 5,000-row limit. Responses are validated, cached for an hour, and kept
for up to STALE_MAX_SECONDS (labelled `cached`) when EIA fails. As with FRED,
the key travels in the URL, so errors are rebuilt without the request URL
and httpx's request logging stays at WARNING.
"""
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from backend import config

log = logging.getLogger("finpulse.eia")

# httpx logs every request URL at INFO level, and EIA's URLs carry the key.
logging.getLogger("httpx").setLevel(logging.WARNING)

PROVIDER = "eia"
ROUTE = "petroleum/pri/spt/data/"
CITATION = "Source: U.S. Energy Information Administration"
SOURCE_URL = "https://www.eia.gov/petroleum/data.php"

# EIA series id -> short label.
SERIES = {
    "RWTC": "WTI crude oil (Cushing, OK)",
    "RBRTE": "Brent crude oil (Europe)",
}

HISTORY_YEARS = 10
PAGE_LENGTH = 5000
MAX_PAGES = 4
CACHE_SECONDS = 3600
STALE_MAX_SECONDS = 3 * 86_400
REQUEST_TIMEOUT_SECONDS = 20
RATE_LIMIT_BACKOFF_SECONDS = 60

_monotonic = time.monotonic
_wall = time.time


class EiaNotConfigured(Exception):
    """No EIA_API_KEY is set."""


class EiaError(Exception):
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class OilPrices:
    series: dict[str, list[dict]]  # id -> [{"date", "value": float | None}] oldest first
    units: dict[str, Optional[str]]
    missing: dict[str, int]
    fetched_mono: float
    fetched_wall: float
    notes: list[str] = field(default_factory=list)


_cache: Optional[OilPrices] = None
_blocked_until = 0.0
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    global _cache, _blocked_until
    _cache = None
    _blocked_until = 0.0


def configured() -> bool:
    return bool(config.EIA_API_KEY)


def _redact(text: str) -> str:
    key = config.EIA_API_KEY
    return text.replace(key, "***") if key else text


def _value(raw) -> Optional[float]:
    # EIA returns values as strings (API v2.1.6+); an empty or null value is missing.
    if raw is None or isinstance(raw, bool):
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def parse_page(body) -> tuple[list[dict], int, list[str]]:
    """(rows, total, warnings) from one EIA response. Raises EiaError if malformed."""
    if not isinstance(body, dict):
        raise EiaError("EIA sent a response that is not a JSON object")
    response = body.get("response")
    if not isinstance(response, dict):
        raise EiaError("EIA sent no response object")
    rows = response.get("data")
    if not isinstance(rows, list):
        raise EiaError("EIA sent no data list")
    try:
        total = int(response.get("total"))
    except (TypeError, ValueError):
        raise EiaError("EIA sent no row total") from None

    warnings = []
    for item in (body, response):
        if item.get("warning"):
            warnings.append(f"EIA warning: {item.get('warning')} {item.get('description') or ''}".strip())
    return rows, total, warnings


def group_rows(rows: list) -> tuple[dict[str, list[dict]], dict[str, Optional[str]], dict[str, int]]:
    """Rows -> per-series observations (oldest first), units and missing counts."""
    by_series: dict[str, dict[str, Optional[float]]] = {sid: {} for sid in SERIES}
    units: dict[str, Optional[str]] = {sid: None for sid in SERIES}
    missing = {sid: 0 for sid in SERIES}

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise EiaError(f"EIA row {index} is not an object")
        series_id = row.get("series")
        if series_id not in SERIES:
            raise EiaError(f"EIA row {index} has an unexpected series {series_id!r}")
        try:
            day = date.fromisoformat(str(row.get("period"))).isoformat()
        except ValueError:
            raise EiaError(f"EIA row {index} has an invalid period") from None
        if day in by_series[series_id]:
            raise EiaError(f"EIA rows repeat {series_id} on {day}")
        if "value" not in row:
            raise EiaError(f"EIA row {index} has no value column")

        value = _value(row.get("value"))
        if value is None:
            missing[series_id] += 1
        by_series[series_id][day] = value
        unit = row.get("units") or row.get("value-units")
        if isinstance(unit, str) and unit:
            units[series_id] = unit

    series = {
        sid: [{"date": day, "value": value} for day, value in sorted(values.items())]
        for sid, values in by_series.items()
    }
    return series, units, missing


async def _get_page(start: date, offset: int) -> dict:
    global _blocked_until
    if not configured():
        raise EiaNotConfigured()
    wait = _blocked_until - _monotonic()
    if wait > 0:
        raise EiaError(f"EIA rate limit: retry in {wait:.0f}s", retry_after=wait)

    params = [
        ("api_key", config.EIA_API_KEY),
        ("frequency", "daily"),
        ("data[0]", "value"),
        *[("facets[series][]", sid) for sid in SERIES],
        ("start", start.isoformat()),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
        ("offset", str(offset)),
        ("length", str(PAGE_LENGTH)),
    ]
    try:
        response = await get_client().get(f"{config.EIA_BASE_URL}/{ROUTE}", params=params)
    except httpx.TimeoutException:
        raise EiaError("EIA did not answer in time") from None
    except httpx.HTTPError as exc:
        # The exception text can contain the request URL (and so the key).
        raise EiaError(f"Could not reach EIA ({type(exc).__name__})") from None

    if response.status_code == 429:
        _blocked_until = _monotonic() + RATE_LIMIT_BACKOFF_SECONDS
        raise EiaError("EIA rate limit reached", retry_after=RATE_LIMIT_BACKOFF_SECONDS)

    try:
        body = response.json()
    except ValueError:
        raise EiaError(f"EIA answered {response.status_code} without JSON") from None

    error = body.get("error") if isinstance(body, dict) else None
    if response.status_code != 200 or error:
        raise EiaError(_redact(f"EIA answered {response.status_code}" + (f": {error}" if error else "")))
    return body


async def oil_prices() -> OilPrices:
    """Both series for the last HISTORY_YEARS, cached; a kept copy if EIA fails."""
    global _cache
    if _cache and _monotonic() - _cache.fetched_mono < CACHE_SECONDS:
        return _cache

    start = datetime.fromtimestamp(_wall(), tz=timezone.utc).date() - timedelta(days=365 * HISTORY_YEARS)
    try:
        rows, notes, offset, total = [], [], 0, None
        for _ in range(MAX_PAGES):
            page, total, warnings = parse_page(await _get_page(start, offset))
            rows.extend(page)
            notes.extend(warnings)
            offset += len(page)
            if not page or offset >= total:
                break
        else:
            raise EiaError(f"EIA has more rows ({total}) than FinPulse pages through")
        series, units, missing = group_rows(rows)
    except EiaError as exc:
        if _cache and _monotonic() - _cache.fetched_mono <= STALE_MAX_SECONDS:
            log.warning("Serving cached EIA prices: %s", exc)
            return OilPrices(
                _cache.series, _cache.units, _cache.missing, _cache.fetched_mono, _cache.fetched_wall,
                [f"EIA unavailable, showing the last response. {exc}"],
            )
        raise

    _cache = OilPrices(series, units, missing, _monotonic(), _wall(), notes)
    return _cache


def latest_two(observations: list[dict]) -> tuple[Optional[dict], Optional[dict]]:
    present = [row for row in observations if row["value"] is not None]
    return (present[-1] if present else None, present[-2] if len(present) > 1 else None)
