"""News feeds and the economic calendar. Every source is mocked (httpx.MockTransport).

The sample feeds follow the real ones checked on 2026-10-30: Fed and ECB RSS with
GMT/+0100 dates, BEA with "EDT", CoinDesk with HTML descriptions, and EDGAR's
submissions JSON.
"""
import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import config, econ_calendar, fred, main, news

SOURCES = {s.id: s for s in news.SOURCES}


def rss(*items):
    body = "".join(
        "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in item.items()) + "</item>" for item in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


FED = rss({"title": "Federal Reserve issues FOMC statement",
           "link": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm",
           "pubDate": "Wed, 28 Oct 2026 18:00:00 GMT", "description": "Federal Reserve issues FOMC statement"},
          {"title": "Minutes of the Board&amp;#39;s discount rate meetings",
           "link": "https://www.federalreserve.gov/x.htm", "pubDate": "Tue, 13 Oct 2026 18:00:00 GMT"})
ECB = rss({"title": "Monetary policy statement", "link": "https://www.ecb.europa.eu//press/press_conference/2026",
           "pubDate": "Thu, 29 Oct 2026 15:00:00 +0100"})
BEA = rss({"title": "GDP (Advance Estimate), 3rd Quarter 2026", "link": "https://www.bea.gov/news/2026/gdp",
           "pubDate": "Thu, 29 Oct 2026 08:30:00 EDT",
           "description": "&lt;p&gt;Real gross domestic product (GDP) increased at an annual rate of 3.4 percent.&lt;/p&gt;"})
COINDESK = rss({"title": "Bitcoin options near expiry as ETH lags", "link": "https://www.coindesk.com/markets/a",
                "pubDate": "Thu, 29 Oct 2026 18:55:35 +0000", "description": "Traders watch BTC and Solana."},
               {"title": "No date here", "link": "https://www.coindesk.com/b"},
               {"title": "Bad link", "link": "javascript:alert(1)", "pubDate": "Thu, 29 Oct 2026 10:00:00 +0000"},
               {"title": "Naive time", "link": "https://www.coindesk.com/c", "pubDate": "2026-10-29T10:00:00"})
EDGAR = {
    "cik": "0000320193", "name": "Apple Inc.",
    "filings": {"recent": {
        "form": ["4", "10-Q", "8-K", "8-K"],
        "accessionNumber": ["0000320193-26-000021", "0000320193-26-000020", "0000320193-26-000018", "0000320193-26-000017"],
        "acceptanceDateTime": ["2026-08-01T22:00:00.000Z", "2026-07-31T10:01:02.000Z", "2026-07-30T20:30:28.000Z", ""],
        "primaryDocument": ["x.xml", "aapl-20260627.htm", "aapl-20260730.htm", "y.htm"],
        "primaryDocDescription": ["4", "10-Q", "8-K", "8-K"],
        "filingDate": ["2026-08-01", "2026-07-31", "2026-07-30", "2026-07-01"],
        "reportDate": ["", "2026-06-27", "2026-07-30", ""],
    }},
}


# ---- text and link handling -------------------------------------------------------

def test_plain_text_strips_html_and_double_escaping():
    assert news.plain_text("Minutes of the Board&amp;#39;s meeting") == "Minutes of the Board's meeting"
    assert news.plain_text("<p style='x'><img src='a.png'/>Real GDP <b>rose</b></p>") == "Real GDP rose"
    assert news.plain_text("word " * 100, 30).endswith("…")
    assert len(news.plain_text("word " * 100, 30)) <= 30


@pytest.mark.parametrize("raw, expected", [
    ("https://www.ecb.europa.eu//press/x.html", "https://www.ecb.europa.eu/press/x.html"),
    ("https://a.example/p//q?u=https://b//c", "https://a.example/p/q?u=https://b//c"),
    ("  https://a.example/ok  ", "https://a.example/ok"),
    ("javascript:alert(1)", None),
    ("data:text/html,x", None),
    ("/relative/path", None),
    ("", None),
    (None, None),
])
def test_only_absolute_http_links_survive(raw, expected):
    assert news.clean_url(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Wed, 28 Oct 2026 18:00:00 GMT", "2026-10-28T18:00:00+00:00"),
    ("Thu, 29 Oct 2026 15:00:00 +0100", "2026-10-29T14:00:00+00:00"),
    ("Thu, 29 Oct 2026 08:30:00 EDT", "2026-10-29T12:30:00+00:00"),
    ("2026-07-30T20:30:28.000Z", "2026-07-30T20:30:28+00:00"),
])
def test_publication_times_become_utc(raw, expected):
    assert news.parse_time(raw).isoformat() == expected


@pytest.mark.parametrize("raw", ["", None, "yesterday", "2026-10-29T10:00:00"])
def test_unplaceable_times_are_rejected(raw):
    assert news.parse_time(raw) is None


def test_instrument_tags_match_tickers_exactly_and_names_loosely():
    assert news.tag_instruments("Bitcoin rallies; ETH and SOL follow") == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    assert news.tag_instruments("A solid quarter for consolidation") == []
    assert news.tag_instruments("ripple effects") == ["XRP/USDT"]
    assert news.tag_instruments("apple pie recipe") == []
    assert news.tag_instruments("Apple unveils a new iPhone") == ["AAPL"]


# ---- parsers ----------------------------------------------------------------------

def test_rss_items_keep_headline_snippet_link_source_and_time():
    items, dropped = news.parse_rss(SOURCES["bea"], BEA)

    assert dropped == 0
    (item,) = items
    assert item["title"] == "GDP (Advance Estimate), 3rd Quarter 2026"
    assert item["summary"].startswith("Real gross domestic product")
    assert item["url"] == "https://www.bea.gov/news/2026/gdp"
    assert item["published_at"] == "2026-10-29T12:30:00Z"
    assert item["source"] == "bea" and item["topics"] == ["macro"]
    assert set(item) == {"id", "source", "source_name", "title", "url", "published_at", "summary", "topics", "instruments"}


def test_items_without_a_time_a_safe_link_or_a_zone_are_dropped_and_counted():
    items, dropped = news.parse_rss(SOURCES["coindesk"], COINDESK)
    assert [i["title"] for i in items] == ["Bitcoin options near expiry as ETH lags"]
    assert dropped == 3
    assert items[0]["instruments"] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def test_a_summary_that_repeats_the_title_is_left_empty():
    items, _ = news.parse_rss(SOURCES["fed"], FED)
    assert items[0]["summary"] == ""
    assert items[1]["title"] == "Minutes of the Board's discount rate meetings"


@pytest.mark.parametrize("content, reason", [
    (b"<html><body>Maintenance</body></html>", "not an RSS feed"),
    (b"not xml at all", "not valid XML"),
    (b'<?xml version="1.0"?><rss></rss>', "not an RSS feed"),
])
def test_non_feeds_are_errors(content, reason):
    with pytest.raises(news.NewsError, match=reason):
        news.parse_rss(SOURCES["fed"], content)


def test_entity_expansion_is_not_followed():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
            b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;"><!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">'
            b'<!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;"><!ENTITY f "&e;&e;&e;&e;&e;&e;&e;&e;&e;&e;">'
            b'<!ENTITY g "&f;&f;&f;&f;&f;&f;&f;&f;&f;&f;"><!ENTITY h "&g;&g;&g;&g;&g;&g;&g;&g;&g;&g;">]>'
            b'<rss><channel><item><title>&h;</title></item></channel></rss>')
    with pytest.raises(news.NewsError):
        news.parse_rss(SOURCES["fed"], bomb)


def test_edgar_filings_link_to_the_document_with_their_acceptance_time():
    items, dropped = news.parse_edgar(SOURCES["sec"], EDGAR)

    assert [i["title"] for i in items] == ["Apple Inc. filed 10-Q", "Apple Inc. filed 8-K"]  # form 4 skipped
    assert dropped == 1  # the 8-K without an acceptance time
    assert items[1]["url"] == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/aapl-20260730.htm"
    assert items[1]["published_at"] == "2026-07-30T20:30:28Z"
    assert items[0]["summary"] == "Form 10-Q filed 2026-07-31 for the period ending 2026-06-27."
    assert items[0]["instruments"] == ["AAPL"]


@pytest.mark.parametrize("body", [{}, {"name": "x", "cik": "1"}, {"name": "x", "cik": "1", "filings": {"recent": {}}}])
def test_malformed_edgar_data_is_an_error(body):
    with pytest.raises(news.NewsError):
        news.parse_edgar(SOURCES["sec"], body)


# ---- fetching -----------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.mono, self.wall = 100.0, 1_793_300_000.0

    def advance(self, s):
        self.mono += s
        self.wall += s


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    for module in (news, econ_calendar):
        monkeypatch.setattr(module, "_monotonic", lambda: c.mono)
        monkeypatch.setattr(module, "_wall", lambda: c.wall)
    return c


FEEDS = {
    "www.federalreserve.gov": lambda r: httpx.Response(200, content=FED),
    "www.ecb.europa.eu": lambda r: httpx.Response(200, content=ECB),
    "apps.bea.gov": lambda r: httpx.Response(200, content=BEA) if r.url.path.endswith("rss.xml")
    else httpx.Response(200, json={"Gross Domestic Product": {"release_dates": [
        "2026-10-29T12:30:00+00:00", "2026-11-25T13:30:00+00:00"]}}),
    "www.coindesk.com": lambda r: httpx.Response(200, content=COINDESK),
    "data.sec.gov": lambda r: httpx.Response(200, json=EDGAR),
}


@pytest.fixture(autouse=True)
def web(monkeypatch, clock):
    monkeypatch.setattr(config, "SEC_USER_AGENT", "FinPulse-tests test@example.invalid")
    news.clear_cache()
    econ_calendar.clear_cache()

    class Web:
        routes = dict(FEEDS)
        requests = []

    def handle(request):
        Web.requests.append(request)
        handler = Web.routes.get(request.url.host)
        if handler is None:
            raise httpx.ConnectError("no route", request=request)
        return handler(request)

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(news, "_client", httpx.AsyncClient(transport=transport))
    monkeypatch.setattr(econ_calendar, "_client", httpx.AsyncClient(transport=transport))
    yield Web
    news.clear_cache()
    econ_calendar.clear_cache()


def collect():
    return asyncio.run(news.collect())


def test_collect_merges_sources_newest_first_with_status(web):
    items, sources = collect()

    assert [i["published_at"] for i in items] == sorted((i["published_at"] for i in items), reverse=True)
    status = {s["id"]: s for s in sources}
    assert {s["status"] for s in sources} == {"ok"}
    assert status["coindesk"]["dropped"] == 3
    assert status["sec"]["count"] == 2
    sec_request = next(r for r in web.requests if r.url.host == "data.sec.gov")
    assert sec_request.headers["User-Agent"] == "FinPulse-tests test@example.invalid"
    fed_request = next(r for r in web.requests if r.url.host == "www.federalreserve.gov")
    assert fed_request.headers["User-Agent"] == config.FEED_USER_AGENT


def test_without_a_sec_user_agent_edgar_is_not_contacted(web, monkeypatch):
    monkeypatch.setattr(config, "SEC_USER_AGENT", None)
    items, sources = collect()

    sec = next(s for s in sources if s["id"] == "sec")
    assert sec["status"] == "not_configured" and "SEC_USER_AGENT" in sec["error"]
    assert not any(r.url.host == "data.sec.gov" for r in web.requests)
    assert items  # the other sources still work


def test_one_failing_source_does_not_hide_the_rest(web):
    web.routes["www.ecb.europa.eu"] = lambda r: httpx.Response(503, text="down")
    items, sources = collect()

    ecb = next(s for s in sources if s["id"] == "ecb")
    assert ecb["status"] == "unavailable" and "503" in ecb["error"]
    assert {i["source"] for i in items} == {"fed", "bea", "coindesk", "sec"}


def test_oversized_and_unreachable_sources_are_errors(web, monkeypatch):
    monkeypatch.setattr(news, "MAX_BYTES", 100)
    del web.routes["data.sec.gov"]
    _, sources = collect()
    status = {s["id"]: s for s in sources}
    assert "more than 100 bytes" in status["fed"]["error"]
    assert "Could not reach SEC EDGAR (ConnectError)" == status["sec"]["error"]


def test_sources_are_cached_then_kept_labelled_stale(web, clock):
    collect()
    count = len(web.requests)
    clock.advance(news.CACHE_SECONDS - 1)
    collect()
    assert len(web.requests) == count  # all served from cache

    clock.advance(2)
    web.routes["www.coindesk.com"] = lambda r: httpx.Response(500)
    items, sources = collect()
    coindesk = next(s for s in sources if s["id"] == "coindesk")
    assert coindesk["status"] == "stale" and "500" in coindesk["error"]
    assert all(i["stale"] for i in items if i["source"] == "coindesk")

    clock.advance(news.STALE_MAX_SECONDS)
    _, sources = collect()
    assert next(s for s in sources if s["id"] == "coindesk")["status"] == "unavailable"


# ---- calendar ------------------------------------------------------------------------

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def test_meetings_come_from_the_central_bank_calendars():
    events = econ_calendar.meeting_events(NOW.date())
    fomc = [e for e in events if e["agency"] == "Federal Reserve"]
    dec = next(e for e in fomc if e["date"] == "2026-12-09")
    assert dec["title"] == "FOMC meeting: rate decision with economic projections"
    assert dec["status"] == "scheduled" and dec["note"].startswith("Tentative until confirmed")
    assert next(e for e in fomc if e["date"] == "2026-10-28")["status"] == "past"
    assert next(e for e in fomc if e["date"] == "2027-01-27")["tentative"] is True
    ecb = [e for e in events if e["agency"] == "ECB"]
    assert [e["date"] for e in ecb][:2] == ["2026-10-29", "2026-12-17"]
    assert all(e["consensus"] is None for e in events)


def test_bea_times_are_kept_in_utc():
    times = econ_calendar.parse_bea_times({"Gross Domestic Product": {"release_dates": [
        "2026-10-29T12:30:00+00:00", "2026-11-25T08:30:00-05:00", "not a time", "2026-12-01T08:30:00"]}})
    assert times == {"Gross Domestic Product": {"2026-10-29": "2026-10-29T12:30:00Z", "2026-11-25": "2026-11-25T13:30:00Z"}}


def test_calendar_combines_fred_dates_bea_times_and_meetings(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "x" * 32)
    dates = {10: ["2026-10-14", "2026-11-10", "2026-12-10"], 50: ["2026-11-06"], 53: ["2026-10-29", "2026-11-25"], 54: []}
    calls = []

    async def fake_get(path, params):
        calls.append((path, params))
        return {"release_dates": [{"release_id": params["release_id"], "date": d} for d in dates[params["release_id"]]]}

    monkeypatch.setattr(fred, "_get", fake_get)
    body = asyncio.run(econ_calendar.build(14, 60, now=NOW))

    assert calls[0][1]["include_release_dates_with_no_data"] == "true"
    assert calls[0][1]["realtime_start"] == "2026-10-16"
    by = {(e["date"], e["title"]): e for e in body["events"]}
    cpi = by[("2026-11-10", "Consumer Price Index")]
    assert cpi["time_utc"] is None and cpi["status"] == "scheduled"  # BLS: date only, no guessed time
    gdp = by[("2026-11-25", "Gross Domestic Product")]
    assert gdp["time_utc"] == "2026-11-25T13:30:00Z"
    assert by[("2026-10-29", "Gross Domestic Product")]["status"] == "past"
    assert ("2026-10-14", "Consumer Price Index") not in by  # before the window
    assert ("2026-12-09", "FOMC meeting: rate decision with economic projections") in by
    assert [e["date"] for e in body["events"]] == sorted(e["date"] for e in body["events"])
    assert all(e["consensus"] is None for e in body["events"])
    assert body["consensus_note"].startswith("No consensus forecasts")


def test_without_fred_only_meetings_are_shown(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", None)
    body = asyncio.run(econ_calendar.build(14, 60, now=NOW))
    assert {e["kind"] for e in body["events"]} == {"meeting"}
    assert "FRED_API_KEY" in body["notes"][0]


def test_a_bea_outage_leaves_dates_without_times(web, monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "x" * 32)

    async def fake_get(path, params):
        return {"release_dates": [{"date": "2026-11-25"}]}

    monkeypatch.setattr(fred, "_get", fake_get)
    web.routes["apps.bea.gov"] = lambda r: httpx.Response(500)
    body = asyncio.run(econ_calendar.build(14, 60, now=NOW))
    gdp = next(e for e in body["events"] if e["title"] == "Gross Domestic Product")
    assert gdp["time_utc"] is None
    assert any("BEA release times unavailable" in n for n in body["notes"])


# ---- API ----------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_news_endpoint_filters(client):
    body = client.get("/api/news").json()
    assert body["policy"].startswith("Headlines and short snippets only")
    assert body["total"] == 7  # fed 2, ecb 1, bea 1, coindesk 1, sec 2

    crypto = client.get("/api/news", params={"topic": "crypto"}).json()["items"]
    assert {i["source"] for i in crypto} == {"coindesk"}
    eth = client.get("/api/news", params={"instrument": "ETH/USDT"}).json()["items"]
    assert [i["title"] for i in eth] == ["Bitcoin options near expiry as ETH lags"]
    aapl = client.get("/api/news", params={"instrument": "AAPL", "limit": 1}).json()
    assert aapl["count"] == 1 and aapl["total"] == 2
    assert client.get("/api/news", params={"source": "fed"}).json()["total"] == 2


@pytest.mark.parametrize("params", [{"topic": "gossip"}, {"instrument": "TSLA"}, {"source": "reuters"}])
def test_news_endpoint_rejects_unknown_filters(client, params):
    assert client.get("/api/news", params=params).status_code == 400


def test_calendar_endpoint_validates_its_window(client, monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", None)
    assert client.get("/api/calendar", params={"days_ahead": 1000}).status_code == 422
    body = client.get("/api/calendar").json()
    assert body["count"] == len(body["events"])
