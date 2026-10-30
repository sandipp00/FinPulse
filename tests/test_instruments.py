"""Instrument catalogue and the unified history endpoint. The exchange is mocked."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import candles as candle_source, config, main
from src.data.schema import MARKET_PRICES_DDL

STORED = [
    ("2026-10-12T00:00:00Z", "AAPL", "stock", 200, 205, 198, 204, 1000),
    ("2026-10-13T00:00:00Z", "AAPL", "stock", 204, 210, 203, 209, 1100),
    ("2026-10-14T00:00:00Z", "AAPL", "stock", 209, 211, 201, 202, 900),
    ("2026-10-13T00:00:00Z", "^NSEI", "index", 22000, 22100, 21900, 22050, 0),
    ("2026-10-14T00:00:00Z", "^NSEI", "index", 22050, 22700, 22000, 22622, 0),
    ("2026-10-13T00:00:00Z", "BTC/USDT", "crypto", 80000, 82000, 79000, 81000, 10),
    ("2026-10-14T00:00:00Z", "BTC/USDT", "crypto", 81000, 83000, 80500, 82268, 12),
]

LIVE_ROWS = [
    {"time": 1793232000, "open": 80000.0, "high": 81000.0, "low": 79500.0, "close": 80500.0, "volume": 5.0},
    {"time": 1793318400, "open": 80500.0, "high": 82000.0, "low": 80000.0, "close": 81900.0, "volume": 6.0},
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    with sqlite3.connect(path) as conn:
        conn.execute(MARKET_PRICES_DDL)
        conn.executemany("INSERT INTO market_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)", STORED)
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_SYMBOLS", ["BTC/USDT", "SOL/USDT"])
    monkeypatch.setattr(config, "TRADFI_LIVE_SYMBOLS", ["XAU/USDT"])
    candle_source._cache.clear()
    with TestClient(main.app) as test_client:
        yield test_client
    candle_source._cache.clear()


@pytest.fixture
def exchange(monkeypatch):
    """A fake exchange; set `exchange.fail = CandleSourceError(...)` to make it fail."""
    class Exchange:
        fail = None
        calls = []

    async def fake(symbol, interval, limit, allow_stale=False):
        Exchange.calls.append((symbol, interval, limit, allow_stale))
        if Exchange.fail:
            raise Exchange.fail
        meta = candle_source.SourceMeta(provider="binance", endpoint="api.binance.com", status="historical")
        return candle_source.CandleSeries(list(LIVE_ROWS), meta)

    monkeypatch.setattr(candle_source, "fetch_candle_series", fake)
    return Exchange


def by_symbol(client):
    return {item["symbol"]: item for item in client.get("/api/instruments").json()["instruments"]}


# ---- catalogue ---------------------------------------------------------

def test_catalogue_lists_live_and_stored_instruments(client):
    items = by_symbol(client)

    assert set(items) == {"BTC/USDT", "SOL/USDT", "XAU/USDT", "AAPL", "^NSEI"}

    btc = items["BTC/USDT"]
    assert btc["live"] is True
    assert btc["intervals"] == ["1m", "15m", "1h", "1d"]
    assert btc["currency"] == "USDT"
    assert btc["stored"]["bars"] == 2

    assert items["SOL/USDT"]["stored"] is None  # live only

    gold = items["XAU/USDT"]  # live gold: Binance futures, intraday intervals
    assert gold["live"] is True
    assert gold["asset_class"] == "commodity"
    assert gold["unit"] == "per troy ounce"
    assert gold["currency"] == "USDT"
    assert gold["intervals"] == ["1m", "15m", "1h", "1d"]

    aapl = items["AAPL"]
    assert aapl["live"] is False
    assert aapl["intervals"] == ["1d"]
    assert aapl["asset_class"] == "stock"
    assert aapl["currency"] == "USD"
    assert aapl["stored"]["first"].startswith("2026-10-12")
    assert aapl["stored"]["last"].startswith("2026-10-14")

    assert items["^NSEI"]["unit"] == "index points"
    assert items["^NSEI"]["currency"] == "INR"


def test_catalogue_without_a_database_still_lists_live_symbols(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "missing.db")

    assert set(by_symbol(client)) == {"BTC/USDT", "SOL/USDT", "XAU/USDT"}


# ---- stored history ----------------------------------------------------

def test_stored_history_is_daily_with_source_metadata(client):
    body = client.get("/api/instruments/history", params={"symbol": "AAPL"}).json()

    assert body["source"] == "database"
    assert body["interval"] == "1d"
    assert body["currency"] == "USD"
    assert body["unit"] == "per share"
    assert body["count"] == 3
    assert [c["close"] for c in body["candles"]] == [204, 209, 202]  # oldest first
    assert body["candles"][0]["time"] == 1791763200  # 2026-10-12T00:00:00Z
    assert body["meta"]["provider"] == "database"
    assert body["meta"]["status"] == "historical"
    assert body["meta"]["source_timestamp"].startswith("2026-10-14T00:00:00")


def test_stored_history_limit_keeps_the_latest_bars(client):
    body = client.get("/api/instruments/history", params={"symbol": "AAPL", "limit": 2}).json()

    assert [c["close"] for c in body["candles"]] == [209, 202]


def test_stored_history_is_daily_only(client):
    response = client.get("/api/instruments/history", params={"symbol": "AAPL", "interval": "1h"})

    assert response.status_code == 400
    assert "1d" in response.json()["detail"]


def test_unknown_instruments_and_missing_sources(client):
    assert client.get("/api/instruments/history", params={"symbol": "TSLA"}).status_code == 404
    assert client.get(
        "/api/instruments/history", params={"symbol": "AAPL", "source": "binance"}
    ).status_code == 400
    assert client.get(
        "/api/instruments/history", params={"symbol": "SOL/USDT", "source": "database"}
    ).status_code == 404
    assert client.get(
        "/api/instruments/history", params={"symbol": "AAPL", "source": "elsewhere"}
    ).status_code == 422


# ---- exchange history --------------------------------------------------

def test_live_symbols_use_the_exchange_by_default(client, exchange):
    body = client.get(
        "/api/instruments/history", params={"symbol": "BTC/USDT", "interval": "1h", "limit": 100}
    ).json()

    assert body["source"] == "binance"
    assert body["interval"] == "1h"
    assert body["currency"] == "USDT"
    assert body["count"] == 2
    assert body["meta"]["provider"] == "binance"
    assert exchange.calls == [("BTC/USDT", "1h", 100, True)]


def test_a_live_symbol_can_still_ask_for_stored_history(client, exchange):
    body = client.get(
        "/api/instruments/history", params={"symbol": "BTC/USDT", "source": "database"}
    ).json()

    assert body["source"] == "database"
    assert body["count"] == 2
    assert exchange.calls == []


def test_exchange_limits_are_enforced(client, exchange):
    response = client.get("/api/instruments/history", params={"symbol": "BTC/USDT", "limit": 10})

    assert response.status_code == 422
    assert exchange.calls == []


def test_daily_requests_fall_back_to_stored_history_when_the_exchange_fails(client, exchange):
    exchange.fail = candle_source.CandleSourceError("api.binance.com: ConnectError")

    body = client.get("/api/instruments/history", params={"symbol": "BTC/USDT", "interval": "1d"}).json()

    assert body["source"] == "database"
    assert body["meta"]["provider"] == "database"
    assert "Exchange unavailable" in body["meta"]["notes"][0]
    assert body["count"] == 2


def test_no_fallback_for_intraday_or_live_only_symbols(client, exchange):
    exchange.fail = candle_source.CandleSourceError("down")

    assert client.get(
        "/api/instruments/history", params={"symbol": "BTC/USDT", "interval": "1h"}
    ).status_code == 502
    assert client.get(
        "/api/instruments/history", params={"symbol": "SOL/USDT", "interval": "1d"}
    ).status_code == 502


def test_rate_limiting_is_a_503_with_retry_after(client, exchange):
    exchange.fail = candle_source.CandleSourceError("limited", retry_after=42)

    response = client.get("/api/instruments/history", params={"symbol": "SOL/USDT", "interval": "1h"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "42"
