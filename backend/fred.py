"""US macroeconomic series from FRED (Federal Reserve Bank of St. Louis).

Only the series in SERIES can be requested, so the API is not an open proxy to
FRED. Responses are validated, cached conservatively (macro data changes at
most daily, and FRED allows 120 requests a minute), and when FRED fails a kept
response is served for a while, labelled `cached`. Missing observations (FRED
sends a non-numeric value such as ".") stay missing; nothing is interpolated.

The API key travels as a URL query parameter, so it must never reach a log line
or an error message: errors are rebuilt from status codes and FRED's own
error_message, never from httpx's exception text (which contains the URL).
"""
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from backend import config

log = logging.getLogger("finpulse.fred")

# httpx logs every request URL at INFO level, and FRED's URLs carry the key.
logging.getLogger("httpx").setLevel(logging.WARNING)

PROVIDER = "fred"
NOTICE = (
    "This product uses the FRED® API but is not endorsed or certified by the "
    "Federal Reserve Bank of St. Louis."
)
TERMS_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"

# A small, curated set: inflation, rates, Treasury yields, growth and jobs.
# All are published by US government agencies; FRED's notes are checked at
# runtime anyway, and a series marked "Copyright" is flagged in the response.
# Each has a category and a short label (FRED's own titles are long, and the two
# Treasury yields only differ at the very end of theirs).
SERIES = {
    "CPIAUCSL": "inflation",
    "PCEPILFE": "inflation",
    "FEDFUNDS": "rates",
    "DGS2": "yields",
    "DGS10": "yields",
    "GDPC1": "growth",
    "UNRATE": "employment",
    "PAYEMS": "employment",
}
LABELS = {
    "CPIAUCSL": "Consumer prices (CPI)",
    "PCEPILFE": "Core PCE prices",
    "FEDFUNDS": "Fed funds rate",
    "DGS2": "2-year Treasury yield",
    "DGS10": "10-year Treasury yield",
    "GDPC1": "Real GDP",
    "UNRATE": "Unemployment rate",
    "PAYEMS": "Nonfarm payrolls",
}

HISTORY_YEARS = 10
CACHE_SECONDS = 3600
STALE_MAX_SECONDS = 86_400
REQUEST_TIMEOUT_SECONDS = 15
RATE_LIMIT_BACKOFF_SECONDS = 60

_monotonic = time.monotonic
_wall = time.time


class FredNotConfigured(Exception):
    """No FRED_API_KEY is set."""


class FredError(Exception):
    def __init__(self, message: str, retry_after: Optional[float] = None, status: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.status = status


@dataclass
class SeriesData:
    info: dict
    observations: list[dict]  # {"date": "YYYY-MM-DD", "value": float | None}
    missing: int
    fetched_mono: float
    fetched_wall: float
    notes: list[str] = field(default_factory=list)


_cache: dict[str, SeriesData] = {}
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


def configured() -> bool:
    return bool(config.FRED_API_KEY)


def _redact(text: str) -> str:
    key = config.FRED_API_KEY
    return text.replace(key, "***") if key else text


async def _get(path: str, params: dict) -> dict:
    global _blocked_until
    if not configured():
        raise FredNotConfigured()
    wait = _blocked_until - _monotonic()
    if wait > 0:
        raise FredError(f"FRED rate limit: retry in {wait:.0f}s", retry_after=wait, status=429)

    query = {**params, "api_key": config.FRED_API_KEY, "file_type": "json"}
    try:
        response = await get_client().get(f"{config.FRED_BASE_URL}/{path}", params=query)
    except httpx.TimeoutException:
        raise FredError("FRED did not answer in time") from None
    except httpx.HTTPError as exc:
        # The exception text can contain the request URL, so only its type is kept.
        raise FredError(f"Could not reach FRED ({type(exc).__name__})") from None

    if response.status_code == 429:
        _blocked_until = _monotonic() + RATE_LIMIT_BACKOFF_SECONDS
        raise FredError("FRED rate limit reached", retry_after=RATE_LIMIT_BACKOFF_SECONDS, status=429)

    try:
        body = response.json()
    except ValueError:
        body = None

    if response.status_code != 200:
        message = body.get("error_message") if isinstance(body, dict) else None
        raise FredError(
            _redact(f"FRED answered {response.status_code}" + (f": {message}" if message else "")),
            status=response.status_code,
        )
    if not isinstance(body, dict):
        raise FredError("FRED sent a response that is not a JSON object")
    return body


def parse_info(body: dict, series_id: str) -> dict:
    items = body.get("seriess")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise FredError(f"FRED sent no metadata for {series_id}")
    info = items[0]
    if info.get("id") != series_id:
        raise FredError(f"FRED sent metadata for {info.get('id')!r}, not {series_id}")
    for name in ("title", "units", "frequency"):
        if not isinstance(info.get(name), str) or not info[name]:
            raise FredError(f"FRED metadata for {series_id} has no {name}")
    return info


def _number(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_observations(body: dict, series_id: str) -> tuple[list[dict], int]:
    """(observations oldest first, count of missing values). Raises FredError if malformed."""
    rows = body.get("observations")
    if not isinstance(rows, list):
        raise FredError(f"FRED sent no observations list for {series_id}")

    observations, missing, previous = [], 0, None
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise FredError(f"{series_id} observation {index} is not an object")
        try:
            day = date.fromisoformat(str(row.get("date")))
        except ValueError:
            raise FredError(f"{series_id} observation {index} has an invalid date") from None
        if previous is not None and day <= previous:
            raise FredError(f"{series_id} observations are not in increasing date order")
        previous = day

        value = _number(row.get("value"))
        if value is None:
            missing += 1
        observations.append({"date": day.isoformat(), "value": value})
    return observations, missing


def parse_last_updated(value) -> Optional[datetime]:
    """FRED's last_updated, e.g. "2026-10-15 07:48:02-05", as an aware datetime."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) >= 3 and text[-3] in "+-" and text[-2:].isdigit():
        text += ":00"  # "-05" -> "-05:00" so fromisoformat accepts it
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _copyright_note(info: dict) -> list[str]:
    if "copyright" in str(info.get("notes", "")).lower():
        return ["FRED marks this series as copyrighted by a third party; use beyond personal research may need the owner's permission."]
    return []


async def fetch_series(series_id: str) -> SeriesData:
    """Metadata and the last HISTORY_YEARS of observations, cached; a kept copy if FRED fails."""
    if series_id not in SERIES:
        raise KeyError(series_id)

    cached = _cache.get(series_id)
    if cached and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
        return cached

    try:
        info = parse_info(await _get("series", {"series_id": series_id}), series_id)
        start = (datetime.fromtimestamp(_wall(), tz=timezone.utc).date() - timedelta(days=365 * HISTORY_YEARS))
        observations, missing = parse_observations(
            await _get("series/observations", {
                "series_id": series_id,
                "observation_start": start.isoformat(),
                "sort_order": "asc",
            }),
            series_id,
        )
    except FredError as exc:
        if cached and _monotonic() - cached.fetched_mono <= STALE_MAX_SECONDS:
            log.warning("Serving cached FRED %s: %s", series_id, exc)
            return SeriesData(
                cached.info, cached.observations, cached.missing, cached.fetched_mono,
                cached.fetched_wall, cached.notes + [f"FRED unavailable, showing the last response. {exc}"],
            )
        raise

    data = SeriesData(info, observations, missing, _monotonic(), _wall(), _copyright_note(info))
    _cache[series_id] = data
    return data


def latest_two(observations: list[dict]) -> tuple[Optional[dict], Optional[dict]]:
    """The newest observation with a value, and the one with a value before it."""
    present = [row for row in observations if row["value"] is not None]
    return (present[-1] if present else None, present[-2] if len(present) > 1 else None)
