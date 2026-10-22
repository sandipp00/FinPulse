import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import config, main
from src.analytics.financial_metrics import asset_snapshot


@pytest.fixture
def client(tmp_path, monkeypatch):
    """API against a throwaway database, with the live feed switched off."""
    db_path = tmp_path / "finpulse.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE market_prices (
                timestamp TEXT, symbol TEXT, asset_type TEXT,
                open REAL, high REAL, low REAL, close REAL, volume REAL
            )
        """)
        conn.executemany(
            "INSERT INTO market_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2025-01-01T00:00:00Z", "BTC/USDT", "crypto", 100, 101, 99, 100, 5),
                ("2025-01-02T00:00:00Z", "BTC/USDT", "crypto", 100, 112, 99, 110, 6),
                ("2025-01-03T00:00:00Z", "BTC/USDT", "crypto", 110, 111, 88, 90, 7),
            ],
        )

    monkeypatch.setattr(main, "DATABASE_PATH", db_path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_assets_returns_metrics(client):
    body = client.get("/api/assets").json()

    assert body["count"] == 1
    asset = body["assets"][0]
    assert asset["symbol"] == "BTC/USDT"
    assert asset["latest_price"] == 90.0
    assert asset["total_return_pct"] == pytest.approx(-10.0)
    assert asset["max_drawdown_pct"] == pytest.approx(-18.1818, abs=1e-3)


def test_prices_unknown_symbol_is_404(client):
    assert client.get("/api/prices", params={"symbol": "NOPE"}).status_code == 404


def test_prices_respects_limit(client):
    body = client.get("/api/prices", params={"symbol": "BTC/USDT", "limit": 2}).json()

    assert body["count"] == 2
    assert body["prices"][-1]["close"] == 90.0


def test_live_status_reports_disabled(client):
    assert client.get("/api/live/status").json()["enabled"] is False


def test_websocket_closes_when_live_feed_disabled(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/prices") as socket:
            socket.receive_json()


def test_asset_snapshot_uses_365_day_year_for_crypto():
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"], utc=True),
        "symbol": "X",
        "asset_type": "crypto",
        "close": [100.0, 110.0, 99.0],
    })
    stock = frame.assign(asset_type="stock")

    crypto_vol = asset_snapshot(frame)["annualized_volatility_pct"]
    stock_vol = asset_snapshot(stock)["annualized_volatility_pct"]

    assert crypto_vol / stock_vol == pytest.approx((365 / 252) ** 0.5)
