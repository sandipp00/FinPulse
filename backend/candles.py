"""Historical OHLCV candles for the live symbols, from Binance klines.

Crypto comes from the spot API; live gold and silver (config.METAL_LIVE_SYMBOLS)
from the USD-M futures API, which returns klines in the same format.

Binance's public REST API needs no key. Responses are cached for a few seconds
so many browser tabs (or rapid timeframe switches) don't hammer the exchange.

Every response is validated before use: a malformed one counts as a failure of
that endpoint, and the next configured endpoint is tried. An endpoint that
answers 429/418 (rate limited / banned) is skipped until its Retry-After passes.
When every endpoint fails, callers that opt in get the last good response,
labelled `cached` with its age, for up to STALE_MAX_SECONDS; nothing is invented.
"""
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from backend import config
from backend.schemas.market import SourceMeta

log = logging.getLogger("finpulse.candles")

PROVIDER = "binance"
INTERVALS = ("1m", "15m", "1h", "1d")
MIN_LIMIT = 50
MAX_LIMIT = 1000
CACHE_SECONDS = 5
# How old a kept response may be and still be served (labelled) when Binance fails.
STALE_MAX_SECONDS = 300
REQUEST_TIMEOUT_SECONDS = 10
# Used when a 429/418 has no usable Retry-After; and the longest we honour.
DEFAULT_RETRY_AFTER_SECONDS = 60
MAX_RETRY_AFTER_SECONDS = 600

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{2,12}/[A-Z0-9]{2,12}$")

# Patchable clocks, so tests can move time without sleeping.
_monotonic = time.monotonic
_wall = time.time


@dataclass
class _CacheEntry:
    fetched_mono: float
    fetched_wall: float
    candles: list[dict]
    endpoint: str


@dataclass
class CandleSeries:
    candles: list[dict]
    meta: SourceMeta


_cache: dict[tuple, _CacheEntry] = {}
# Endpoint base URL -> monotonic time until which it is not asked again.
_blocked_until: dict[str, float] = {}

# One long-lived client: reusing its connections avoids a fresh TLS handshake
# on every request (about 1s each), which matters when five symbols load at once.
_client: httpx.AsyncClient | None = None


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


class CandleSourceError(Exception):
    """Every configured Binance endpoint failed."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        # Set when every endpoint is rate limited: seconds until one may be asked again.
        self.retry_after = retry_after


class MalformedResponse(ValueError):
    """The provider answered, but not with valid klines."""


class RateLimited(Exception):
    def __init__(self, retry_after: float):
        super().__init__(f"rate limited for {retry_after:.0f}s")
        self.retry_after = retry_after


def _number(value, field: str, index: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise MalformedResponse(f"row {index}: {field} is not a number") from None
    if not math.isfinite(number):
        raise MalformedResponse(f"row {index}: {field} is not finite")
    return number


def parse_klines(rows) -> list[dict]:
    """Binance kline arrays -> candles with a unix-seconds `time`.

    Raises MalformedResponse unless every row is a well-formed, internally
    consistent bar and the bars are in strictly increasing time order.
    """
    if not isinstance(rows, list):
        raise MalformedResponse(f"expected a list of klines, got {type(rows).__name__}")

    candles = []
    previous_time = None
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise MalformedResponse(f"row {index}: expected at least 6 fields")
        if isinstance(row[0], bool) or not isinstance(row[0], int) or row[0] <= 0:
            raise MalformedResponse(f"row {index}: open time is not a positive integer")

        open_, high, low, close, volume = (
            _number(row[i], name, index)
            for i, name in enumerate(("open", "high", "low", "close", "volume"), start=1)
        )
        if min(open_, high, low, close) <= 0:
            raise MalformedResponse(f"row {index}: prices must be positive")
        if volume < 0:
            raise MalformedResponse(f"row {index}: volume is negative")
        if not low <= min(open_, close) <= max(open_, close) <= high:
            raise MalformedResponse(f"row {index}: open/close outside the low-high range")

        candle_time = row[0] // 1000
        if previous_time is not None and candle_time <= previous_time:
            raise MalformedResponse(f"row {index}: times are not increasing")
        previous_time = candle_time

        candles.append({
            "time": candle_time,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
    return candles


def _retry_after(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        seconds = DEFAULT_RETRY_AFTER_SECONDS
    if not math.isfinite(seconds) or seconds <= 0:
        seconds = DEFAULT_RETRY_AFTER_SECONDS
    return min(seconds, MAX_RETRY_AFTER_SECONDS)


async def _get_json(client: httpx.AsyncClient, url: str, params: dict):
    response = await client.get(url, params=params)
    # 429: over the request-weight limit. 418: IP banned for ignoring 429s.
    if response.status_code in (418, 429):
        raise RateLimited(_retry_after(response))
    response.raise_for_status()
    return response.json()


def _host(base: str) -> str:
    return urlparse(base).netloc or base


def _utc(seconds: float | None) -> datetime | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, tz=timezone.utc)


def _meta(entry: _CacheEntry, status: str, notes: list[str]) -> SourceMeta:
    newest = entry.candles[-1]["time"] if entry.candles else None
    return SourceMeta(
        provider=PROVIDER,
        endpoint=_host(entry.endpoint),
        status=status,
        retrieved_at=_utc(entry.fetched_wall),
        source_timestamp=_utc(newest),
        cache_age_seconds=round(_monotonic() - entry.fetched_mono, 1),
        notes=notes,
    )


def validate_request(symbol: str, interval: str, limit: int) -> None:
    if not SYMBOL_PATTERN.match(symbol):
        raise ValueError(f"Invalid symbol format: {symbol!r}")
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported interval: {interval!r}")
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}")


def _endpoints(symbol: str) -> tuple[list[str], str]:
    """(REST bases, klines path) for a symbol's market."""
    if symbol in config.METAL_LIVE_SYMBOLS:
        return config.BINANCE_FUTURES_REST_URLS, "/fapi/v1/klines"
    return config.BINANCE_REST_URLS, "/api/v3/klines"


async def fetch_candle_series(
    symbol: str, interval: str, limit: int, allow_stale: bool = False
) -> CandleSeries:
    """Candles plus where they came from and how fresh they are."""
    validate_request(symbol, interval, limit)

    key = (symbol, interval, limit)
    cached = _cache.get(key)
    if cached and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
        return CandleSeries(cached.candles, _meta(cached, "historical", []))

    params = {
        "symbol": symbol.replace("/", ""),
        "interval": interval,
        "limit": limit,
    }
    errors: list[str] = []
    retry_after: list[float] = []

    bases, path = _endpoints(symbol)
    client = get_client()
    for base in bases:
        blocked = _blocked_until.get(base, 0) - _monotonic()
        if blocked > 0:
            errors.append(f"{_host(base)}: rate limited, retry in {blocked:.0f}s")
            retry_after.append(blocked)
            continue

        try:
            rows = await _get_json(client, f"{base.rstrip('/')}{path}", params)
            candles = parse_klines(rows)
        except RateLimited as exc:
            _blocked_until[base] = _monotonic() + exc.retry_after
            errors.append(f"{_host(base)}: {exc}")
            retry_after.append(exc.retry_after)
            log.warning("Klines request to %s rate limited for %.0fs", base, exc.retry_after)
            continue
        except MalformedResponse as exc:
            errors.append(f"{_host(base)}: malformed response ({exc})")
            log.warning("Klines from %s rejected: %s", base, exc)
            continue
        except (httpx.HTTPError, ValueError) as exc:  # ValueError: body was not JSON
            errors.append(f"{_host(base)}: {type(exc).__name__}: {exc}")
            log.warning("Klines request to %s failed: %s", base, exc)
            continue

        entry = _CacheEntry(_monotonic(), _wall(), candles, base)
        _cache[key] = entry
        return CandleSeries(candles, _meta(entry, "historical", []))

    message = "; ".join(errors) or "no endpoints configured"
    if allow_stale and cached and _monotonic() - cached.fetched_mono <= STALE_MAX_SECONDS:
        log.warning("Serving cached %s %s candles: %s", symbol, interval, message)
        return CandleSeries(
            cached.candles,
            _meta(cached, "cached", [f"Exchange unavailable, showing the last response. {message}"]),
        )

    # Only a rate limit on every endpoint says when to come back.
    all_limited = len(retry_after) == len(bases) and retry_after
    raise CandleSourceError(message, retry_after=min(retry_after) if all_limited else None)


async def fetch_candles(symbol: str, interval: str, limit: int) -> list[dict]:
    """Fresh candles only (signals and backtests must not run on a kept response)."""
    return (await fetch_candle_series(symbol, interval, limit)).candles
