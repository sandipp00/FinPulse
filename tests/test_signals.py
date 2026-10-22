import numpy as np
import pandas as pd
import pytest

from src.signals import indicators
from src.signals.engine import (
    RULE_WEIGHTS,
    WARMUP_CANDLES,
    latest_signal,
    rating_for,
    score_frame,
)


def make_candles(closes, volume=100.0, step=60):
    closes = np.asarray(closes, dtype=float)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame({
        "time": 1_700_000_000 + np.arange(len(closes)) * step,
        "open": opens,
        "high": np.maximum(opens, closes) * 1.001,
        "low": np.minimum(opens, closes) * 0.999,
        "close": closes,
        "volume": volume,
    })


def trend(length, start=100.0, per_bar=0.5):
    return start + per_bar * np.arange(length)


# ---- indicators -------------------------------------------------------

def test_sma_and_ema_match_hand_calculation():
    values = pd.Series([1.0, 2, 3, 4, 5])

    assert indicators.sma(values, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    assert indicators.sma(values, 3).iloc[:2].isna().all()
    # EMA seeded with SMA(1,2,3)=2, k=0.5 -> 3, 4
    assert indicators.ema(values, 3).tolist()[2:] == [2.0, 3.0, 4.0]


def test_rsi_matches_wilders_textbook_example():
    closes = pd.Series([
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
        46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
    ])

    assert indicators.rsi(closes, 14).iloc[14] == pytest.approx(70.46, abs=0.05)


def test_rsi_extremes():
    rising = pd.Series(np.arange(1.0, 30))

    assert indicators.rsi(rising).iloc[-1] == 100.0
    assert indicators.rsi(rising[::-1].reset_index(drop=True)).iloc[-1] == 0.0


def test_bollinger_uses_population_deviation():
    bands = indicators.bollinger(pd.Series([1.0, 2.0, 3.0]), period=3, multiplier=2)

    deviation = np.sqrt(2 / 3)
    assert bands["bb_middle"].iloc[2] == 2.0
    assert bands["bb_upper"].iloc[2] == pytest.approx(2 + 2 * deviation)
    assert bands["bb_lower"].iloc[2] == pytest.approx(2 - 2 * deviation)


def test_macd_definition_and_warmup():
    closes = pd.Series(trend(60, per_bar=1.0))
    result = indicators.macd(closes)

    assert result["macd"].iloc[24] != result["macd"].iloc[24]  # NaN before slow EMA
    assert not np.isnan(result["macd"].iloc[25])
    assert np.isnan(result["macd_signal"].iloc[32])
    assert not np.isnan(result["macd_signal"].iloc[33])
    assert result["macd_hist"].iloc[40] == pytest.approx(
        result["macd"].iloc[40] - result["macd_signal"].iloc[40]
    )
    assert result["macd"].iloc[-1] > 0  # steady uptrend


def test_indicators_are_causal():
    """A value must not change when later candles are appended."""
    candles = make_candles(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 120)))
    short = score_frame(candles.iloc[:90])
    full = score_frame(candles)

    columns = ["sma50", "rsi", "macd_hist", "bb_upper", "score"]
    pd.testing.assert_frame_equal(
        short[columns].reset_index(drop=True),
        full[columns].iloc[:90].reset_index(drop=True),
    )


# ---- engine -----------------------------------------------------------

def test_rating_thresholds():
    assert rating_for(0.5) == "Strong Buy"
    assert rating_for(0.2) == "Buy"
    assert rating_for(0.0) == "Hold"
    assert rating_for(-0.19) == "Hold"
    assert rating_for(-0.2) == "Sell"
    assert rating_for(-0.5) == "Strong Sell"


def noisy_trend(per_bar, start=100.0, accel=0.0, length=120, seed=7):
    steps = np.arange(length)
    noise = np.random.default_rng(seed).normal(0, 1.5, length)
    return start + per_bar * steps + accel * steps**2 + noise


def test_uptrend_rates_bullish_and_explains_itself():
    signal = latest_signal(make_candles(noisy_trend(0.5)))

    assert signal["rating"] in {"Buy", "Strong Buy"}
    assert signal["score"] > 20
    assert signal["confidence"] >= 50
    assert {reason["rule"] for reason in signal["reasons"]} == set(RULE_WEIGHTS)
    assert all(reason["text"] for reason in signal["reasons"])
    assert sum(signal["votes"].values()) == len(RULE_WEIGHTS)


def test_accelerating_downtrend_rates_bearish():
    signal = latest_signal(make_candles(noisy_trend(-0.5, start=300.0, accel=-0.01)))

    assert signal["rating"] in {"Sell", "Strong Sell"}
    assert signal["score"] < -20
    assert signal["confidence"] >= 50


def test_perfect_trend_is_tempered_by_overbought_rsi():
    """Documented design trade-off: RSI is a contrarian vote, so a perfectly
    smooth rally (RSI pinned at 100) is not rated Buy on trend alone."""
    scored = score_frame(make_candles(trend(120, per_bar=1.0))).iloc[-1]

    assert scored["vote_trend"] == 1 and scored["vote_ma_cross"] == 1
    assert scored["vote_rsi"] == -1
    assert scored["vote_macd"] == 0  # float noise (~-1e-15) must not count as bearish
    assert rating_for(scored["score"]) == "Hold"


def test_flat_market_is_hold_without_confidence():
    signal = latest_signal(make_candles(np.full(120, 100.0)))

    assert signal["rating"] == "Hold"
    assert signal["confidence"] is None


def test_too_few_candles_reports_insufficient_data():
    signal = latest_signal(make_candles(trend(WARMUP_CANDLES - 1)))

    assert signal["rating"] == "Insufficient data"
    assert signal["score"] is None
    assert signal["candles_required"] == WARMUP_CANDLES


def test_scores_stay_within_bounds_and_warmup_is_unscored():
    scored = score_frame(make_candles(100 + np.cumsum(np.random.default_rng(2).normal(0, 2, 300))))

    assert scored["score"].between(-1, 1).all()
    assert (scored["score"].iloc[: WARMUP_CANDLES - 1] == 0).all()
    assert not scored["ready"].iloc[: WARMUP_CANDLES - 1].any()
    assert scored["ready"].iloc[WARMUP_CANDLES - 1:].all()
