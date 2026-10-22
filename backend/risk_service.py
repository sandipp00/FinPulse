"""The risk report: per-asset risk measures and a correlation matrix.

Sources, chosen per asset:
  * live crypto symbols: about three years of daily candles from Binance, so
    every coin (including SOL, BNB and XRP) has history;
  * everything else (stocks, indices): the stored history in SQLite.
If Binance is unreachable, a symbol falls back to its stored history when it
has any; otherwise it is left out and the response says so.
"""
import asyncio
import time
from typing import Optional

import pandas as pd

from backend import candles as candle_source, config, db
from backend.signal_service import to_closed_frame
from src.analytics.risk import correlation_matrix, risk_metrics

CACHE_SECONDS = 60
HISTORY_CANDLES = 1000

METHODOLOGY = {
    "returns": "Simple daily returns between consecutive daily closes.",
    "volatility": "Standard deviation of daily returns, annualized (365 days for crypto, 252 otherwise).",
    "var_95": "Historical value at risk: the 5th percentile of daily returns, i.e. a loss this large or worse happened on 1 day in 20.",
    "expected_shortfall": "The average return on those worst 1-in-20 days.",
    "drawdown": "The decline from the highest close so far.",
    "correlation": "Pearson correlation of daily returns, measured on the dates two assets share.",
    "caveat": "These describe past behaviour in the data shown. They do not predict future losses.",
}

_cache: Optional[tuple[float, dict]] = None


def clear_cache() -> None:
    global _cache
    _cache = None


def _load_stored() -> dict[str, tuple[pd.Series, str]]:
    conn = db.connect()
    try:
        frame = pd.read_sql_query(
            "SELECT timestamp, symbol, asset_type, close FROM market_prices ORDER BY symbol, timestamp",
            conn,
        )
    finally:
        conn.close()

    stored = {}
    for (symbol, asset_type), group in frame.groupby(["symbol", "asset_type"]):
        index = pd.to_datetime(group["timestamp"], utc=True)
        stored[symbol] = (pd.Series(group["close"].to_numpy(dtype=float), index=index), asset_type)
    return stored


async def _live_series(symbol: str) -> pd.Series:
    rows = await candle_source.fetch_candles(symbol, "1d", HISTORY_CANDLES)
    frame = to_closed_frame(rows, "1d")  # drop today's still-forming candle
    index = pd.to_datetime(frame["time"], unit="s", utc=True)
    return pd.Series(frame["close"].to_numpy(dtype=float), index=index)


def _compute(series: dict[str, pd.Series], kinds: dict[str, str], sources: dict[str, str]) -> tuple[list, dict]:
    assets = []
    for symbol, closes in series.items():
        metrics = risk_metrics(closes, kinds[symbol])
        if metrics:
            assets.append({"symbol": symbol, "asset_type": kinds[symbol], "source": sources[symbol], **metrics})

    symbols, matrix = correlation_matrix({asset["symbol"]: series[asset["symbol"]] for asset in assets})
    return assets, {"symbols": symbols, "matrix": matrix}


async def build_report() -> dict:
    global _cache
    if _cache and time.monotonic() - _cache[0] < CACHE_SECONDS:
        return _cache[1]

    stored = await asyncio.to_thread(_load_stored)
    series: dict[str, pd.Series] = {}
    kinds: dict[str, str] = {}
    sources: dict[str, str] = {}
    notes: list[str] = []

    live = config.LIVE_SYMBOLS
    results = await asyncio.gather(*(_live_series(s) for s in live), return_exceptions=True)
    for symbol, result in zip(live, results):
        if isinstance(result, candle_source.CandleSourceError):
            fallback = " Using stored history instead." if symbol in stored else " It is left out."
            notes.append(f"Could not load live daily candles for {symbol}.{fallback}")
            continue
        if isinstance(result, Exception):
            raise result
        series[symbol], kinds[symbol], sources[symbol] = result, "crypto", "binance"

    for symbol, (closes, asset_type) in stored.items():
        if symbol not in series:
            series[symbol], kinds[symbol], sources[symbol] = closes, asset_type, "database"

    assets, correlation = await asyncio.to_thread(_compute, series, kinds, sources)
    short = sorted(set(series) - {asset["symbol"] for asset in assets})
    if short:
        notes.append(f"Not enough history to measure risk for: {', '.join(short)}.")

    report = {
        "as_of": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "count": len(assets),
        "assets": assets,
        "correlation": correlation,
        "notes": notes,
        "methodology": METHODOLOGY,
    }
    _cache = (time.monotonic(), report)
    return report
