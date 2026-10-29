"""Glue between the candle source and the signal engine / backtester."""
import asyncio
import time
from typing import Optional

import pandas as pd

from backend import candles as candle_source
from src.backtesting.backtest import run_backtest
from src.signals.engine import latest_signal

INTERVAL_SECONDS = {"1m": 60, "15m": 900, "1h": 3600, "1d": 86400}

SIGNAL_CANDLES = 500
BACKTEST_CANDLES = 1000

DISCLAIMER = (
    "Educational signals from technical indicators, not investment advice. "
    "They describe recent price action and do not predict future returns."
)


def to_closed_frame(
    rows: list[dict], interval: str, now: Optional[float] = None
) -> pd.DataFrame:
    """Candles as a DataFrame, without the still-forming latest candle."""
    now = time.time() if now is None else now
    span = INTERVAL_SECONDS[interval]
    closed = [row for row in rows if row["time"] + span <= now]
    return pd.DataFrame(
        closed, columns=["time", "open", "high", "low", "close", "volume"]
    )


async def _closed_candles(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    rows = await candle_source.fetch_candles(symbol, interval, limit)
    return to_closed_frame(rows, interval)


async def signal_for(symbol: str, interval: str) -> dict:
    frame = await _closed_candles(symbol, interval, SIGNAL_CANDLES)
    signal = await asyncio.to_thread(latest_signal, frame)
    return {"symbol": symbol, "interval": interval, **signal}


async def signals_for(symbols: list[str], interval: str) -> list[dict]:
    return list(await asyncio.gather(*(signal_for(s, interval) for s in symbols)))


async def backtest_for(
    symbol: str, interval: str, fee: float, slippage: float = 0.0, position_size: float = 1.0
) -> dict:
    frame = await _closed_candles(symbol, interval, BACKTEST_CANDLES)
    result = await asyncio.to_thread(run_backtest, frame, interval, fee, slippage, position_size)
    return {"symbol": symbol, **result}
