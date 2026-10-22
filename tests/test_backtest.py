import numpy as np
import pandas as pd
import pytest

from src.backtesting.backtest import (
    backtest_scored,
    hold_flags,
    run_backtest,
)
from src.signals.engine import WARMUP_CANDLES


def scored_frame(opens, closes, scores):
    """A frame that looks like score_frame() output, with chosen scores."""
    n = len(closes)
    return pd.DataFrame({
        "time": 1_700_000_000 + np.arange(n) * 3600,
        "open": opens,
        "close": closes,
        "score": scores,
        "ready": np.arange(n) >= WARMUP_CANDLES - 1,
    })


def flat_then(n_extra, value=100.0):
    return np.full(WARMUP_CANDLES - 1 + n_extra, value)


def test_hold_flags_have_hysteresis():
    scores = np.array([0.0, 0.3, 0.1, -0.1, -0.3, 0.1, 0.25])
    ready = np.ones(len(scores), dtype=bool)

    # Buy at 0.3, stay through the Hold zone, sell at -0.3, re-buy at 0.25.
    assert hold_flags(scores, ready).tolist() == [False, True, True, True, False, False, True]


def test_hold_flags_ignore_unready_rows():
    flags = hold_flags(np.array([0.9, 0.9, 0.9]), np.array([False, False, True]))

    assert flags.tolist() == [False, False, True]


def test_trade_fills_at_next_open_not_the_signal_close():
    n = WARMUP_CANDLES + 5
    first = WARMUP_CANDLES - 1  # first scored candle
    opens = np.full(n, 100.0)
    closes = np.full(n, 100.0)
    # A buy signal on `first`'s close; the next candle opens at 110, closes 121.
    opens[first + 1] = 110.0
    closes[first + 1] = 121.0
    opens[first + 2:] = 121.0
    closes[first + 2:] = 121.0
    scores = np.zeros(n)
    scores[first] = 0.6  # buy; stays long through the rest (Hold zone)

    result = backtest_scored(scored_frame(opens, closes, scores), "1h", fee=0.0)

    trade = result["trades"]["list"][0]
    assert trade["entry_price"] == 110.0  # next open, NOT the 100 close
    assert trade["open"] is True
    assert result["strategy_return_pct"] == pytest.approx((121 / 110 - 1) * 100)


def test_closed_trade_exits_at_next_open_and_pays_fees_both_ways():
    n = WARMUP_CANDLES + 8
    first = WARMUP_CANDLES - 1
    opens = np.full(n, 100.0)
    closes = np.full(n, 100.0)
    closes[first + 1:first + 4] = 110.0      # price rises while we hold
    opens[first + 2:first + 4] = 110.0
    closes[first + 4:] = 120.0
    opens[first + 4:] = 120.0                # candle after the sell signal opens at 120
    scores = np.zeros(n)
    scores[first] = 0.6                      # buy -> fills at open[first+1] = 100
    scores[first + 3] = -0.6                 # sell -> fills at open[first+4] = 120

    fee = 0.001
    result = backtest_scored(scored_frame(opens, closes, scores), "1h", fee=fee)

    trade = result["trades"]["list"][0]
    assert (trade["entry_price"], trade["exit_price"], trade["open"]) == (100.0, 120.0, False)
    assert trade["return_pct"] == pytest.approx((1.2 * (1 - fee) ** 2 - 1) * 100, abs=1e-3)
    assert result["trades"]["count"] == 1
    assert result["trades"]["win_rate_pct"] == 100.0


def test_fees_reduce_returns():
    n = WARMUP_CANDLES + 6
    first = WARMUP_CANDLES - 1
    prices = np.linspace(100, 130, n)
    scores = np.zeros(n)
    scores[first] = 0.6

    frame = scored_frame(prices, prices, scores)
    free = backtest_scored(frame, "1h", fee=0.0)["strategy_return_pct"]
    paid = backtest_scored(frame, "1h", fee=0.01)["strategy_return_pct"]

    assert paid < free


def test_no_signals_means_no_trades_and_flat_equity():
    n = WARMUP_CANDLES + 10
    prices = np.linspace(100, 150, n)

    result = backtest_scored(scored_frame(prices, prices, np.zeros(n)), "1d")

    assert result["trades"]["count"] == 0
    assert result["strategy_return_pct"] == 0.0
    assert result["exposure_pct"] == 0.0
    assert result["trades"]["win_rate_pct"] is None
    assert result["sample_warning"] is True
    assert result["buy_hold_return_pct"] > 0


def test_losing_trade_counts_as_a_loss():
    n = WARMUP_CANDLES + 6
    first = WARMUP_CANDLES - 1
    opens = np.full(n, 100.0)
    closes = np.full(n, 100.0)
    closes[first + 1:] = 90.0
    opens[first + 2:] = 90.0
    scores = np.zeros(n)
    scores[first] = 0.6
    scores[first + 2] = -0.6

    result = backtest_scored(scored_frame(opens, closes, scores), "1h", fee=0.0)

    assert result["trades"]["win_rate_pct"] == 0.0
    assert result["trades"]["worst_pct"] == pytest.approx(-10.0)
    assert result["strategy_max_drawdown_pct"] < 0


def test_equity_curve_is_bounded_and_ordered():
    rng = np.random.default_rng(3)
    prices = 100 + np.cumsum(rng.normal(0, 1, 900))
    candles = pd.DataFrame({
        "time": 1_700_000_000 + np.arange(900) * 3600,
        "open": np.concatenate([[prices[0]], prices[:-1]]),
        "high": prices * 1.002,
        "low": prices * 0.998,
        "close": prices,
        "volume": 50.0,
    })

    result = run_backtest(candles, "1h")

    curve = result["equity_curve"]
    assert 2 <= len(curve) <= 200
    assert [p["time"] for p in curve] == sorted(p["time"] for p in curve)
    assert result["period"]["candles"] == 900 - WARMUP_CANDLES
    assert "disclaimer" not in result  # added by the API layer


def test_too_few_candles_raises():
    candles = pd.DataFrame({
        "time": range(10), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
    })

    with pytest.raises(ValueError):
        run_backtest(candles, "1h")


def test_sharpe_is_only_reported_for_windows_of_two_weeks_or_more():
    def run(interval_seconds):
        n = WARMUP_CANDLES + 60
        rng = np.random.default_rng(5)
        prices = 100 + np.cumsum(rng.normal(0.1, 1, n))
        scores = np.zeros(n)
        scores[WARMUP_CANDLES - 1] = 0.6
        frame = scored_frame(prices, prices, scores)
        frame["time"] = 1_700_000_000 + np.arange(n) * interval_seconds
        return backtest_scored(frame, "1h")["sharpe_ratio"]

    assert run(60) is None                 # 60 one-minute candles ~ 1 hour
    assert run(86_400) is not None         # 60 daily candles ~ 2 months
