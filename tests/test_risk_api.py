import sqlite3
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import candles as candle_source, config, main, risk_service

DAY = 86_400


def daily_candles(seed, days=120):
    """Closed daily candles ending yesterday, as Binance would return them."""
    rng = np.random.default_rng(seed)
    closes = 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, days))
    end = int(time.time() // DAY) * DAY
    return [
        {"time": end - (days - i) * DAY, "open": float(c), "high": float(c), "low": float(c),
         "close": float(c), "volume": 1.0}
        for i, c in enumerate(closes)
    ]


@pytest.fixture
def api(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_SYMBOLS", ["BTC/USDT", "SOL/USDT"])
    risk_service.clear_cache()

    calls = []

    async def fake_fetch(symbol, interval, limit):
        calls.append((symbol, interval, limit))
        return daily_candles(seed=sum(map(ord, symbol)))

    monkeypatch.setattr(candle_source, "fetch_candles", fake_fetch)

    with TestClient(main.app) as client:
        # Stored history for a stock and for BTC (which Binance data should override).
        conn = sqlite3.connect(path)
        rng = np.random.default_rng(1)
        for symbol, kind in (("AAPL", "stock"), ("BTC/USDT", "crypto")):
            price = 100.0
            for day in range(90):
                price *= 1 + rng.normal(0, 0.015)
                stamp = f"2026-0{1 + day // 31}-{1 + day % 28:02d}T00:00:00Z"
                conn.execute("INSERT OR REPLACE INTO market_prices VALUES (?,?,?,?,?,?,?,?)",
                             (stamp, symbol, kind, price, price, price, price, 1.0))
        conn.commit()
        conn.close()
        yield client, calls


def test_report_covers_live_crypto_and_stored_assets(api):
    client, _ = api

    report = client.get("/api/risk").json()

    by_symbol = {a["symbol"]: a for a in report["assets"]}
    assert set(by_symbol) == {"BTC/USDT", "SOL/USDT", "AAPL"}
    assert by_symbol["SOL/USDT"]["source"] == "binance"     # no stored history, still covered
    assert by_symbol["BTC/USDT"]["source"] == "binance"     # live data wins over the stored copy
    assert by_symbol["AAPL"]["source"] == "database"
    assert by_symbol["AAPL"]["asset_type"] == "stock"
    for asset in report["assets"]:
        assert asset["var_95_pct"] < 0 and asset["max_drawdown_pct"] <= 0
        assert asset["annualized_volatility_pct"] > 0


def test_correlation_matrix_matches_the_assets(api):
    client, _ = api

    report = client.get("/api/risk").json()

    symbols = report["correlation"]["symbols"]
    matrix = report["correlation"]["matrix"]
    assert symbols == [a["symbol"] for a in report["assets"]]
    assert len(matrix) == len(symbols) and all(len(row) == len(symbols) for row in matrix)
    assert all(matrix[i][i] == 1.0 for i in range(len(symbols)))
    assert all(matrix[i][j] == matrix[j][i] for i in range(len(symbols)) for j in range(len(symbols)))
    assert "caveat" in report["methodology"]


def test_report_is_cached_briefly(api):
    client, calls = api

    client.get("/api/risk")
    first = len(calls)
    client.get("/api/risk")

    assert first == 2 and len(calls) == first               # one fetch per live symbol, then served from cache


def test_a_failing_symbol_falls_back_to_stored_history_or_is_left_out(api, monkeypatch):
    client, _ = api

    async def broken(symbol, interval, limit):
        raise candle_source.CandleSourceError("exchange unreachable")

    monkeypatch.setattr(candle_source, "fetch_candles", broken)
    risk_service.clear_cache()

    report = client.get("/api/risk").json()

    by_symbol = {a["symbol"]: a for a in report["assets"]}
    assert by_symbol["BTC/USDT"]["source"] == "database"     # had stored history
    assert "SOL/USDT" not in by_symbol                       # had none
    assert any("SOL/USDT" in note and "left out" in note for note in report["notes"])
    assert any("BTC/USDT" in note and "stored history" in note for note in report["notes"])


def test_an_empty_database_with_no_exchange_gives_an_empty_report_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "empty.db")
    monkeypatch.setattr(main, "DATABASE_PATH", tmp_path / "empty.db")
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_SYMBOLS", ["BTC/USDT"])
    risk_service.clear_cache()

    async def broken(symbol, interval, limit):
        raise candle_source.CandleSourceError("down")

    monkeypatch.setattr(candle_source, "fetch_candles", broken)

    with TestClient(main.app) as client:
        response = client.get("/api/risk")

    assert response.status_code == 200
    assert response.json()["assets"] == [] and response.json()["count"] == 0
