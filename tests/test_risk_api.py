import sqlite3
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import candles as candle_source, config, main, risk_service, yahoo_history

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
    # One Yahoo index, one FX pair and AAPL (stored, so it stays on the database).
    monkeypatch.setattr(config, "YAHOO_LIVE_SYMBOLS", ["AAPL", "^N225", "^VIX", "EUR/USD"])
    monkeypatch.setattr(risk_service, "YAHOO_FUTURES", {"CL=F": "commodity"})

    async def fake_yahoo(symbol, interval, limit):
        calls.append((symbol, interval, limit))
        return daily_candles(seed=sum(map(ord, symbol))), SimpleNamespace(exchange_timezone=None)

    monkeypatch.setattr(yahoo_history, "fetch_candle_series", fake_yahoo)

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
    assert set(by_symbol) == {"BTC/USDT", "SOL/USDT", "AAPL", "^N225", "EUR/USD", "CL=F"}  # no ^VIX: not a price
    assert by_symbol["SOL/USDT"]["source"] == "binance"     # no stored history, still covered
    assert by_symbol["BTC/USDT"]["source"] == "binance"     # live data wins over the stored copy
    assert by_symbol["AAPL"]["source"] == "database"
    assert by_symbol["AAPL"]["asset_type"] == "stock"
    assert {s: by_symbol[s]["source"] for s in ("^N225", "EUR/USD", "CL=F")} == dict.fromkeys(
        ("^N225", "EUR/USD", "CL=F"), "yahoo")
    assert [by_symbol[s]["asset_type"] for s in ("^N225", "EUR/USD", "CL=F")] == ["index", "fx", "commodity"]
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

    assert first == 5 and len(calls) == first               # one fetch per live or Yahoo symbol, then cached


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


def test_yahoo_history_is_cut_to_completed_days_from_the_stored_start(api, monkeypatch):
    client, _ = api
    start = int(pd.Timestamp("2022-06-01", tz="UTC").timestamp())
    today = int(time.time() // DAY) * DAY
    # Yahoo stamps Tokyo's daily bar at the 09:00 open, which is 00:00 UTC.
    candles = [{"time": t, "open": 1.0, "high": 1.0, "low": 1.0, "close": 100.0 + (t // DAY) % 7,
                "volume": 0.0} for t in range(start, today + DAY, DAY)]

    async def fake_yahoo(symbol, interval, limit):
        return candles, SimpleNamespace(exchange_timezone="Asia/Tokyo")

    monkeypatch.setattr(yahoo_history, "fetch_candle_series", fake_yahoo)
    risk_service.clear_cache()

    nikkei = next(a for a in client.get("/api/risk").json()["assets"] if a["symbol"] == "^N225")

    assert nikkei["start_date"] == "2023-01-01"
    assert nikkei["end_date"] == (pd.Timestamp(today, unit="s") - pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def test_a_failing_yahoo_symbol_is_left_out_with_a_note(api, monkeypatch):
    client, _ = api

    async def broken(symbol, interval, limit):
        raise yahoo_history.YahooHistoryError("Yahoo answered 429")

    monkeypatch.setattr(yahoo_history, "fetch_candle_series", broken)
    risk_service.clear_cache()

    report = client.get("/api/risk").json()

    symbols = {a["symbol"] for a in report["assets"]}
    assert symbols == {"BTC/USDT", "SOL/USDT", "AAPL"}
    for symbol in ("^N225", "EUR/USD", "CL=F"):
        assert any(symbol in note and "left out" in note for note in report["notes"])


def test_an_empty_database_with_no_exchange_gives_an_empty_report_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "empty.db")
    monkeypatch.setattr(main, "DATABASE_PATH", tmp_path / "empty.db")
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_SYMBOLS", ["BTC/USDT"])
    risk_service.clear_cache()

    async def broken(symbol, interval, limit):
        raise candle_source.CandleSourceError("down")

    monkeypatch.setattr(candle_source, "fetch_candles", broken)

    async def yahoo_down(symbol, interval, limit):
        raise yahoo_history.YahooHistoryError("down")

    monkeypatch.setattr(yahoo_history, "fetch_candle_series", yahoo_down)

    with TestClient(main.app) as client:
        response = client.get("/api/risk")

    assert response.status_code == 200
    assert response.json()["assets"] == [] and response.json()["count"] == 0
