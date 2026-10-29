"""FX rates: ECB euro reference rates, fetched through the Frankfurter API.

The ECB publishes one rate per currency against the euro, around 16:00 CET on
TARGET working days, "for information purposes only". Pairs without the euro
(USD/INR, GBP/USD, USD/JPY) are cross rates that FinPulse derives from two of
those euro rates; the ECB does not publish them, and responses say so.

One request fetches every needed currency for the whole history window, which
is then cached for an hour. When the source fails, the last response is served
for up to STALE_MAX_SECONDS, labelled `cached`. Days without a publication
(weekends, TARGET holidays) simply have no observation; nothing is filled in.
"""
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from backend import config

log = logging.getLogger("finpulse.fx")

PROVIDER = "ecb"
SOURCE_NOTE = (
    "Euro foreign exchange reference rates from the European Central Bank (source: ECB), "
    "via the Frankfurter API. Published around 16:00 CET on TARGET working days, "
    "for information purposes only."
)
ECB_URL = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html"

CURRENCIES = ("USD", "GBP", "JPY", "INR")

# pair -> (base, quote). A pair is "derived" unless EUR is its base.
PAIRS = {
    "EUR/USD": ("EUR", "USD"),
    "EUR/GBP": ("EUR", "GBP"),
    "EUR/JPY": ("EUR", "JPY"),
    "EUR/INR": ("EUR", "INR"),
    "GBP/USD": ("GBP", "USD"),
    "USD/JPY": ("USD", "JPY"),
    "USD/INR": ("USD", "INR"),
}

HISTORY_YEARS = 10
CACHE_SECONDS = 3600
STALE_MAX_SECONDS = 3 * 86_400
REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_RETRY_AFTER_SECONDS = 60
MAX_RETRY_AFTER_SECONDS = 600

_monotonic = time.monotonic
_wall = time.time


class FxError(Exception):
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class EuroRates:
    """ECB rates per date: {"2026-10-29": {"USD": 1.113, "GBP": ...}}, oldest date first."""
    by_date: dict[str, dict[str, float]]
    fetched_mono: float
    fetched_wall: float
    notes: list[str] = field(default_factory=list)


_cache: Optional[EuroRates] = None
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


def is_derived(pair: str) -> bool:
    return PAIRS[pair][0] != "EUR"


def parse_rates(body) -> dict[str, dict[str, float]]:
    """Frankfurter's [{date, base, quote, rate}, ...] -> rates per date. Raises FxError if malformed."""
    if not isinstance(body, list):
        raise FxError("The FX source did not send a list of rates")

    by_date: dict[str, dict[str, float]] = {}
    for index, row in enumerate(body):
        if not isinstance(row, dict):
            raise FxError(f"FX row {index} is not an object")
        if row.get("base") != "EUR":
            raise FxError(f"FX row {index} is not quoted against EUR")
        quote = row.get("quote")
        if quote not in CURRENCIES:
            raise FxError(f"FX row {index} has an unexpected currency {quote!r}")
        try:
            day = date.fromisoformat(str(row.get("date"))).isoformat()
        except ValueError:
            raise FxError(f"FX row {index} has an invalid date") from None
        rate = row.get("rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
            raise FxError(f"FX row {index} has an invalid rate")
        if quote in by_date.get(day, {}):
            raise FxError(f"FX rows repeat {quote} on {day}")
        by_date.setdefault(day, {})[quote] = float(rate)

    return dict(sorted(by_date.items()))


def _retry_after(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        seconds = DEFAULT_RETRY_AFTER_SECONDS
    if not math.isfinite(seconds) or seconds <= 0:
        seconds = DEFAULT_RETRY_AFTER_SECONDS
    return min(seconds, MAX_RETRY_AFTER_SECONDS)


async def _request(start: date) -> dict[str, dict[str, float]]:
    global _blocked_until
    wait = _blocked_until - _monotonic()
    if wait > 0:
        raise FxError(f"FX source rate limit: retry in {wait:.0f}s", retry_after=wait)

    params = {
        "base": "EUR",
        "quotes": ",".join(CURRENCIES),
        "providers": "ecb",
        "from": start.isoformat(),
    }
    try:
        response = await get_client().get(f"{config.FX_BASE_URL}/rates", params=params)
    except httpx.TimeoutException:
        raise FxError("The FX source did not answer in time") from None
    except httpx.HTTPError as exc:
        raise FxError(f"Could not reach the FX source ({type(exc).__name__})") from None

    if response.status_code == 429:
        seconds = _retry_after(response)
        _blocked_until = _monotonic() + seconds
        raise FxError("FX source rate limit reached", retry_after=seconds)

    try:
        body = response.json()
    except ValueError:
        raise FxError(f"The FX source answered {response.status_code} without JSON") from None

    if response.status_code != 200:
        message = body.get("message") if isinstance(body, dict) else None
        raise FxError(f"The FX source answered {response.status_code}" + (f": {message}" if message else ""))
    return parse_rates(body)


async def euro_rates() -> EuroRates:
    """The cached ECB euro rates, refreshed hourly; a kept copy if the source fails."""
    global _cache
    if _cache and _monotonic() - _cache.fetched_mono < CACHE_SECONDS:
        return _cache

    start = datetime.fromtimestamp(_wall(), tz=timezone.utc).date() - timedelta(days=365 * HISTORY_YEARS)
    try:
        by_date = await _request(start)
    except FxError as exc:
        if _cache and _monotonic() - _cache.fetched_mono <= STALE_MAX_SECONDS:
            log.warning("Serving cached FX rates: %s", exc)
            return EuroRates(
                _cache.by_date, _cache.fetched_mono, _cache.fetched_wall,
                [f"FX source unavailable, showing the last response. {exc}"],
            )
        raise

    _cache = EuroRates(by_date, _monotonic(), _wall())
    return _cache


def pair_series(rates: EuroRates, pair: str) -> list[dict]:
    """[{date, rate}] for a pair, oldest first. A date missing either currency is skipped."""
    base, quote = PAIRS[pair]
    series = []
    for day, row in rates.by_date.items():
        base_rate = 1.0 if base == "EUR" else row.get(base)
        quote_rate = row.get(quote)
        if base_rate and quote_rate:
            series.append({"date": day, "rate": quote_rate / base_rate})
    return series
