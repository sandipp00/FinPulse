"""The asset registry and per-asset news. Yahoo is mocked; general news is stubbed."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import asset_news, config, main, news


def rss(*items):
    body = "".join(
        f"<item><title>{title}</title><link>https://news.example/{slug}</link>"
        f"<pubDate>{when}</pubDate><description>{summary}</description></item>"
        for title, slug, when, summary in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Yahoo</title>{body}</channel></rss>'.encode()


FEEDS = {
    "GC=F": rss(
        ("Gold falls below $4,000 as inflation concerns weigh", "gold-1", "Fri, 30 Oct 2026 01:46:13 +0000", "Bullion slid."),
        ("Tech stocks rally ahead of earnings", "tech-1", "Fri, 30 Oct 2026 02:00:00 +0000", "Gold was flat."),
    ),
    "CL=F": rss(("Oil climbs on supply worries", "oil-1", "Fri, 30 Oct 2026 03:00:00 +0000", "")),
    "BZ=F": rss(
        ("Brent crude tops $116", "oil-2", "Thu, 29 Oct 2026 12:00:00 +0000", ""),
        ("Oil climbs on supply worries", "oil-1", "Fri, 30 Oct 2026 03:00:00 +0000", ""),  # in both feeds
    ),
    "BTC-USD": rss(("Bitcoin is getting boring", "btc-1", "Fri, 30 Oct 2026 05:00:00 +0000", "")),
}

GENERAL = [
    {"id": "c1", "source": "coindesk", "source_name": "CoinDesk", "title": "Bitcoin ETF flows turn positive",
     "url": "https://coindesk.example/1", "published_at": "2026-10-30T04:00:00Z", "summary": "",
     "topics": ["crypto"], "instruments": ["BTC/USDT"]},
    {"id": "e1", "source": "ecb", "source_name": "European Central Bank", "title": "Monetary policy decisions",
     "url": "https://ecb.example/1", "published_at": "2026-10-29T12:15:00Z", "summary": "",
     "topics": ["fx", "rates"], "instruments": []},
]


@pytest.fixture(autouse=True)
def web(monkeypatch):
    asset_news.clear_cache()
    requests = []

    def handle(request):
        requests.append(request)
        symbol = request.url.params["s"]
        if symbol not in FEEDS:
            return httpx.Response(503)
        return httpx.Response(200, content=FEEDS[symbol])

    monkeypatch.setattr(news, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    async def collect():
        return list(GENERAL), [{"id": "coindesk", "name": "CoinDesk", "status": "ok", "count": 1},
                               {"id": "sec", "name": "SEC EDGAR", "status": "not_configured", "count": 0}]

    monkeypatch.setattr(news, "collect", collect)
    yield requests
    asset_news.clear_cache()


def headlines(key):
    return asyncio.run(asset_news.asset_headlines(asset_news.find(key)))


def test_assets_are_found_by_id_or_any_of_their_symbols():
    assert asset_news.find("gold").name == "Gold"
    assert asset_news.find("GC=F").id == "gold" and asset_news.find("XAU/USDT").id == "gold"
    assert asset_news.find("RWTC").id == "wti"
    assert asset_news.find("EUR/USD").id == "eurusd"
    assert asset_news.find("DOGE/USDT") is None


def test_yahoo_headlines_must_name_the_asset(web):
    body = headlines("gold")

    assert [i["title"] for i in body["items"]] == ["Gold falls below $4,000 as inflation concerns weigh"]
    yahoo = body["sources"][0]
    assert yahoo["status"] == "ok" and yahoo["count"] == 1 and yahoo["filtered_out"] == 1
    assert web[0].headers["User-Agent"] == config.FEED_USER_AGENT
    assert body["items"][0]["source_name"] == "Yahoo Finance" and body["items"][0]["url"] == "https://news.example/gold-1"


def test_oil_assets_share_both_oil_feeds_without_repeats():
    body = headlines("wti")
    assert [i["url"] for i in body["items"]] == ["https://news.example/oil-1", "https://news.example/oil-2"]
    assert body["sources"][0]["count"] == 2


def test_crypto_merges_yahoo_with_tagged_general_news_newest_first():
    body = headlines("btc")
    assert [i["source"] for i in body["items"]] == ["yahoo", "coindesk"]
    assert [s["id"] for s in body["sources"]] == ["yahoo", "coindesk"]  # not-configured sources are left out


def test_fx_assets_include_central_bank_releases():
    body = headlines("eurusd")  # Yahoo has no EURUSD=X feed in this test: it is reported, not hidden
    assert [i["source"] for i in body["items"]] == ["ecb"]
    assert body["sources"][0]["status"] == "unavailable" and "503" in body["sources"][0]["error"]


def test_a_failed_refresh_serves_the_kept_headlines_marked_stale(web, monkeypatch):
    headlines("gold")
    clock = [asset_news._monotonic() + asset_news.CACHE_SECONDS + 1]
    monkeypatch.setattr(asset_news, "_monotonic", lambda: clock[0])
    monkeypatch.setitem(FEEDS, "GC=F", b"not xml")

    body = headlines("gold")
    assert body["items"][0]["stale"] is True
    assert body["sources"][0]["status"] == "stale"


def test_headlines_are_cached_between_refreshes(web):
    headlines("gold")
    headlines("gold")
    assert len(web) == 1


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_registry_and_news_endpoints(client):
    registry = client.get("/api/asset-registry").json()
    gold = next(a for a in registry["assets"] if a["id"] == "gold")
    assert gold["live"] == "XAU/USDT" and gold["stored"] == "GC=F" and gold["has_news"] is True
    nifty = next(a for a in registry["assets"] if a["id"] == "nifty")
    assert nifty["has_news"] is False

    body = client.get("/api/asset-news", params={"asset": "GC=F"}).json()
    assert body["asset"]["id"] == "gold" and body["count"] == 1 and body["refresh_seconds"] == 120

    assert client.get("/api/asset-news", params={"asset": "nifty"}).json()["items"] == []
    assert client.get("/api/asset-news", params={"asset": "nope"}).status_code == 404
