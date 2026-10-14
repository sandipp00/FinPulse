import pandas as pd
import pytest

from src.analytics.financial_metrics import (
    calculate_daily_returns,
    calculate_summary,
)


def sample_data():
    return pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2025-01-01", "2025-01-02", "2025-01-03"
        ], utc=True),
        "symbol": ["TEST", "TEST", "TEST"],
        "asset_type": ["stock", "stock", "stock"],
        "close": [100.0, 110.0, 90.0],
    })


def test_daily_returns():
    result = calculate_daily_returns(sample_data())

    assert pd.isna(result["daily_return"].iloc[0])
    assert result["daily_return"].iloc[1] == pytest.approx(0.10)
    assert result["daily_return"].iloc[2] == pytest.approx(-20 / 110)


def test_growth_of_one():
    result = calculate_daily_returns(sample_data())

    assert result["growth_of_1"].iloc[0] == pytest.approx(1.0)
    assert result["growth_of_1"].iloc[1] == pytest.approx(1.1)
    assert result["growth_of_1"].iloc[2] == pytest.approx(0.9)


def test_drawdown():
    result = calculate_daily_returns(sample_data())

    assert result["drawdown"].iloc[0] == pytest.approx(0.0)
    assert result["drawdown"].iloc[1] == pytest.approx(0.0)
    assert result["drawdown"].iloc[2] == pytest.approx(-0.18181818)


def test_summary_total_return():
    daily = calculate_daily_returns(sample_data())
    summary = calculate_summary(daily)

    assert len(summary) == 1
    assert summary.iloc[0]["symbol"] == "TEST"
    assert summary.iloc[0]["total_return_pct"] == pytest.approx(-10.0)
    assert summary.iloc[0]["max_drawdown_pct"] == pytest.approx(-18.18181818)
