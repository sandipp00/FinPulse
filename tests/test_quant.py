"""src.analytics.quant against hand-computed values and edge cases."""
import math

import numpy as np
import pandas as pd
import pytest

from src.analytics import quant


def series(values, start="2024-01-01", freq="D"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq, tz="UTC"), dtype=float)


# ---- returns -------------------------------------------------------------------

def test_simple_and_log_returns_by_hand():
    closes = series([100, 110, 99])
    assert quant.simple_returns(closes).round(6).tolist() == [0.1, -0.1]
    assert quant.log_returns(closes).tolist() == pytest.approx([math.log(1.1), math.log(0.9)])
    # Log returns add up: their sum is the log of the total growth.
    assert quant.log_returns(closes).sum() == pytest.approx(math.log(99 / 100))


def test_total_return():
    assert quant.total_return(series([100, 120, 150])) == pytest.approx(0.5)
    assert quant.total_return(series([100])) is None
    assert quant.total_return(series([0, 1])) is None


def test_annualized_return_uses_calendar_time():
    # Doubling over exactly 365.25 days is 100% a year; over two such years, sqrt(2)-1.
    one_year = pd.Series([100.0, 200.0], index=pd.to_datetime(["2024-01-01", "2025-01-01"], utc=True))
    days = (one_year.index[1] - one_year.index[0]).days  # 366 (2024 is a leap year)
    assert quant.annualized_return(one_year) == pytest.approx(2 ** (365.25 / days) - 1)

    two_years = pd.Series([100.0, 200.0], index=pd.to_datetime(["2023-01-01", "2025-01-01"], utc=True))
    assert quant.annualized_return(two_years) == pytest.approx(2 ** (365.25 / 731) - 1)


def test_annualized_return_refuses_short_or_invalid_spans():
    assert quant.annualized_return(series([100, 101])) is None  # 1 day: not annualized
    assert quant.annualized_return(series([100] * 29 + [110])) is None  # 29 days
    assert quant.annualized_return(series([100] * 30 + [110])) is not None  # 30 days
    assert quant.annualized_return(series([-1, 1] + [1] * 40)) is None


def test_annualized_volatility_by_hand():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02])
    sd = np.std([0.01, -0.01, 0.02, -0.02], ddof=1)
    assert quant.annualized_volatility(returns, 252) == pytest.approx(sd * math.sqrt(252))
    assert quant.annualized_volatility(pd.Series([0.01]), 252) is None


def test_rolling_volatility_is_undefined_until_the_window_is_full():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02, 0.0])
    rolled = quant.rolling_volatility(returns, 3, 365)
    assert rolled.iloc[:2].isna().all()
    assert rolled.iloc[2] == pytest.approx(np.std([0.01, -0.01, 0.02], ddof=1) * math.sqrt(365))


def test_periods_for_mixed_calendars():
    assert quant.periods_for("crypto") == 365
    assert quant.periods_for("crypto", "crypto") == 365
    assert quant.periods_for("crypto", "stock") == 252  # shared dates are weekdays
    assert quant.periods_for("index") == 252


# ---- drawdowns ---------------------------------------------------------------

def test_drawdown_peak_trough_and_recovery():
    closes = series([100, 120, 90, 60, 100, 125, 110])
    stats = quant.drawdown_stats(closes)

    assert stats.max_drawdown == pytest.approx(60 / 120 - 1)  # -50%
    assert stats.peak_date == closes.index[1]
    assert stats.trough_date == closes.index[3]
    assert stats.recovery_date == closes.index[5]  # first close >= 120 after the trough
    assert stats.duration_days == 4
    assert stats.recovered is True


def test_an_unrecovered_drawdown_runs_to_the_last_date():
    closes = series([100, 80, 90, 85])
    stats = quant.drawdown_stats(closes)
    assert stats.max_drawdown == pytest.approx(-0.2)
    assert stats.recovered is False and stats.recovery_date is None
    assert stats.duration_days == 3


def test_a_series_that_only_rises_has_no_drawdown():
    stats = quant.drawdown_stats(series([1, 2, 3]))
    assert stats.max_drawdown == 0.0 and stats.recovered is True and stats.duration_days == 0
    assert quant.drawdown_stats(series([1])).max_drawdown is None


# ---- comparing two assets ----------------------------------------------------

def test_align_keeps_only_shared_dates():
    crypto = series(range(1, 15))  # 14 consecutive days
    stock = series(range(1, 11), freq="B")  # 10 weekdays from the same start
    joined = quant.align({"c": crypto, "s": stock})
    assert all(day.weekday() < 5 for day in joined.index)
    assert list(joined.columns) == ["c", "s"]
    assert len(joined) == len(set(crypto.index.normalize().tz_convert(None)) & set(stock.index.normalize().tz_convert(None)))


def _random_walk(n, seed, scale=0.01):
    rng = np.random.default_rng(seed)
    return 100 * np.cumprod(1 + rng.normal(0.0005, scale, n))


def test_an_asset_compared_with_itself():
    closes = series(_random_walk(200, 1))
    stats = quant.relative_stats(closes, closes, 252)

    assert stats.correlation == pytest.approx(1.0)
    assert stats.beta == pytest.approx(1.0)
    assert stats.excess_return == pytest.approx(0.0)
    assert stats.tracking_error is None and stats.information_ratio is None  # no active risk at all


def test_twice_the_moves_gives_beta_two_and_the_known_tracking_error():
    bench = series(_random_walk(300, 2))
    rb = bench.pct_change()
    asset = 100 * (1 + 2 * rb.fillna(0)).cumprod()  # exactly twice the benchmark's daily return

    stats = quant.relative_stats(asset, bench, 252)

    rb = rb.dropna()
    assert stats.beta == pytest.approx(2.0)
    assert stats.correlation == pytest.approx(1.0)
    # Active return equals the benchmark return, so tracking error = sd(r_b) * sqrt(252).
    assert stats.tracking_error == pytest.approx(rb.std(ddof=1) * math.sqrt(252))
    assert stats.information_ratio == pytest.approx(rb.mean() * 252 / (rb.std(ddof=1) * math.sqrt(252)))
    assert stats.r_squared == pytest.approx(1.0)


def test_beta_and_correlation_match_numpy_on_random_data():
    a, b = series(_random_walk(250, 3)), series(_random_walk(250, 4))
    stats = quant.relative_stats(a, b, 252)
    ra, rb = a.pct_change().dropna().to_numpy(), b.pct_change().dropna().to_numpy()
    assert stats.beta == pytest.approx(np.cov(ra, rb, ddof=1)[0, 1] / np.var(rb, ddof=1))
    assert stats.correlation == pytest.approx(np.corrcoef(ra, rb)[0, 1])
    assert abs(stats.correlation) < 0.3  # independent walks are only loosely related


def test_too_little_overlap_gives_no_measures():
    a = series(_random_walk(40, 5), start="2024-01-01")
    b = series(_random_walk(40, 6), start="2024-01-20")  # 21 shared days
    stats = quant.relative_stats(a, b, 252)
    assert stats.overlap == 21
    assert stats.beta is None and stats.correlation is None and stats.excess_return is None


def test_a_flat_benchmark_has_no_beta():
    stats = quant.relative_stats(series(_random_walk(60, 7)), series([100.0] * 60), 252)
    assert stats.beta is None and stats.correlation is None


def test_rolling_correlation_window():
    a, b = series(_random_walk(100, 8)), series(_random_walk(100, 9))
    ra, rb = a.pct_change().dropna(), b.pct_change().dropna()
    rolled = quant.rolling_correlation(ra, rb, 20)
    assert rolled.iloc[:19].isna().all()
    assert rolled.iloc[19] == pytest.approx(np.corrcoef(ra.iloc[:20], rb.iloc[:20])[0, 1])
