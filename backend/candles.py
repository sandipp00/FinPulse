"""Historical OHLCV candles for the live crypto symbols, from Binance klines.

Binance's public REST API needs no key. Responses are cached for a few seconds
so many browser tabs (or rapid timeframe switches) don't hammer the exchange.
"""
import logging
import time

import httpx

from backend import config

log = logging.getLogger("finpulse.candles")

INTERVALS = ("1m", "15m", "1h", "1d")
MIN_LIMIT = 50
MAX_LIMIT = 1000
CACHE_SECONDS = 5

_cache: dict[tuple, tuple[float, list[dict]]] = {}

# One long-lived client: reusing its connections avoids a fresh TLS handshake
# on every request (about 1s each), which matters when five symbols load at once.
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class CandleSourceError(Exception):
    """Every configured Binance endpoint failed."""


def parse_klines(rows: list[list]) -> list[dict]:
    """Binance kline arrays -> candles with a unix-seconds `time`."""
    return [
        {
            "time": int(row[0]) // 1000,
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
    ]


async def _get_json(client: httpx.AsyncClient, url: str, params: dict):
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


async def fetch_candles(symbol: str, interval: str, limit: int) -> list[dict]:
    key = (symbol, interval, limit)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    params = {
        "symbol": symbol.replace("/", ""),
        "interval": interval,
        "limit": limit,
    }
    last_error = None

    client = get_client()
    for base in config.BINANCE_REST_URLS:
        try:
            rows = await _get_json(client, f"{base.rstrip('/')}/api/v3/klines", params)
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            log.warning("Klines request to %s failed: %s", base, exc)
            continue

        candles = parse_klines(rows)
        _cache[key] = (time.monotonic(), candles)
        return candles

    raise CandleSourceError(str(last_error))
