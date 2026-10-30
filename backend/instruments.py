"""Instrument catalogue and one history endpoint for every supported instrument.

Three sources, chosen per instrument:
  * live symbols: candles from Binance (any interval in candles.INTERVALS), spot
    for crypto and futures for live gold, silver and oil;
  * FX pairs and world indices quoted from Yahoo: candles from Yahoo's chart API,
    except that an index with stored daily history keeps using it for `1d`;
  * stored instruments (stocks, indices, gold and silver futures, some crypto):
    daily bars from SQLite.

`source=auto` uses Binance for live symbols and the database otherwise. If
Binance fails for a daily request and the instrument has stored daily bars,
those are served instead, and the metadata says so. Nothing is filled in.
"""
import asyncio
import sqlite3
import time
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend import candles as candle_source, config, yahoo_history
from backend.errors import exchange_error
from backend.market_service import UNITS, asset_class_of, currency_of, live_asset_class, unit_for
from backend.schemas.market import AssetClass, Candle, SourceMeta

router = APIRouter(prefix="/api/instruments", tags=["instruments"])

STORED_INTERVAL = "1d"
MAX_STORED_LIMIT = 5000


class StoredCoverage(BaseModel):
    interval: str
    bars: int
    first: Optional[datetime]
    last: Optional[datetime]


class Instrument(BaseModel):
    symbol: str
    asset_class: AssetClass
    currency: Optional[str]
    unit: str
    live: bool
    intervals: list[str]
    stored: Optional[StoredCoverage] = None


class InstrumentList(BaseModel):
    count: int
    instruments: list[Instrument]


class InstrumentHistory(BaseModel):
    symbol: str
    asset_class: AssetClass
    currency: Optional[str]
    unit: str
    interval: str
    source: Literal["binance", "yahoo", "database"]
    count: int
    candles: list[Candle]
    meta: SourceMeta


def _connect() -> sqlite3.Connection:
    """Read-only use of the market-data database (see main.get_connection)."""
    if not config.DATABASE_PATH.exists():
        raise FileNotFoundError(config.DATABASE_PATH)
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _parse_time(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _stored_coverage() -> dict[str, tuple[str, StoredCoverage]]:
    """symbol -> (asset_type, coverage). Empty if there is no database yet."""
    try:
        conn = _connect()
    except (FileNotFoundError, sqlite3.Error):
        return {}
    try:
        rows = conn.execute(
            """
            SELECT symbol, asset_type, COUNT(*), MIN(timestamp), MAX(timestamp)
            FROM market_prices GROUP BY symbol, asset_type ORDER BY symbol
            """
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()

    return {
        symbol: (asset_type, StoredCoverage(
            interval=STORED_INTERVAL, bars=count, first=_parse_time(first), last=_parse_time(last),
        ))
        for symbol, asset_type, count, first, last in rows
    }


def yahoo_chart_symbols() -> list[str]:
    """FX pairs and indices quoted live from Yahoo, which also serves their candles."""
    return [s for s in config.YAHOO_LIVE_SYMBOLS if live_asset_class(s) in ("fx", "index")]


def catalogue() -> dict[str, Instrument]:
    stored = _stored_coverage()
    instruments: dict[str, Instrument] = {}

    for symbol in [*config.LIVE_SYMBOLS, *config.TRADFI_LIVE_SYMBOLS]:
        asset_class = live_asset_class(symbol)
        instruments[symbol] = Instrument(
            symbol=symbol, asset_class=asset_class, currency=currency_of(symbol), unit=unit_for(symbol, asset_class),
            live=True, intervals=list(candle_source.INTERVALS),
            stored=stored[symbol][1] if symbol in stored else None,
        )

    for symbol in yahoo_chart_symbols():
        asset_class = live_asset_class(symbol)
        instruments[symbol] = Instrument(
            symbol=symbol, asset_class=asset_class, currency=currency_of(symbol), unit=UNITS[asset_class],
            live=True, intervals=list(yahoo_history.INTERVALS),
            stored=stored[symbol][1] if symbol in stored else None,
        )

    for symbol, (asset_type, coverage) in stored.items():
        if symbol in instruments:
            continue
        asset_class = asset_class_of(asset_type)
        instruments[symbol] = Instrument(
            symbol=symbol, asset_class=asset_class, currency=currency_of(symbol), unit=UNITS[asset_class],
            live=False, intervals=[STORED_INTERVAL], stored=coverage,
        )
    return instruments


def stored_candles(symbol: str, limit: int) -> list[dict]:
    """The latest `limit` daily bars for a stored symbol, oldest first."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT timestamp, open, high, low, close, volume FROM (
                SELECT timestamp, open, high, low, close, volume FROM market_prices
                WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?
            ) ORDER BY timestamp
            """,
            (symbol, limit),
        ).fetchall()
    finally:
        conn.close()

    candles = []
    for timestamp, open_, high, low, close, volume in rows:
        parsed = _parse_time(timestamp)
        if parsed is None:
            continue  # an unreadable timestamp is skipped, not guessed
        candles.append({
            "time": int(parsed.timestamp()), "open": open_, "high": high,
            "low": low, "close": close, "volume": volume,
        })
    return candles


def _stored_meta(candles: list[dict], notes: list[str]) -> SourceMeta:
    return SourceMeta(
        provider="database",
        status="historical",
        retrieved_at=datetime.now(timezone.utc),
        source_timestamp=datetime.fromtimestamp(candles[-1]["time"], tz=timezone.utc) if candles else None,
        notes=notes,
    )


@router.get("", response_model=InstrumentList)
def list_instruments():
    """Every instrument the API can chart, with its sources and intervals."""
    instruments = list(catalogue().values())
    return {"count": len(instruments), "instruments": instruments}


@router.get("/history", response_model=InstrumentHistory)
async def history(
    symbol: str = Query(..., min_length=1, max_length=32),
    interval: str = Query(default=STORED_INTERVAL),
    limit: int = Query(default=500, ge=1, le=MAX_STORED_LIMIT),
    source: Literal["auto", "binance", "yahoo", "database"] = "auto",
):
    """OHLCV history for one instrument, oldest first, with where it came from."""
    instruments = catalogue()
    instrument = instruments.get(symbol)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Unknown instrument: {symbol}")

    from_yahoo = symbol in yahoo_chart_symbols()
    if source == "auto" and from_yahoo:
        # Daily bars of an index with stored history stay on the database (the same series
        # the risk and research figures use); everything else comes from Yahoo.
        chosen = "database" if interval == STORED_INTERVAL and instrument.stored else "yahoo"
    elif source == "auto":
        chosen = "binance" if instrument.live else "database"
    else:
        chosen = source
    if (chosen == "yahoo") != from_yahoo and chosen != "database":
        raise HTTPException(status_code=400, detail=f"{symbol} is not available from {chosen}")
    if chosen == "binance" and not instrument.live:
        raise HTTPException(status_code=400, detail=f"{symbol} has no live exchange source")
    if chosen == "database" and instrument.stored is None:
        raise HTTPException(status_code=404, detail=f"{symbol} has no stored history")

    allowed = {"binance": candle_source.INTERVALS, "yahoo": yahoo_history.INTERVALS}.get(chosen, (STORED_INTERVAL,))
    if interval not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Interval {interval} is not available for {symbol} from {chosen}. "
                   f"Use one of: {', '.join(allowed)}",
        )

    notes: list[str] = []
    if chosen in ("binance", "yahoo"):
        if not candle_source.MIN_LIMIT <= limit <= candle_source.MAX_LIMIT:
            raise HTTPException(
                status_code=422,
                detail=f"limit must be between {candle_source.MIN_LIMIT} and {candle_source.MAX_LIMIT} for exchange data",
            )

    if chosen == "binance":
        try:
            series = await candle_source.fetch_candle_series(symbol, interval, limit, allow_stale=True)
        except candle_source.CandleSourceError as exc:
            if interval != STORED_INTERVAL or instrument.stored is None:
                raise exchange_error(exc) from exc
            chosen = "database"
            notes.append(f"Exchange unavailable ({exc}); showing stored daily history instead.")
        else:
            candles, meta = series.candles, series.meta

    if chosen == "yahoo":
        try:
            candles, meta = await yahoo_history.fetch_candle_series(symbol, interval, limit)
        except yahoo_history.YahooHistoryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    if chosen == "database":
        try:
            candles = stored_candles(symbol, limit)
        except (FileNotFoundError, sqlite3.Error) as exc:
            raise HTTPException(status_code=503, detail=f"Stored history unavailable: {exc}") from exc
        meta = _stored_meta(candles, notes)

    return {
        "symbol": symbol,
        "asset_class": instrument.asset_class,
        "currency": instrument.currency,
        "unit": instrument.unit,
        "interval": interval,
        "source": chosen,
        "count": len(candles),
        "candles": candles,
        "meta": meta,
    }


# ---- 7-day change -------------------------------------------------------------------

WEEK_SECONDS = 7 * 86_400
WEEK_BARS = 50  # the fewest bars an exchange request takes; plenty for a week back
WEEK_CACHE_SECONDS = 300
MAX_WEEK_SYMBOLS = 80
_week_cache: dict[str, tuple[float, dict]] = {}
_monotonic = time.monotonic


def week_change(candles: list[dict]) -> Optional[dict]:
    """Change from the close a week before the newest daily bar to the newest close.

    The base is the last bar dated at least seven days (less twelve hours, for time
    zones) before the newest one, so a weekend or holiday is skipped, not filled in.
    """
    if len(candles) < 2:
        return None
    last = candles[-1]
    target = last["time"] - WEEK_SECONDS + 12 * 3600
    earlier = [c for c in candles[:-1] if c["time"] <= target]
    if not earlier or earlier[-1]["close"] <= 0:
        return None
    base = earlier[-1]
    return {
        "change_pct": round((last["close"] / base["close"] - 1) * 100, 4),
        "close": last["close"], "base_close": base["close"],
        "time": last["time"], "base_time": base["time"],
    }


@router.get("/week-change")
async def week_changes(symbols: str = Query(..., min_length=1, max_length=2000)):
    """The 7-day change of each instrument, from its own daily bars (same source as its chart).

    For exchange sources the newest daily bar is today's, still forming, so the change
    is up to date; stored history ends at its last stored day. Cached for five minutes.
    """
    wanted = [s for s in dict.fromkeys(part.strip() for part in symbols.split(",")) if s][:MAX_WEEK_SYMBOLS]
    known = catalogue()
    now = _monotonic()

    async def one(symbol: str) -> tuple[str, Optional[dict], Optional[str]]:
        cached = _week_cache.get(symbol)
        if cached and now - cached[0] < WEEK_CACHE_SECONDS:
            return symbol, cached[1], None
        if symbol not in known:
            return symbol, None, "Unknown instrument"
        # Indices with stored history would chart 1d from the database (ending at the last
        # stored day); for a week's change Yahoo's bars, including today's, are fresher.
        source = "yahoo" if symbol in yahoo_chart_symbols() else "auto"
        try:
            body = await history(symbol=symbol, interval=STORED_INTERVAL, limit=WEEK_BARS, source=source)
        except HTTPException as exc:
            return symbol, None, str(exc.detail)
        change = week_change(body["candles"])
        if change is not None:
            change["source"] = body["source"]
            _week_cache[symbol] = (now, change)
        return symbol, change, None if change else "Not enough daily history"

    gate = asyncio.Semaphore(8)

    async def limited(symbol):
        async with gate:
            return await one(symbol)

    results = await asyncio.gather(*(limited(s) for s in wanted))
    return {
        "count": len(results),
        "changes": {symbol: change for symbol, change, _ in results if change},
        "errors": {symbol: error for symbol, _, error in results if error},
    }
