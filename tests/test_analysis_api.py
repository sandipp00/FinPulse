"""The analysis routes: which history each asset uses, local dates, caching, errors."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import analysis_api, asset_news, config, main


def test_each_asset_uses_its_longest_daily_history():
    source = lambda key: analysis_api.daily_source(asset_news.find(key))  # noqa: E731
    assert source("gold") == ("database", "GC=F")
    assert source("btc") == ("database", "BTC/USDT")
    assert source("sol") == ("binance", "SOL/USDT")
    assert source("wti") == ("yahoo", "CL=F")
    assert source("n225") == ("yahoo", "^N225")
    assert source("eurusd") == ("yahoo", "EUR/USD")


def test_bars_are_dated_by_their_local_day_and_today_is_dropped():
    tokyo_midnight = int(datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc).timestamp())  # Oct 29 00:00 JST
    new_york_midnight = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())  # Oct 29 00:00 EDT
    today = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    closes = analysis_api.to_closes([
        {"time": tokyo_midnight, "close": 1.0},
        {"time": new_york_midnight + 86400, "close": 2.0},  # Oct 30 New York
        {"time": today, "close": 3.0},  # still forming
    ])
    assert [d.date().isoformat() for d in closes.index] == ["2026-10-29", "2026-10-30"][: len(closes)]
    assert 3.0 not in closes.values


def fake_closes(days=400):
    index = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.Series(100 * 1.001 ** np.arange(days), index=index)


@pytest.fixture
def client(monkeypatch):
    analysis_api.clear_cache()
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    calls = []

    async def load(asset):
        calls.append(asset.id)
        if asset.id == "sol":
            raise LookupError("binance history for SOL/USDT is unavailable: down")
        if asset.id == "xrp":
            return fake_closes(10), "binance", "XRP/USDT"
        return fake_closes(), "yahoo", asset.live

    monkeypatch.setattr(analysis_api, "load_closes", load)
    with TestClient(main.app) as test_client:
        test_client.calls = calls
        yield test_client
    analysis_api.clear_cache()


def test_scoreboard_has_a_row_for_every_asset_and_reports_failures(client):
    body = client.get("/api/analysis/scoreboard").json()
    rows = {row["asset"]["id"]: row for row in body["rows"]}
    assert body["count"] == len(asset_news.ASSETS) == len(rows)
    assert rows["gold"]["trend"] == "up" and rows["gold"]["return_1y"] == pytest.approx(1.001 ** 365 - 1)
    assert "unavailable" in rows["sol"]["error"]
    assert rows["xrp"]["error"] == "Not enough daily history"


def test_asset_detail_and_caching(client):
    body = client.get("/api/analysis/asset", params={"asset": "XAU/USDT"}).json()
    assert body["asset"]["id"] == "gold" and body["periods_per_year"] == 252
    assert {"performance", "risk", "distribution", "technicals", "monthly_returns", "series"} <= set(body)
    client.get("/api/analysis/asset", params={"asset": "gold"})
    assert client.calls.count("gold") == 1  # cached

    assert client.get("/api/analysis/asset", params={"asset": "sol"}).status_code == 502
    assert client.get("/api/analysis/asset", params={"asset": "xrp"}).status_code == 422
    assert client.get("/api/analysis/asset", params={"asset": "nope"}).status_code == 404
