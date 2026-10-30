"""The VIX term structure: the curve, VIX3M / VIX, its history, and failures. No network."""
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import config, main, vix_curve, yahoo_history

DAY = 86_400
START = 1_790_000_000  # a Tuesday


def bars(closes):
    return [{"time": START + i * DAY, "open": c, "high": c, "low": c, "close": c, "volume": 0.0} for i, c in enumerate(closes)]


def test_the_shape_is_read_from_vix3m_over_vix():
    assert vix_curve.shape(1.10) == "contango"
    assert vix_curve.shape(1.01) == "flat"
    assert vix_curve.shape(0.85) == "backwardation"
    assert vix_curve.shape(None) is None


def test_ratio_history_uses_shared_days_and_skips_zero():
    days = pd.to_datetime(["2026-10-26", "2026-10-27", "2026-10-28"])
    vix = pd.Series([20.0, 0.0, 25.0], index=days)
    vix3m = pd.Series([22.0, 21.0, 20.0], index=days)
    assert vix_curve.ratio_history(vix, vix3m).tolist() == [1.1, 0.8]
    assert vix_curve.percentile(0.8, pd.Series([0.8, 1.1])) == 50


@pytest.fixture
def api(monkeypatch):
    vix_curve.clear_cache()
    monkeypatch.setattr(vix_curve, "_lock", None)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    series = {"^VIX9D": [18, 19, 21, 30], "^VIX": [20, 20, 20, 25], "^VIX3M": [22, 22, 21, 24], "^VIX6M": [23, 23, 23, 24]}
    state = {"calls": 0, "down": set()}

    async def fake(symbol, interval, limit):
        state["calls"] += 1
        if symbol in state["down"]:
            raise yahoo_history.YahooHistoryError("Yahoo answered 429")
        closes = series.get(symbol, [23.0])  # ^VIX1Y: today only
        return bars(closes), SimpleNamespace(exchange_timezone="America/New_York")

    monkeypatch.setattr(yahoo_history, "fetch_candle_series", fake)
    with TestClient(main.app) as client:
        yield client, state


def test_the_curve_now_and_the_ratio(api):
    client, state = api
    body = client.get("/api/vix-curve").json()
    assert [p["value"] for p in body["curve"]] == [30, 25, 24, 24, 23.0]
    assert body["ratio"] == 0.96 and body["shape"] == "backwardation"  # more than 3% below 1
    assert [p["value"] for p in body["ratio_history"]] == [1.1, 1.1, 1.05, 0.96]  # past days, all completed
    assert body["curve"][4]["history_days"] in (0, 1)
    assert state["calls"] == 5
    client.get("/api/vix-curve")
    assert state["calls"] == 5  # cached


def test_a_missing_index_is_reported_and_all_missing_is_an_error(api):
    client, state = api
    state["down"] = {"^VIX6M"}
    body = client.get("/api/vix-curve").json()
    assert body["curve"][3]["value"] is None and any("^VIX6M" in e for e in body["errors"])

    vix_curve.clear_cache()
    state["down"] = {s for s, _, _ in vix_curve.TENORS}
    assert client.get("/api/vix-curve").status_code == 502
