"""Long-only backtest of the signal engine.

Rules of the simulation:
  * The rating is computed from a candle's close. The resulting trade fills at
    the NEXT candle's open, so the strategy never trades on information it
    could not have had.
  * Enter (go long) when the score reaches a Buy rating; exit (go to cash)
    when it reaches a Sell rating. In between ("Hold") the position is kept,
    which avoids churning on small score changes.
  * Every fill pays `fee` (a fraction; 0.001 = 0.1%, roughly Binance spot).
    No slippage, leverage, shorting or position sizing.
  * Buy-and-hold is measured over the same window, bought at the same first
    tradable open.

Past results do not predict future results, and a handful of trades says very
little. `sample_warning` flags runs with too few trades to mean much.
"""
import numpy as np
import pandas as pd

from src.signals.engine import DIRECTIONAL_THRESHOLD, WARMUP_CANDLES, score_frame

BARS_PER_YEAR = {"1m": 525_600, "15m": 35_040, "1h": 8_760, "1d": 365}
DEFAULT_FEE = 0.001
MIN_TRADES_FOR_SIGNIFICANCE = 10
MAX_CURVE_POINTS = 200
# Annualizing a Sharpe ratio from a few hours of returns is noise, so it is
# only reported for windows at least this long.
MIN_SHARPE_DAYS = 14


def hold_flags(scores: np.ndarray, ready: np.ndarray) -> np.ndarray:
    """Position held after each candle's close, given its score (with hysteresis)."""
    flags = np.zeros(len(scores), dtype=bool)
    held = False
    for i, score in enumerate(scores):
        if ready[i]:
            if not held and score >= DIRECTIONAL_THRESHOLD:
                held = True
            elif held and score <= -DIRECTIONAL_THRESHOLD:
                held = False
        flags[i] = held
    return flags


def _max_drawdown_pct(equity: np.ndarray) -> float:
    # Start from the 1.0 of capital held before the window, so a loss on the
    # very first candle still counts as a drawdown.
    equity = np.concatenate([[1.0], equity])
    peaks = np.maximum.accumulate(equity)
    return float((equity / peaks - 1).min() * 100)


def _number(value, digits=2):
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), digits)


def backtest_scored(
    frame: pd.DataFrame, interval: str, fee: float = DEFAULT_FEE
) -> dict:
    """Backtest a frame that already has `score` and `ready` columns."""
    n = len(frame)
    first_scored = int(np.argmax(frame["ready"].to_numpy())) if frame["ready"].any() else n
    start = first_scored + 1  # first candle a trade can fill on
    if n - start < 2:
        raise ValueError("Not enough candles to backtest.")

    opens = frame["open"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    times = frame["time"].to_numpy()

    flags = hold_flags(
        frame["score"].to_numpy(dtype=float), frame["ready"].to_numpy(dtype=bool)
    )
    # Position held *through* each candle: decided at the previous close.
    held = np.concatenate([[False], flags[:-1]])
    was_held = np.concatenate([[False], held[:-1]])

    growth = np.ones(n)
    for j in range(1, n):
        if held[j] and was_held[j]:
            growth[j] = closes[j] / closes[j - 1]
        elif held[j]:  # entering at this candle's open
            growth[j] = (1 - fee) * closes[j] / opens[j]
        elif was_held[j]:  # exiting at this candle's open
            growth[j] = (opens[j] / closes[j - 1]) * (1 - fee)

    window = slice(start, n)
    strategy_equity = np.cumprod(growth[window])
    buy_hold_equity = closes[window] / opens[start] * (1 - fee)
    bar_returns = growth[window] - 1

    # Trades are the entry/exit transitions inside the window.
    trades = []
    entry = None
    for j in range(start, n):
        if held[j] and not was_held[j]:
            entry = j
        if entry is not None and not held[j] and was_held[j]:
            trades.append(_trade(times, opens, opens, entry, j, fee, is_open=False))
            entry = None
    if entry is not None:
        trades.append(_trade(times, opens, closes, entry, n - 1, fee, is_open=True))

    returns = np.array([t["return_pct"] for t in trades])
    sharpe = None
    window_days = (times[-1] - times[start]) / 86_400
    if window_days >= MIN_SHARPE_DAYS and bar_returns.std(ddof=1) > 0:
        sharpe = (
            bar_returns.mean() / bar_returns.std(ddof=1)
            * np.sqrt(BARS_PER_YEAR[interval])
        )

    picks = np.unique(np.linspace(0, len(strategy_equity) - 1, MAX_CURVE_POINTS).astype(int))
    curve = [
        {
            "time": int(times[start + k]),
            "strategy": _number((strategy_equity[k] - 1) * 100),
            "buy_hold": _number((buy_hold_equity[k] - 1) * 100),
        }
        for k in picks
    ]

    return {
        "interval": interval,
        "fee_pct": _number(fee * 100, 3),
        "period": {
            "start": int(times[start]),
            "end": int(times[-1]),
            "candles": int(n - start),
        },
        "strategy_return_pct": _number((strategy_equity[-1] - 1) * 100),
        "buy_hold_return_pct": _number((buy_hold_equity[-1] - 1) * 100),
        "strategy_max_drawdown_pct": _number(_max_drawdown_pct(strategy_equity)),
        "buy_hold_max_drawdown_pct": _number(_max_drawdown_pct(buy_hold_equity)),
        "sharpe_ratio": _number(sharpe),
        "exposure_pct": _number(held[window].mean() * 100, 1),
        "trades": {
            "count": len(trades),
            "win_rate_pct": _number((returns > 0).mean() * 100, 1) if len(returns) else None,
            "average_return_pct": _number(returns.mean()) if len(returns) else None,
            "best_pct": _number(returns.max()) if len(returns) else None,
            "worst_pct": _number(returns.min()) if len(returns) else None,
            "list": trades[-20:],
        },
        "sample_warning": len(trades) < MIN_TRADES_FOR_SIGNIFICANCE,
        "equity_curve": curve,
    }


def _trade(times, opens, exit_prices, entry, exit_index, fee, is_open) -> dict:
    entry_price = opens[entry]
    exit_price = exit_prices[exit_index]
    # A closed trade pays the fee on both fills; an open one only on entry.
    fees = (1 - fee) if is_open else (1 - fee) ** 2
    return {
        "entry_time": int(times[entry]),
        "entry_price": _number(entry_price, 4),
        "exit_time": int(times[exit_index]),
        "exit_price": _number(exit_price, 4),
        "return_pct": _number((exit_price / entry_price * fees - 1) * 100, 3),
        "bars_held": int(exit_index - entry),
        "open": is_open,
    }


def run_backtest(
    candles: pd.DataFrame, interval: str, fee: float = DEFAULT_FEE
) -> dict:
    """Score `candles` (time, open, high, low, close, volume) and backtest."""
    if len(candles) < WARMUP_CANDLES + 3:
        raise ValueError(
            f"Need at least {WARMUP_CANDLES + 3} candles to backtest, "
            f"got {len(candles)}."
        )
    return backtest_scored(score_frame(candles), interval, fee)
