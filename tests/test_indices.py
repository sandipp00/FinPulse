"""The world indices: registry, asset class, currency and the endpoint."""
from fastapi.testclient import TestClient

from backend import config, indices, main, market_service, quotes_live


def test_thirty_six_indices_across_four_regions():
    assert len(indices.WORLD_INDICES) == 36
    assert {row[2] for row in indices.WORLD_INDICES} == set(indices.REGIONS)
    assert set(indices.INDEX_SYMBOLS) <= set(config.YAHOO_LIVE_SYMBOLS)  # every index is polled live


def test_indices_are_index_class_in_their_own_currency():
    assert quotes_live.asset_class_for("000001.SS") == "index"  # Shanghai has no ^ prefix
    assert quotes_live.asset_class_for("^FTSE") == "index"
    assert quotes_live.asset_class_for("AAPL") == "stock"
    assert market_service.currency_of("^N225") == "JPY"
    assert market_service.currency_of("000001.SS") == "CNY"
    assert market_service.currency_of("^GSPC") == "USD"
    assert market_service.currency_of("^VIX") is None  # points, not a price
    assert quotes_live.asset_class_for("FTSEMIB.MI") == "index"


def test_world_indices_endpoint(monkeypatch):
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as client:
        body = client.get("/api/world-indices").json()
    assert body["count"] == 36
    assert body["regions"] == ["Americas", "Europe", "Asia-Pacific", "Middle East & Africa"]
    hsi = next(i for i in body["indices"] if i["symbol"] == "^HSI")
    assert hsi == {"symbol": "^HSI", "name": "Hang Seng", "region": "Asia-Pacific", "country": "Hong Kong",
                   "currency": "HKD", "timezone": "Asia/Hong_Kong"}
