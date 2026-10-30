"""The risk report: per-asset risk measures and a correlation matrix.

Sources, chosen per asset:
  * live crypto symbols: about three years of daily candles from Binance, so
    every coin (including SOL, BNB and XRP) has history;
  * stored instruments (AAPL, the S&P 500, NIFTY 50, gold and silver): the
    stored history in SQLite;
  * the other world indices and the FX pairs quoted from Yahoo, and WTI/Brent
    through their futures CL=F and BZ=F: Yahoo daily bars from STORED_START, the
    same start as the stored history.
If Binance is unreachable, a symbol falls back to its stored history when it
has any; otherwise it is left out and the response says so. A Yahoo series that
cannot be loaded is left out the same way.
"""
import asyncio
import time
from typing import Optional

import pandas as pd

from backend import candles as candle_source, config, db, yahoo_history
from backend.analysis_api import YAHOO_DAILY_BARS, to_closes
from backend.instruments import yahoo_chart_symbols
from backend.market_service import live_asset_class
from backend.signal_service import to_closed_frame
from src.analytics.risk import correlation_matrix, risk_metrics

# Daily closes change once a day; a longer cache keeps ~70 fetches per refresh rare.
CACHE_SECONDS = 15 * 60
HISTORY_CANDLES = 1000
# Yahoo series start where the stored history does, so the windows are comparable.
STORED_START = pd.Timestamp("2023-01-01")
# Oil has no stored history and its Binance contracts are new: use Yahoo's futures.
YAHOO_FUTURES = {"CL=F": "commodity", "BZ=F": "commodity"}
YAHOO_CONCURRENCY = 6
# The VIX measures expected volatility in points; it is not a price anyone holds, so
# drawdowns, value at risk and diversification do not apply to it.
NOT_PRICES = {"^VIX"}

METHODOLOGY = {
    "returns": "Simple daily returns between consecutive daily closes.",
    "volatility": "Standard deviation of daily returns, annualized (365 days for crypto, 252 otherwise).",
    "var_95": "Historical value at risk: the 5th percentile of daily returns, i.e. a loss this large or worse happened on 1 day in 20.",
    "expected_shortfall": "The average return on those worst 1-in-20 days.",
    "drawdown": "The decline from the highest close so far.",
    "correlation": "Pearson correlation of daily returns, measured on the dates two assets share.",
    "sources": "Crypto: about three years of Binance daily candles. AAPL, the S&P 500, NIFTY 50, gold and silver: "
               "the stored history. Other indices, FX pairs and WTI/Brent oil futures: Yahoo daily bars from 2023. "
               "Only completed days are used. The VIX is left out: it measures volatility in points, "
               "not a price.",
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


async def _yahoo_series(symbol: str) -> pd.Series:
    """Completed daily closes from Yahoo, by local trading date, from STORED_START."""
    candles, meta = await yahoo_history.fetch_candle_series(symbol, "1d", YAHOO_DAILY_BARS)
    closes = to_closes(candles, meta.exchange_timezone)
    return closes[closes.index >= STORED_START]


def yahoo_symbols(stored: dict) -> dict[str, str]:
    """symbol -> asset_type for the Yahoo-sourced assets without stored history."""
    wanted = {s: live_asset_class(s) for s in yahoo_chart_symbols()}
    wanted.update(YAHOO_FUTURES)
    return {s: kind for s, kind in wanted.items() if s not in stored and s not in NOT_PRICES}


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

    from_yahoo = yahoo_symbols(stored)
    gate = asyncio.Semaphore(YAHOO_CONCURRENCY)

    async def limited(symbol):
        async with gate:
            return await _yahoo_series(symbol)

    results = await asyncio.gather(*(limited(s) for s in from_yahoo), return_exceptions=True)
    for (symbol, asset_type), result in zip(from_yahoo.items(), results):
        if isinstance(result, yahoo_history.YahooHistoryError):
            notes.append(f"Could not load Yahoo daily history for {symbol}. It is left out.")
            continue
        if isinstance(result, Exception):
            raise result
        series[symbol], kinds[symbol], sources[symbol] = result, asset_type, "yahoo"

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
