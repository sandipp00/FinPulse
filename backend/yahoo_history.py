"""Intraday and daily candles for the Yahoo-quoted FX pairs (/v8/finance/chart).

The newest bar is the one in progress: it keeps changing until its interval
ends, which is what a live chart shows. Responses are cached for CACHE_SECONDS
per (symbol, interval) and, if Yahoo fails, the last good response is served
for up to STALE_MAX_SECONDS, labelled `cached`. Yahoo reports no FX volume, so
volume is 0. Yahoo Finance data is for personal use.
"""
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

from backend import config
from backend.quotes_live import HEADERS, yahoo_symbol
from backend.schemas.market import SourceMeta

log = logging.getLogger("finpulse.yahoo_history")

PROVIDER = "yahoo"
# Interval -> the range Yahoo is asked for (Yahoo keeps 1m bars for about a week).
RANGES = {"1m": "5d", "15m": "60d", "1h": "2y", "1d": "10y"}
INTERVALS = tuple(RANGES)
YAHOO_INTERVAL = {"1h": "60m"}
CACHE_SECONDS = 20
STALE_MAX_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 15

_monotonic = time.monotonic
_wall = time.time


class YahooHistoryError(Exception):
    pass


@dataclass
class _Entry:
    candles: list[dict]
    fetched_mono: float
    fetched_wall: float
    timezone: Optional[str] = None


_cache: dict[tuple[str, str], _Entry] = {}
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    _cache.clear()


def parse_chart(body) -> list[dict]:
    """A chart response -> candles oldest first; bars with a missing price are skipped."""
    try:
        result = body["chart"]["result"][0]
        times = result.get("timestamp") or []
        quote_ = result["indicators"]["quote"][0]
        columns = [quote_.get(k) or [] for k in ("open", "high", "low", "close", "volume")]
    except (KeyError, IndexError, TypeError):
        raise YahooHistoryError("Yahoo sent chart data in an unexpected shape") from None

    candles = []
    for when, open_, high, low, close, volume in zip(times, *columns):
        prices = (open_, high, low, close)
        if not isinstance(when, int) or not all(isinstance(p, (int, float)) and math.isfinite(p) and p > 0 for p in prices):
            continue
        candles.append({
            "time": when, "open": float(open_), "high": max(prices), "low": min(prices),
            "close": float(close), "volume": float(volume) if isinstance(volume, (int, float)) else 0.0,
        })
    return candles


def exchange_timezone(body) -> Optional[str]:
    """The exchange's IANA time zone from a chart response, or None.

    Yahoo stamps a daily bar at its session's open in exchange time (09:30 in New
    York is 13:30 UTC, 09:00 in Tokyo is 00:00 UTC), so the trading date is the
    stamp's date in this zone, not in UTC.
    """
    try:
        name = body["chart"]["result"][0]["meta"]["exchangeTimezoneName"]
    except (KeyError, IndexError, TypeError):
        return None
    return name if isinstance(name, str) and name else None


def _meta(entry: _Entry, status: str, notes: list[str]) -> SourceMeta:
    last = entry.candles[-1]["time"] if entry.candles else None
    return SourceMeta(
        provider=PROVIDER,
        endpoint=urlparse(config.YAHOO_QUOTE_URL).netloc or None,
        status=status,
        retrieved_at=datetime.fromtimestamp(entry.fetched_wall, tz=timezone.utc),
        source_timestamp=datetime.fromtimestamp(last, tz=timezone.utc) if last else None,
        cache_age_seconds=round(_monotonic() - entry.fetched_mono, 1),
        exchange_timezone=entry.timezone,
        notes=notes,
    )


async def fetch_candle_series(symbol: str, interval: str, limit: int) -> tuple[list[dict], SourceMeta]:
    """The latest `limit` candles and their source metadata."""
    if interval not in RANGES:
        raise ValueError(f"Unsupported interval: {interval!r}")
    key = (symbol, interval)
    cached = _cache.get(key)
    if cached and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
        return cached.candles[-limit:], _meta(cached, "historical", [])

    url = f"{config.YAHOO_QUOTE_URL}/v8/finance/chart/{quote(yahoo_symbol(symbol), safe='')}"
    try:
        response = await get_client().get(url, params={
            "interval": YAHOO_INTERVAL.get(interval, interval), "range": RANGES[interval],
        })
        if response.status_code != 200:
            raise YahooHistoryError(f"Yahoo answered {response.status_code}")
        body = response.json()
        candles = parse_chart(body)
        if not candles:
            raise YahooHistoryError("Yahoo returned no prices")
    except (httpx.HTTPError, ValueError, YahooHistoryError) as exc:
        message = str(exc) if isinstance(exc, YahooHistoryError) else f"Could not reach Yahoo ({type(exc).__name__})"
        if cached and _monotonic() - cached.fetched_mono <= STALE_MAX_SECONDS:
            log.warning("Serving cached Yahoo %s %s candles: %s", symbol, interval, message)
            return cached.candles[-limit:], _meta(cached, "cached", [f"Yahoo unavailable, showing the last response. {message}"])
        raise YahooHistoryError(message) from None

    entry = _Entry(candles, _monotonic(), _wall(), exchange_timezone(body))
    _cache[key] = entry
    return candles[-limit:], _meta(entry, "historical", [])
