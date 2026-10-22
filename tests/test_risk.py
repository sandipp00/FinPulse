import numpy as np
import pandas as pd
import pytest

from src.analytics.risk import (
    MIN_OBSERVATIONS,
    correlation_matrix,
    normalize_daily,
    risk_metrics,
)


def closes_from_returns(returns, start="2025-01-01", base=100.0, freq="D"):
    values = base * np.cumprod(1 + np.asarray(returns))
    index = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    return pd.Series(np.concatenate([[base], values])[1:], index=index)


def test_normalize_daily_handles_timezones_duplicates_and_order():
    index = pd.to_datetime(
        ["2025-01-03T00:00:00Z", "2025-01-01T00:00:00Z", "2025-01-03T00:00:00Z"], utc=True
    )

    result = normalize_daily(pd.Series([3.0, 1.0, 9.0], index=index))

    assert result.index.tolist() == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-03")]
    assert result.tolist() == [1.0, 9.0]            # the later duplicate wins


def test_too_little_history_returns_none():
    closes = closes_from_returns([0.01] * (MIN_OBSERVATIONS - 2))

    assert risk_metrics(closes, "crypto") is None


def test_known_series_gives_known_drawdown_and_worst_day():
    returns = [0.01] * 30 + [-0.10] + [0.01] * 5             # a run-up, a 10% crash, a partial rebound
    metrics = risk_metrics(closes_from_returns(returns), "stock")

    assert metrics["worst_day_pct"] == pytest.approx(-10.0, abs=0.01)
    assert metrics["best_day_pct"] == pytest.approx(1.0, abs=0.01)
    assert metrics["worst_day_date"] == "2025-01-31"        # the 31st daily close
    assert metrics["max_drawdown_date"] == "2025-01-31"
    assert metrics["max_drawdown_pct"] == pytest.approx(-10.0, abs=0.01)
    # Five +1% days after the crash: 0.90 * 1.01**5 of the peak, i.e. still 5.4% below it.
    assert metrics["current_drawdown_pct"] == pytest.approx((0.90 * 1.01**5 - 1) * 100, abs=0.01)


def test_a_new_high_means_no_current_drawdown():
    returns = [0.01] * 30 + [-0.10] + [0.01] * 25            # rebounds past the old peak
    metrics = risk_metrics(closes_from_returns(returns), "stock")

    assert metrics["current_drawdown_pct"] == 0.0
    assert metrics["max_drawdown_pct"] == pytest.approx(-10.0, abs=0.01)   # the history is not forgotten


def test_value_at_risk_is_the_fifth_percentile_of_daily_returns():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0005, 0.02, 400)
    metrics = risk_metrics(closes_from_returns(returns), "stock")

    expected = np.quantile(pd.Series(returns).iloc[1:], 0.05) * 100   # first value is the base
    assert metrics["var_95_pct"] == pytest.approx(expected, abs=0.35)
    assert metrics["var_95_pct"] < 0
    assert metrics["expected_shortfall_pct"] <= metrics["var_95_pct"]  # the tail average is worse


def test_crypto_annualizes_on_365_days_and_stocks_on_252():
    returns = np.random.default_rng(1).normal(0, 0.01, 200)
    closes = closes_from_returns(returns)

    crypto = risk_metrics(closes, "crypto")["annualized_volatility_pct"]
    stock = risk_metrics(closes, "stock")["annualized_volatility_pct"]

    assert crypto / stock == pytest.approx((365 / 252) ** 0.5, rel=1e-2)


def test_recent_volatility_reflects_the_last_30_days_only():
    calm = [0.001, -0.001] * 50
    wild = [0.05, -0.05] * 15                                # the most recent 30 daily returns
    metrics = risk_metrics(closes_from_returns(calm + wild), "crypto")

    assert metrics["recent_volatility_pct"] == pytest.approx(0.05 * 365**0.5 * 100, rel=0.05)   # about 95%
    assert metrics["recent_volatility_pct"] > 1.5 * metrics["annualized_volatility_pct"]


# ---- correlation ------------------------------------------------------------------

def test_identical_and_scaled_series_are_perfectly_correlated():
    a = closes_from_returns(np.random.default_rng(2).normal(0, 0.02, 120))

    symbols, matrix = correlation_matrix({"A": a, "B": a * 3})

    assert symbols == ["A", "B"]
    assert matrix[0][0] == matrix[1][1] == 1.0
    assert matrix[0][1] == matrix[1][0] == pytest.approx(1.0)


def test_mirrored_returns_are_negatively_correlated():
    returns = np.random.default_rng(3).normal(0, 0.01, 150)
    up = closes_from_returns(returns)
    down = closes_from_returns(-returns)

    _, matrix = correlation_matrix({"UP": up, "DOWN": down})

    assert matrix[0][1] < -0.99


def test_independent_series_are_roughly_uncorrelated():
    rng = np.random.default_rng(4)
    _, matrix = correlation_matrix({
        "X": closes_from_returns(rng.normal(0, 0.02, 400)),
        "Y": closes_from_returns(rng.normal(0, 0.02, 400)),
    })

    assert abs(matrix[0][1]) < 0.15


def test_different_trading_calendars_are_compared_on_shared_dates_only():
    rng = np.random.default_rng(5)
    daily = closes_from_returns(rng.normal(0, 0.02, 200), freq="D")          # 7 days a week
    weekdays = daily[daily.index.dayofweek < 5] * 2                          # same prices, weekdays only

    _, matrix = correlation_matrix({"CRYPTO": daily, "STOCK": weekdays})

    # Same underlying prices on the shared dates, so a calendar mismatch must not
    # be allowed to wreck the number.
    assert matrix[0][1] == pytest.approx(1.0, abs=1e-6)


def test_pairs_with_too_little_overlap_are_none_and_the_matrix_is_symmetric():
    long = closes_from_returns(np.random.default_rng(6).normal(0, 0.02, 200))
    short = closes_from_returns(np.random.default_rng(7).normal(0, 0.02, 10), start="2025-06-01")
    other = closes_from_returns(np.random.default_rng(8).normal(0, 0.02, 200))

    _, matrix = correlation_matrix({"LONG": long, "SHORT": short, "OTHER": other})

    assert matrix[0][1] is None and matrix[1][0] is None
    assert matrix[0][2] == matrix[2][0] and matrix[0][2] is not None
