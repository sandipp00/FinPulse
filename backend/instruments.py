"""Instrument catalogue and one history endpoint for every supported instrument.

Two sources, chosen per instrument:
  * live crypto symbols: candles from Binance (any interval in candles.INTERVALS);
  * stored instruments (stocks, indices, some crypto): daily bars from SQLite.

`source=auto` uses Binance for live symbols and the database otherwise. If
Binance fails for a daily request and the instrument has stored daily bars,
those are served instead, and the metadata says so. Nothing is filled in.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend import candles as candle_source, config
from backend.errors import exchange_error
from backend.market_service import UNITS, asset_class_of, currency_of
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
    source: Literal["binance", "database"]
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


def catalogue() -> dict[str, Instrument]:
    stored = _stored_coverage()
    instruments: dict[str, Instrument] = {}

    for symbol in config.LIVE_SYMBOLS:
        instruments[symbol] = Instrument(
            symbol=symbol, asset_class="crypto", currency=currency_of(symbol), unit=UNITS["crypto"],
            live=True, intervals=list(candle_source.INTERVALS),
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
    source: Literal["auto", "binance", "database"] = "auto",
):
    """OHLCV history for one instrument, oldest first, with where it came from."""
    instruments = catalogue()
    instrument = instruments.get(symbol)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Unknown instrument: {symbol}")

    chosen = source if source != "auto" else ("binance" if instrument.live else "database")
    if chosen == "binance" and not instrument.live:
        raise HTTPException(status_code=400, detail=f"{symbol} has no live exchange source")
    if chosen == "database" and instrument.stored is None:
        raise HTTPException(status_code=404, detail=f"{symbol} has no stored history")

    if interval not in (candle_source.INTERVALS if chosen == "binance" else (STORED_INTERVAL,)):
        allowed = candle_source.INTERVALS if chosen == "binance" else (STORED_INTERVAL,)
        raise HTTPException(
            status_code=400,
            detail=f"Interval {interval} is not available for {symbol} from {chosen}. "
                   f"Use one of: {', '.join(allowed)}",
        )

    notes: list[str] = []
    if chosen == "binance":
        if not candle_source.MIN_LIMIT <= limit <= candle_source.MAX_LIMIT:
            raise HTTPException(
                status_code=422,
                detail=f"limit must be between {candle_source.MIN_LIMIT} and {candle_source.MAX_LIMIT} for exchange data",
            )
        try:
            series = await candle_source.fetch_candle_series(symbol, interval, limit, allow_stale=True)
        except candle_source.CandleSourceError as exc:
            if interval != STORED_INTERVAL or instrument.stored is None:
                raise exchange_error(exc) from exc
            chosen = "database"
            notes.append(f"Exchange unavailable ({exc}); showing stored daily history instead.")
        else:
            candles, meta = series.candles, series.meta

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
