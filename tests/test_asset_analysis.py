"""Per-asset analysis on synthetic closes with known answers."""
import numpy as np
import pandas as pd
import pytest

from src.analytics import asset_analysis as aa


def closes(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


GROWTH = closes(100 * 1.001 ** np.arange(800))  # +0.1% every day for 800 days


def test_period_returns_need_enough_history():
    perf = aa.performance(GROWTH)
    assert perf["1W"] == pytest.approx(1.001 ** 7 - 1)
    assert perf["1Y"] == pytest.approx(1.001 ** 365 - 1)
    assert perf["3Y"] is None  # 800 days is not three years: not answered
    short = aa.performance(closes([100, 101, 102]))
    assert short["1M"] is None and short["1W"] is None


def test_year_to_date_measures_from_the_last_close_of_last_year():
    series = closes([100, 110, 121], start="2025-12-31")  # Dec 31, Jan 1, Jan 2
    assert aa.year_to_date(series) == pytest.approx(0.21)
    assert aa.year_to_date(closes([100, 110], start="2026-01-01")) is None  # no prior-year close


def test_risk_figures():
    up_down = closes([100, 110, 99, 108.9, 98.01] * 20)
    r = aa.risk(up_down, 365)
    assert r["best_day"] == pytest.approx(0.10) and r["worst_day"] == pytest.approx(-0.10)
    assert r["max_drawdown"] == pytest.approx(98.01 / 110 - 1)
    assert 0 < r["var_95"] <= r["cvar_95"]
    assert r["positive_days"] == pytest.approx(0.6, abs=0.02)  # +10%, -10%, +10%, -10%, +2%
    smooth = aa.risk(GROWTH, 365)
    assert smooth["max_drawdown"] == 0.0 and smooth["current_drawdown"] == 0.0
    assert smooth["sortino"] is None  # no down days: no downside deviation to divide by


def test_technicals_trend_and_52_week_range():
    t = aa.technicals(GROWTH)
    assert t["trend"] == "up" and t["vs_sma_200"] > t["vs_sma_50"] > 0
    assert t["from_high_52w"] == pytest.approx(0.0) and t["rsi_14"] > 90
    assert t["macd_state"] == "bullish"
    falling = aa.technicals(closes(100 * 0.999 ** np.arange(400)))
    assert falling["trend"] == "down" and falling["from_low_52w"] == pytest.approx(0.0)
    assert aa.technicals(closes([100] * 30))["trend"] is None  # too short for a 200-day average


def test_a_golden_cross_is_found():
    values = list(100 * 0.998 ** np.arange(300)) + list(100 * 0.998 ** 299 * 1.01 ** np.arange(1, 200))
    cross = aa.last_cross(closes(values))
    assert cross["type"] == "golden"


def test_monthly_returns_skip_the_first_month():
    series = closes([100] * 31 + [110] * 28 + [99] * 31, start="2025-01-01")  # Jan, Feb (28 days), Mar
    rows = aa.monthly_returns(series)
    assert [(r["month"], round(r["return"], 4)) for r in rows] == [(2, 0.1), (3, -0.1)]


def test_distribution_needs_thirty_returns():
    assert aa.distribution(closes([1, 2, 3]))["bins"] == []
    d = aa.distribution(GROWTH)
    assert sum(b["count"] for b in d["bins"]) == d["count"] == 799


def test_analyse_and_summary_shapes():
    full = aa.analyse(GROWTH, 365)
    assert full["observations"] == 800 and full["last_date"] == "2026-03-10"
    assert len(full["series"]["drawdown"]) == 800
    assert len(full["series"]["rolling_volatility"]) == 799 - aa.ROLLING_WINDOW + 1
    row = aa.summary(GROWTH, 365)
    assert row["trend"] == "up" and row["return_1y"] == pytest.approx(1.001 ** 365 - 1)
