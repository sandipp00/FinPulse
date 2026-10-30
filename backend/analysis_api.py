"""Per-asset analysis routes: a scoreboard of every asset and a full analysis of one.

Each asset is analysed from the longest daily history FinPulse can get for it:
stored bars (database) where they exist, otherwise Binance (crypto) or Yahoo
(indices, FX, and WTI/Brent through their futures CL=F and BZ=F). Only completed
days are used; today's bar is still forming. Results are cached for
CACHE_SECONDS, so the scoreboard does not re-fetch every asset on each visit.
"""
import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend import asset_news, candles as candle_source, instruments, yahoo_history
from src.analytics import asset_analysis, quant

log = logging.getLogger("finpulse.analysis")

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

CACHE_SECONDS = 15 * 60
YAHOO_DAILY_BARS = 2600  # about ten years
BINANCE_DAILY_BARS = 1000  # Binance's most per request
MIN_DAYS = 30
CONCURRENCY = 6
# Oil has no stored history and its Binance contracts are new: use Yahoo's futures.
YAHOO_DAILY = {"wti": "CL=F", "brent": "BZ=F"}

_monotonic = time.monotonic


@dataclass
class _Entry:
    body: dict
    fetched: float


_cache: dict[tuple[str, str], _Entry] = {}


def clear_cache() -> None:
    _cache.clear()


def daily_source(asset: asset_news.Asset) -> tuple[str, str]:
    """(provider, symbol) of the daily history used for an asset."""
    if asset.id in YAHOO_DAILY:
        return "yahoo", YAHOO_DAILY[asset.id]
    if asset.stored:
        return "database", asset.stored
    if asset.asset_class == "crypto":
        return "binance", asset.live
    return "yahoo", asset.live


def to_closes(candles: list[dict]) -> pd.Series:
    """Candles -> daily closes by local trading date, completed days only.

    Bars are stamped at local midnight (Tokyo's is 15:00 UTC the day before), so
    twelve hours are added before taking the date: right for any UTC offset up to
    twelve hours either way.
    """
    if not candles:
        return pd.Series(dtype=float)
    stamps = pd.to_datetime([c["time"] + 12 * 3600 for c in candles], unit="s", utc=True)
    days = stamps.tz_convert(None).normalize()
    closes = pd.Series([float(c["close"]) for c in candles], index=days)
    closes = closes[~closes.index.duplicated(keep="last")].sort_index()
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    return closes[closes.index < today]


async def load_closes(asset: asset_news.Asset) -> tuple[pd.Series, str, str]:
    provider, symbol = daily_source(asset)
    try:
        if provider == "database":
            candles = await asyncio.to_thread(instruments.stored_candles, symbol, instruments.MAX_STORED_LIMIT)
        elif provider == "binance":
            candles = await candle_source.fetch_candles(symbol, "1d", BINANCE_DAILY_BARS)
        else:
            candles, _ = await yahoo_history.fetch_candle_series(symbol, "1d", YAHOO_DAILY_BARS)
    except (candle_source.CandleSourceError, yahoo_history.YahooHistoryError, FileNotFoundError, sqlite3.Error) as exc:
        raise LookupError(f"{provider} history for {symbol} is unavailable: {exc}") from exc
    return to_closes(candles), provider, symbol


def _source(provider: str, symbol: str, closes: pd.Series) -> dict:
    return {
        "provider": provider, "symbol": symbol,
        "first_date": closes.index[0].date().isoformat() if len(closes) else None,
        "last_date": closes.index[-1].date().isoformat() if len(closes) else None,
        "days": len(closes),
    }


async def _cached(kind: str, asset: asset_news.Asset, build) -> dict:
    key = (kind, asset.id)
    entry = _cache.get(key)
    if entry and _monotonic() - entry.fetched < CACHE_SECONDS:
        return entry.body
    body = await build()
    _cache[key] = _Entry(body, _monotonic())
    return body


async def asset_summary(asset: asset_news.Asset) -> dict:
    async def build():
        row = {"asset": asset_news.describe(asset)}
        try:
            closes, provider, symbol = await load_closes(asset)
        except LookupError as exc:
            return {**row, "error": str(exc)}
        if len(closes) < MIN_DAYS:
            return {**row, "source": _source(provider, symbol, closes), "error": "Not enough daily history"}
        periods = quant.periods_for(asset.asset_class)
        return {**row, "source": _source(provider, symbol, closes), **asset_analysis.summary(closes, periods)}

    return await _cached("summary", asset, build)


@router.get("/scoreboard")
async def scoreboard():
    """Headline figures for every asset, from its daily history."""
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(asset):
        async with gate:
            return await asset_summary(asset)

    rows = await asyncio.gather(*(one(a) for a in asset_news.ASSETS))
    return {
        "count": len(rows),
        "rows": list(rows),
        "notes": [
            "From daily closes of completed days. Returns over a period are left blank when the history is "
            "shorter than the period.",
            "Trend: up when the price is above its 50-day average and that is above the 200-day; down when "
            "the reverse; otherwise mixed.",
        ],
    }


@router.get("/asset")
async def asset_detail(asset: str = Query(..., min_length=1, max_length=20)):
    """The full analysis of one asset."""
    found = asset_news.find(asset)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset}")

    async def build():
        try:
            closes, provider, symbol = await load_closes(found)
        except LookupError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if len(closes) < MIN_DAYS:
            raise HTTPException(status_code=422, detail=f"Only {len(closes)} days of history; at least {MIN_DAYS} are needed.")
        periods = quant.periods_for(found.asset_class)
        return {
            "asset": asset_news.describe(found),
            "source": _source(provider, symbol, closes),
            "periods_per_year": periods,
            **asset_analysis.analyse(closes, periods),
            "notes": [
                "From daily closes of completed days; today's bar is still forming.",
                "Risk-free rate taken as zero for the Sharpe and Sortino ratios. Value at risk is the 1-day "
                "loss exceeded on 5% of days in this history.",
            ],
        }

    return await _cached("detail", found, build)
