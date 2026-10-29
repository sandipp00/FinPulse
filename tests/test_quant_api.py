"""GET /api/quant/relative against a temporary database of known prices."""
import sqlite3

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import config, main
from src.data.schema import MARKET_PRICES_DDL


def rows(symbol, asset_type, closes, start="2025-01-01", freq="B"):
    days = pd.date_range(start, periods=len(closes), freq=freq)
    return [(f"{d:%Y-%m-%d}T00:00:00Z", symbol, asset_type, c, c * 1.01, c * 0.99, c, 100) for d, c in zip(days, closes)]


rng = np.random.default_rng(11)
BENCH = 4000 * np.cumprod(1 + rng.normal(0.0004, 0.01, 260))
DOUBLE = 100 * np.cumprod(1 + 2 * np.r_[0, BENCH[1:] / BENCH[:-1] - 1])  # exactly twice the index's daily moves


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    with sqlite3.connect(path) as conn:
        conn.execute(MARKET_PRICES_DDL)
        conn.executemany("INSERT INTO market_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         rows("^GSPC", "index", BENCH) + rows("AAPL", "stock", DOUBLE)
                         + rows("^NSEI", "index", BENCH[:20], start="2020-01-01"))
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_SYMBOLS", [])
    with TestClient(main.app) as test_client:
        yield test_client


def test_relative_metrics_for_a_doubled_benchmark(client):
    body = client.get("/api/quant/relative", params={"symbol": "AAPL", "benchmark": "^GSPC", "window": 60}).json()

    m = body["metrics"]
    assert m["beta"] == pytest.approx(2.0, abs=1e-3)
    assert m["correlation"] == pytest.approx(1.0, abs=1e-3)
    assert body["overlap"] == 260
    assert body["periods_per_year"] == 252
    assert body["start_date"] == "2025-01-01"
    assert m["tracking_error_pct"] > 0 and m["information_ratio"] is not None
    assert body["assets"]["AAPL"]["max_drawdown_pct"] < body["assets"]["^GSPC"]["max_drawdown_pct"]  # deeper falls
    assert body["sources"]["AAPL"]["source"] == "database"
    assert body["methodology"]["caveat"].startswith("These describe how the two series moved together")


def test_rolling_series_start_once_the_window_is_full(client):
    body = client.get("/api/quant/relative", params={"symbol": "AAPL", "benchmark": "^GSPC", "window": 60}).json()
    rolling = body["rolling"]
    assert len(rolling) == 259 - 60 + 1  # 259 returns, first full window at the 60th
    assert all(r["correlation"] == pytest.approx(1.0, abs=1e-6) for r in rolling)
    assert rolling[0]["asset_volatility_pct"] == pytest.approx(2 * rolling[0]["benchmark_volatility_pct"], abs=0.02)  # both rounded to 0.01


def test_no_shared_dates_means_no_measures(client):
    body = client.get("/api/quant/relative", params={"symbol": "^NSEI", "benchmark": "^GSPC"}).json()
    assert body["overlap"] == 0
    assert body["metrics"]["beta"] is None and body["rolling"] == []
    assert body["note"].startswith("Only 0 shared dates")
    assert body["assets"]["^NSEI"] is None


@pytest.mark.parametrize("params, status", [
    ({"symbol": "AAPL", "benchmark": "AAPL"}, 400),
    ({"symbol": "TSLA", "benchmark": "^GSPC"}, 404),
    ({"symbol": "AAPL", "benchmark": "^GSPC", "window": 5}, 422),
    ({"symbol": "AAPL"}, 422),
])
def test_validation(client, params, status):
    assert client.get("/api/quant/relative", params=params).status_code == status
