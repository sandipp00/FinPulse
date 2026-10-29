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
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)  # init_db() runs at startup
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
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/prices") as socket:
            socket.receive_json()

    # 1013 = "try again later": the handshake was accepted and the feed is off.
    # (An error in the app-wide dependencies would be a 500 instead.)
    assert closed.value.code == 1013


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


# ---- /api/candles ----------------------------------------------------

KLINES = [
    [1700000000000, "100.0", "105.0", "99.0", "104.0", "12.5", 1700000059999],
    [1700000060000, "104.0", "106.0", "103.0", "105.5", "8.0", 1700000119999],
]


def test_parse_klines():
    from backend.candles import parse_klines

    assert parse_klines(KLINES)[0] == {
        "time": 1700000000, "open": 100.0, "high": 105.0,
        "low": 99.0, "close": 104.0, "volume": 12.5,
    }


def test_candles_endpoint_returns_parsed_rows(client, monkeypatch):
    from backend import candles as candle_source

    async def fake_get_json(_client, _url, params):
        assert params["symbol"] == "BTCUSDT"
        assert params["interval"] == "15m"
        return KLINES

    monkeypatch.setattr(candle_source, "_get_json", fake_get_json)
    candle_source._cache.clear()

    body = client.get(
        "/api/candles", params={"symbol": "BTC/USDT", "interval": "15m", "limit": 50}
    ).json()

    assert body["count"] == 2
    assert body["candles"][1]["close"] == 105.5


def test_candles_rejects_unknown_symbol_and_interval(client):
    assert client.get("/api/candles", params={"symbol": "DOGE/USDT"}).status_code == 404
    assert client.get(
        "/api/candles", params={"symbol": "BTC/USDT", "interval": "3m"}
    ).status_code == 400
    assert client.get(
        "/api/candles", params={"symbol": "BTC/USDT", "limit": 5}
    ).status_code == 422


def test_candles_returns_502_when_exchange_unreachable(client, monkeypatch):
    import httpx

    from backend import candles as candle_source

    async def failing_get_json(_client, _url, _params):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(candle_source, "_get_json", failing_get_json)
    candle_source._cache.clear()

    response = client.get("/api/candles", params={"symbol": "ETH/USDT"})

    assert response.status_code == 502


# ---- /api/signals and /api/backtest ------------------------------------

def _fake_rows(n=300, interval_seconds=3600, trend=0.5):
    import numpy as np

    rng = np.random.default_rng(7)
    closes = 100 + trend * np.arange(n) + rng.normal(0, 1.5, n)
    start = 1_700_000_000
    return [
        {
            "time": start + i * interval_seconds,
            "open": float(closes[i - 1] if i else closes[0]),
            "high": float(closes[i] + 1),
            "low": float(closes[i] - 1),
            "close": float(closes[i]),
            "volume": 100.0,
        }
        for i in range(n)
    ]


@pytest.fixture
def fake_candles(monkeypatch):
    from backend import candles as candle_source

    async def fake_fetch(symbol, interval, limit):
        return _fake_rows()

    monkeypatch.setattr(candle_source, "fetch_candles", fake_fetch)


def test_to_closed_frame_drops_the_forming_candle():
    from backend.signal_service import to_closed_frame

    rows = _fake_rows(n=3)
    # "now" is halfway through the last candle.
    now = rows[-1]["time"] + 1800

    frame = to_closed_frame(rows, "1h", now=now)

    assert len(frame) == 2
    assert frame["time"].iloc[-1] == rows[1]["time"]


def test_signals_endpoint_returns_a_rated_signal_per_symbol(client, fake_candles):
    body = client.get("/api/signals", params={"interval": "1h"}).json()

    assert body["count"] == len(config.LIVE_SYMBOLS)
    first = body["signals"][0]
    assert first["rating"] in {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}
    assert len(first["reasons"]) == 6
    assert "not investment advice" in body["disclaimer"]


def test_signals_endpoint_filters_to_one_symbol(client, fake_candles):
    body = client.get("/api/signals", params={"symbol": "ETH/USDT"}).json()

    assert [item["symbol"] for item in body["signals"]] == ["ETH/USDT"]


def test_signals_validation(client):
    assert client.get("/api/signals", params={"interval": "3m"}).status_code == 400
    assert client.get("/api/signals", params={"symbol": "DOGE/USDT"}).status_code == 404


def test_backtest_endpoint_reports_strategy_and_benchmark(client, fake_candles):
    body = client.get(
        "/api/backtest", params={"symbol": "BTC/USDT", "interval": "1h"}
    ).json()

    assert body["symbol"] == "BTC/USDT"
    assert body["fee_pct"] == 0.1
    assert "strategy_return_pct" in body and "buy_hold_return_pct" in body
    assert body["trades"]["count"] >= len(body["trades"]["list"])
    assert len(body["trades"]["list"]) <= 20  # only the most recent are listed
    assert isinstance(body["sample_warning"], bool)
    assert body["equity_curve"]


def test_backtest_validation_and_short_history(client, monkeypatch):
    from backend import candles as candle_source

    async def short_history(symbol, interval, limit):
        return _fake_rows(n=20)

    monkeypatch.setattr(candle_source, "fetch_candles", short_history)

    assert client.get("/api/backtest", params={"symbol": "BTC/USDT", "interval": "9m"}).status_code == 400
    assert client.get("/api/backtest", params={"symbol": "BTC/USDT", "fee_pct": 5}).status_code == 422
    assert client.get("/api/backtest", params={"symbol": "BTC/USDT"}).status_code == 422


def test_websocket_streams_a_snapshot_when_the_feed_is_on(client, monkeypatch):
    """Regression: app-wide dependencies must not break WebSocket routes."""
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", True)
    monkeypatch.setattr(main.feed, "latest", {"BTC/USDT": {"symbol": "BTC/USDT", "price": 1.0}})

    with client.websocket_connect("/ws/prices") as socket:
        message = socket.receive_json()

    assert message["type"] == "snapshot"
    assert message["ticks"][0]["symbol"] == "BTC/USDT"


def test_websocket_from_another_site_is_refused(client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", True)

    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/prices", headers={"origin": "https://evil.example"}):
            pass
    assert closed.value.code == 1008

    allowed = {"origin": config.CORS_ORIGINS[0]}
    with client.websocket_connect("/ws/prices", headers=allowed) as socket:
        assert socket.receive_json()["type"] == "snapshot"


def test_backtest_endpoint_passes_slippage_and_position_size(client, fake_candles):
    base = {"symbol": "BTC/USDT", "interval": "1h"}
    default = client.get("/api/backtest", params=base).json()
    custom = client.get("/api/backtest", params={**base, "slippage_bps": 10, "position_pct": 50}).json()

    assert (default["slippage_pct"], default["position_size_pct"]) == (0.0, 100.0)
    assert (custom["slippage_pct"], custom["position_size_pct"]) == (0.1, 50.0)
    assert custom["buy_hold_return_pct"] != default["buy_hold_return_pct"]
    assert "trend" in custom["baselines"] and "split" in custom


@pytest.mark.parametrize("params", [{"slippage_bps": -1}, {"slippage_bps": 101}, {"position_pct": 0}, {"position_pct": 120}])
def test_backtest_settings_are_validated(client, params):
    response = client.get("/api/backtest", params={"symbol": "BTC/USDT", "interval": "1h", **params})
    assert response.status_code == 422
