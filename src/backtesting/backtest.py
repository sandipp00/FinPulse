"""Long-only backtest of the signal engine.

Rules of the simulation:
  * The rating is computed from a candle's close. The resulting trade fills at
    the NEXT candle's open, so the strategy never trades on information it
    could not have had.
  * Enter (go long) when the score reaches a Buy rating; exit (go to cash)
    when it reaches a Sell rating. In between ("Hold") the position is kept,
    which avoids churning on small score changes.
  * Every fill pays `fee` (a fraction; 0.001 = 0.1%, roughly Binance spot) and
    `slippage` (a fraction of the price, always against the trader: buys fill
    higher, sells lower). Defaults: 0.1% fee, no slippage.
  * `position_size` is the share of equity invested on each entry (1.0 = all
    of it); the rest stays in cash, earning nothing. No leverage or shorting.
  * Buy-and-hold is measured over the same window, bought at the same first
    tradable open, with the same fee, slippage and position size.
  * A second baseline, the 50/200 moving-average trend rule (long while the
    50-candle average is above the 200-candle one), runs through the same
    simulation so the signal rules are compared with something simple.
  * Results are also split into the first 70% of the window and the most
    recent 30%. The signal rules have no fitted parameters, so this is not a
    validation of a fit: it shows whether the result held up in the latest
    stretch or came from one earlier period.

Past results do not predict future results, and a handful of trades says very
little. `sample_warning` flags runs with too few trades to mean much.
"""
import numpy as np
import pandas as pd

from src.signals.engine import DIRECTIONAL_THRESHOLD, WARMUP_CANDLES, score_frame
from src.signals.indicators import sma

BARS_PER_YEAR = {"1m": 525_600, "15m": 35_040, "1h": 8_760, "1d": 365}
DEFAULT_FEE = 0.001
DEFAULT_SLIPPAGE = 0.0
DEFAULT_POSITION_SIZE = 1.0
MIN_TRADES_FOR_SIGNIFICANCE = 10
MAX_CURVE_POINTS = 200
# Annualizing a Sharpe ratio from a few hours of returns is noise, so it is
# only reported for windows at least this long.
MIN_SHARPE_DAYS = 14
IN_SAMPLE_SHARE = 0.7
TREND_FAST, TREND_SLOW = 50, 200


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


def trend_flags(closes: np.ndarray) -> np.ndarray:
    """Long after a candle's close while the 50-candle average is above the 200-candle one."""
    series = pd.Series(closes)
    fast, slow = sma(series, TREND_FAST).to_numpy(), sma(series, TREND_SLOW).to_numpy()
    return np.where(np.isnan(slow), False, fast > slow)


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


def simulate(opens, closes, flags, start, fee, slippage, size):
    """Equity (start of capital = 1.0) at each close from `start`, and the trades.

    `flags[i]` is the position wanted after candle i's close; it is acted on at
    candle i+1's open. Cash and units are tracked explicitly.
    """
    n = len(closes)
    held = np.concatenate([[False], flags[:-1]])
    was_held = np.concatenate([[False], held[:-1]])
    cash, units = 1.0, 0.0
    equity = np.empty(n - start)
    trades, entry = [], None

    for k, j in enumerate(range(start, n)):
        if held[j] and not was_held[j]:  # buy at this candle's open
            price = opens[j] * (1 + slippage)
            invested = cash * size
            units = invested * (1 - fee) / price
            cash -= invested
            entry = (j, price)
        elif was_held[j] and not held[j]:  # sell at this candle's open
            price = opens[j] * (1 - slippage)
            cash += units * price * (1 - fee)
            units = 0.0
            trades.append(_trade_record(entry, j, price, fee, is_open=False))
            entry = None
        equity[k] = cash + units * closes[j]

    if entry is not None:  # still open: valued at the last close, no exit costs
        trades.append(_trade_record(entry, n - 1, closes[-1], fee, is_open=True))
    exposure = held[start:n].mean() * 100
    return equity, trades, exposure


def _trade_record(entry, exit_index, exit_price, fee, is_open):
    entry_index, entry_price = entry
    # A closed trade pays the fee on both fills; an open one only on entry. The
    # return is on the money invested in the trade, whatever the position size.
    # It is rounded to the 3 decimals shown, and the trade summaries (best, worst,
    # average) are taken from those shown values so they always agree with the list.
    fees = (1 - fee) if is_open else (1 - fee) ** 2
    return {
        "entry_index": entry_index, "exit_index": exit_index,
        "entry_price": entry_price, "exit_price": exit_price,
        "return_pct": _number((exit_price / entry_price * fees - 1) * 100, 3),
        "open": is_open,
    }


def _public_trade(trade, times):
    return {
        "entry_time": int(times[trade["entry_index"]]),
        "entry_price": _number(trade["entry_price"], 4),
        "exit_time": int(times[trade["exit_index"]]),
        "exit_price": _number(trade["exit_price"], 4),
        "return_pct": trade["return_pct"],
        "bars_held": int(trade["exit_index"] - trade["entry_index"]),
        "open": trade["open"],
    }


def _segment(equity, buy_hold, trend, trades, lo, hi, start, times):
    """Return, buy-and-hold, trend and drawdown over equity[lo:hi], rebased to its start."""
    base = lambda curve: 1.0 if lo == 0 else curve[lo - 1]  # noqa: E731
    seg = lambda curve: curve[lo:hi] / base(curve)  # noqa: E731
    in_segment = [t for t in trades if lo <= t["entry_index"] - start < hi]
    returns = np.array([t["return_pct"] for t in in_segment])
    return {
        "start": int(times[start + lo]),
        "end": int(times[start + hi - 1]),
        "candles": int(hi - lo),
        "strategy_return_pct": _number((seg(equity)[-1] - 1) * 100),
        "buy_hold_return_pct": _number((seg(buy_hold)[-1] - 1) * 100),
        "trend_return_pct": _number((seg(trend)[-1] - 1) * 100),
        "strategy_max_drawdown_pct": _number(_max_drawdown_pct(seg(equity))),
        "trades": len(in_segment),
        "win_rate_pct": _number((returns > 0).mean() * 100, 1) if len(returns) else None,
    }


def backtest_scored(
    frame: pd.DataFrame,
    interval: str,
    fee: float = DEFAULT_FEE,
    slippage: float = DEFAULT_SLIPPAGE,
    position_size: float = DEFAULT_POSITION_SIZE,
) -> dict:
    """Backtest a frame that already has `score` and `ready` columns."""
    if not 0 < position_size <= 1:
        raise ValueError("position_size must be more than 0 and at most 1.")
    if not 0 <= slippage < 0.1:
        raise ValueError("slippage must be at least 0 and below 10%.")

    n = len(frame)
    first_scored = int(np.argmax(frame["ready"].to_numpy())) if frame["ready"].any() else n
    start = first_scored + 1  # first candle a trade can fill on
    if n - start < 2:
        raise ValueError("Not enough candles to backtest.")

    opens = frame["open"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    times = frame["time"].to_numpy()

    flags = hold_flags(frame["score"].to_numpy(dtype=float), frame["ready"].to_numpy(dtype=bool))
    strategy_equity, trades, exposure = simulate(opens, closes, flags, start, fee, slippage, position_size)
    trend_equity, trend_trades, trend_exposure = simulate(
        opens, closes, trend_flags(closes), start, fee, slippage, position_size
    )

    entry_fill = opens[start] * (1 + slippage)
    buy_hold_equity = (1 - position_size) + position_size * (1 - fee) * closes[start:] / entry_fill
    bar_returns = np.diff(np.concatenate([[1.0], strategy_equity]))
    bar_returns = bar_returns / np.concatenate([[1.0], strategy_equity[:-1]])

    returns = np.array([t["return_pct"] for t in trades])
    sharpe = None
    window_days = (times[-1] - times[start]) / 86_400
    if window_days >= MIN_SHARPE_DAYS and bar_returns.std(ddof=1) > 0:
        sharpe = bar_returns.mean() / bar_returns.std(ddof=1) * np.sqrt(BARS_PER_YEAR[interval])

    picks = np.unique(np.linspace(0, len(strategy_equity) - 1, MAX_CURVE_POINTS).astype(int))
    curve = [
        {
            "time": int(times[start + k]),
            "strategy": _number((strategy_equity[k] - 1) * 100),
            "buy_hold": _number((buy_hold_equity[k] - 1) * 100),
            "trend": _number((trend_equity[k] - 1) * 100),
        }
        for k in picks
    ]

    length = n - start
    cut = int(round(length * IN_SAMPLE_SHARE))
    split = None
    if 2 <= cut <= length - 2:
        split = {
            "in_sample": _segment(strategy_equity, buy_hold_equity, trend_equity, trades, 0, cut, start, times),
            "out_of_sample": _segment(strategy_equity, buy_hold_equity, trend_equity, trades, cut, length, start, times),
            "note": "The signal rules have no fitted parameters, so this split does not validate a fit; it shows "
                    "whether the result held up in the most recent 30% of the window.",
        }

    trend_returns = np.array([t["return_pct"] for t in trend_trades])
    return {
        "interval": interval,
        "fee_pct": _number(fee * 100, 3),
        "slippage_pct": _number(slippage * 100, 3),
        "position_size_pct": _number(position_size * 100, 1),
        "period": {"start": int(times[start]), "end": int(times[-1]), "candles": int(length)},
        "strategy_return_pct": _number((strategy_equity[-1] - 1) * 100),
        "buy_hold_return_pct": _number((buy_hold_equity[-1] - 1) * 100),
        "strategy_max_drawdown_pct": _number(_max_drawdown_pct(strategy_equity)),
        "buy_hold_max_drawdown_pct": _number(_max_drawdown_pct(buy_hold_equity)),
        "sharpe_ratio": _number(sharpe),
        "exposure_pct": _number(exposure, 1),
        "trades": {
            "count": len(trades),
            "win_rate_pct": _number((returns > 0).mean() * 100, 1) if len(returns) else None,
            "average_return_pct": _number(returns.mean()) if len(returns) else None,
            "best_pct": _number(returns.max()) if len(returns) else None,
            "worst_pct": _number(returns.min()) if len(returns) else None,
            "list": [_public_trade(t, times) for t in trades[-20:]],
        },
        "baselines": {
            "trend": {
                "name": f"{TREND_FAST}/{TREND_SLOW} moving-average trend",
                "return_pct": _number((trend_equity[-1] - 1) * 100),
                "max_drawdown_pct": _number(_max_drawdown_pct(trend_equity)),
                "exposure_pct": _number(trend_exposure, 1),
                "trades": len(trend_trades),
                "win_rate_pct": _number((trend_returns > 0).mean() * 100, 1) if len(trend_returns) else None,
                "note": f"Needs {TREND_SLOW} candles before its first signal and is in cash until then.",
            },
        },
        "split": split,
        "sample_warning": len(trades) < MIN_TRADES_FOR_SIGNIFICANCE,
        "equity_curve": curve,
    }


def run_backtest(
    candles: pd.DataFrame,
    interval: str,
    fee: float = DEFAULT_FEE,
    slippage: float = DEFAULT_SLIPPAGE,
    position_size: float = DEFAULT_POSITION_SIZE,
) -> dict:
    """Score `candles` (time, open, high, low, close, volume) and backtest."""
    if len(candles) < WARMUP_CANDLES + 3:
        raise ValueError(
            f"Need at least {WARMUP_CANDLES + 3} candles to backtest, "
            f"got {len(candles)}."
        )
    return backtest_scored(score_frame(candles), interval, fee, slippage, position_size)
