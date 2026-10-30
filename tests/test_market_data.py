"""Market-data foundation: kline validation, provider failures, caching, quotes.

Every provider response is mocked (httpx.MockTransport), so these tests never
touch the network.
"""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import candles as candle_source, config, main, market_service
from backend.schemas.market import MarketRecord

A = "https://a.example"
B = "https://b.example"

KLINES = [
    [1700000000000, "100.0", "105.0", "99.0", "104.0", "12.5", 1700000059999],
    [1700000060000, "104.0", "106.0", "103.0", "105.5", "8.0", 1700000119999],
]


class Clock:
    """Stands in for time.monotonic and time.time inside backend.candles."""

    def __init__(self):
        self.mono = 1000.0
        self.wall = 1_800_000_000.0

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(candle_source, "_monotonic", lambda: clock.mono)
    monkeypatch.setattr(candle_source, "_wall", lambda: clock.wall)
    return clock


@pytest.fixture(autouse=True)
def provider(monkeypatch, clock):
    """Two fake Binance endpoints. Set `provider.routes[host] = handler` per test."""
    candle_source._cache.clear()
    candle_source._blocked_until.clear()
    monkeypatch.setattr(config, "BINANCE_REST_URLS", [A, B])

    class Provider:
        routes = {}
        calls = []

    def handle(request: httpx.Request):
        host = f"{request.url.scheme}://{request.url.host}"
        Provider.calls.append(host)
        handler = Provider.routes.get(host)
        if handler is None:
            raise httpx.ConnectError("no route", request=request)
        return handler(request)

    monkeypatch.setattr(
        candle_source, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    yield Provider
    candle_source._cache.clear()
    candle_source._blocked_until.clear()


def ok(rows=KLINES):
    return lambda _request: httpx.Response(200, json=rows)


def fetch(allow_stale=False, symbol="BTC/USDT"):
    return asyncio.run(candle_source.fetch_candle_series(symbol, "1h", 50, allow_stale=allow_stale))


# ---- validation --------------------------------------------------------

def test_valid_klines_parse():
    candles = candle_source.parse_klines(KLINES)
    assert candles[0] == {"time": 1700000000, "open": 100.0, "high": 105.0,
                          "low": 99.0, "close": 104.0, "volume": 12.5}


def test_an_empty_list_is_valid():
    assert candle_source.parse_klines([]) == []


@pytest.mark.parametrize("rows, reason", [
    ({"code": -1121, "msg": "Invalid symbol."}, "expected a list"),
    ([[1700000000000, "1", "2"]], "at least 6 fields"),
    ([["1700000000000", "100", "105", "99", "104", "1"]], "open time"),
    ([[True, "100", "105", "99", "104", "1"]], "open time"),
    ([[1700000000000, "abc", "105", "99", "104", "1"]], "open is not a number"),
    ([[1700000000000, None, "105", "99", "104", "1"]], "open is not a number"),
    ([[1700000000000, "NaN", "105", "99", "104", "1"]], "not finite"),
    ([[1700000000000, "100", "inf", "99", "104", "1"]], "not finite"),
    ([[1700000000000, "0", "105", "0", "104", "1"]], "positive"),
    ([[1700000000000, "100", "105", "99", "104", "-1"]], "volume is negative"),
    ([[1700000000000, "100", "98", "99", "104", "1"]], "low-high range"),
    ([[1700000000000, "100", "105", "101", "104", "1"]], "low-high range"),
    ([KLINES[1], KLINES[0]], "not increasing"),
    ([KLINES[0], KLINES[0]], "not increasing"),
])
def test_malformed_klines_are_rejected(rows, reason):
    with pytest.raises(candle_source.MalformedResponse, match=reason):
        candle_source.parse_klines(rows)


@pytest.mark.parametrize("symbol", ["btcusdt", "BTC-USDT", "BTC/", "/USDT", "BTC/USDT; DROP", "B/USDT"])
def test_bad_symbols_are_refused_before_any_request(provider, symbol):
    provider.routes[A] = ok()
    with pytest.raises(ValueError, match="Invalid symbol"):
        fetch(symbol=symbol)
    assert provider.calls == []


# ---- provider responses ------------------------------------------------

def test_a_valid_response_carries_source_metadata(provider, clock):
    provider.routes[A] = ok()

    series = fetch()

    assert len(series.candles) == 2
    meta = series.meta
    assert meta.provider == "binance"
    assert meta.endpoint == "a.example"
    assert meta.status == "historical"
    assert meta.retrieved_at.timestamp() == clock.wall
    assert meta.source_timestamp.timestamp() == 1700000060  # newest candle's open time
    assert meta.cache_age_seconds == 0


def test_a_malformed_response_falls_through_to_the_next_endpoint(provider):
    provider.routes[A] = ok([[1, "x"]])
    provider.routes[B] = ok()

    series = fetch()

    assert series.meta.endpoint == "b.example"
    assert provider.calls == [A, B]


def test_a_non_json_body_counts_as_a_failure(provider):
    provider.routes[A] = lambda _r: httpx.Response(200, text="<html>maintenance</html>")
    provider.routes[B] = ok()

    assert fetch().meta.endpoint == "b.example"


def test_server_errors_and_timeouts_try_the_next_endpoint(provider):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    provider.routes[A] = timeout
    provider.routes[B] = lambda _r: httpx.Response(500)

    with pytest.raises(candle_source.CandleSourceError) as raised:
        fetch()

    message = str(raised.value)
    assert "a.example: ReadTimeout" in message
    assert "b.example: HTTPStatusError" in message
    assert raised.value.retry_after is None


def test_a_rate_limited_endpoint_is_skipped_until_retry_after(provider, clock):
    provider.routes[A] = lambda _r: httpx.Response(429, headers={"Retry-After": "30"})
    provider.routes[B] = ok()

    assert fetch().meta.endpoint == "b.example"

    candle_source._cache.clear()
    provider.calls.clear()
    clock.advance(10)
    assert fetch().meta.endpoint == "b.example"
    assert provider.calls == [B]  # A is not asked again while blocked

    candle_source._cache.clear()
    provider.calls.clear()
    clock.advance(25)
    provider.routes[A] = ok()
    assert fetch().meta.endpoint == "a.example"


@pytest.mark.parametrize("headers, expected", [
    ({"Retry-After": "12"}, 12),
    ({}, candle_source.DEFAULT_RETRY_AFTER_SECONDS),
    ({"Retry-After": "soon"}, candle_source.DEFAULT_RETRY_AFTER_SECONDS),
    ({"Retry-After": "-5"}, candle_source.DEFAULT_RETRY_AFTER_SECONDS),
    ({"Retry-After": "99999"}, candle_source.MAX_RETRY_AFTER_SECONDS),
])
def test_retry_after_is_parsed_conservatively(provider, headers, expected):
    provider.routes[A] = lambda _r: httpx.Response(418, headers=headers)
    provider.routes[B] = lambda _r: httpx.Response(429, headers=headers)

    with pytest.raises(candle_source.CandleSourceError) as raised:
        fetch()

    assert raised.value.retry_after == expected


# ---- caching -----------------------------------------------------------

def test_a_repeat_request_inside_the_cache_window_is_not_sent(provider, clock):
    provider.routes[A] = ok()
    fetch()
    clock.advance(3)

    series = fetch()

    assert provider.calls == [A]
    assert series.meta.status == "historical"
    assert series.meta.cache_age_seconds == 3


def test_a_failing_exchange_serves_the_last_response_labelled_cached(provider, clock):
    provider.routes[A] = ok()
    fetch()
    provider.routes.clear()
    clock.advance(120)

    series = fetch(allow_stale=True)

    assert series.meta.status == "cached"
    assert series.meta.cache_age_seconds == 120
    assert "Exchange unavailable" in series.meta.notes[0]
    assert series.candles == candle_source.parse_klines(KLINES)


def test_a_cached_response_is_never_served_past_the_limit(provider, clock):
    provider.routes[A] = ok()
    fetch()
    provider.routes.clear()
    clock.advance(candle_source.STALE_MAX_SECONDS + 1)

    with pytest.raises(candle_source.CandleSourceError):
        fetch(allow_stale=True)


def test_signals_and_backtests_never_get_a_cached_response(provider, clock):
    provider.routes[A] = ok()
    fetch()
    provider.routes.clear()
    clock.advance(60)

    with pytest.raises(candle_source.CandleSourceError):
        asyncio.run(candle_source.fetch_candles("BTC/USDT", "1h", 50))


# ---- API ---------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_candles_endpoint_includes_meta(client, provider):
    provider.routes[A] = ok()

    body = client.get("/api/candles", params={"symbol": "BTC/USDT", "interval": "1h", "limit": 50}).json()

    assert body["count"] == 2
    assert body["meta"]["provider"] == "binance"
    assert body["meta"]["status"] == "historical"
    assert body["meta"]["source_timestamp"].startswith("2023-11-14T22:14:20")


def test_candles_endpoint_labels_a_cached_response(client, provider, clock):
    provider.routes[A] = ok()
    client.get("/api/candles", params={"symbol": "BTC/USDT", "limit": 50})
    provider.routes.clear()
    clock.advance(30)

    body = client.get("/api/candles", params={"symbol": "BTC/USDT", "limit": 50}).json()

    assert body["meta"]["status"] == "cached"
    assert body["meta"]["cache_age_seconds"] == 30


def test_a_malformed_provider_response_is_a_502_not_a_crash(client, provider):
    provider.routes[A] = ok([[1700000000000, "100", "98", "99", "104", "1"]])
    provider.routes[B] = ok({"unexpected": True})

    response = client.get("/api/candles", params={"symbol": "ETH/USDT"})

    assert response.status_code == 502
    assert "malformed response" in response.json()["detail"]


def test_rate_limiting_everywhere_is_a_503_with_retry_after(client, provider):
    provider.routes[A] = lambda _r: httpx.Response(429, headers={"Retry-After": "20"})
    provider.routes[B] = lambda _r: httpx.Response(429, headers={"Retry-After": "45"})

    response = client.get("/api/candles", params={"symbol": "ETH/USDT"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "20"


def test_signals_report_rate_limiting_as_503(client, provider):
    provider.routes[A] = lambda _r: httpx.Response(429, headers={"Retry-After": "20"})
    provider.routes[B] = lambda _r: httpx.Response(429, headers={"Retry-After": "20"})

    response = client.get("/api/signals", params={"interval": "1d", "symbol": "BTC/USDT"})

    assert response.status_code == 503


# ---- normalized quotes -------------------------------------------------

NOW = 1_800_000_000.0

STORED = [
    {"symbol": "AAPL", "asset_type": "stock", "latest_price": 230.5,
     "latest_timestamp": "2026-10-14 00:00:00+00:00", "daily_change_pct": 1.2},
    {"symbol": "^NSEI", "asset_type": "index", "latest_price": 22622.7,
     "latest_timestamp": "2026-10-14 00:00:00+00:00", "daily_change_pct": -0.4},
    {"symbol": "BTC/USDT", "asset_type": "crypto", "latest_price": 82268.6,
     "latest_timestamp": "2026-10-14 00:00:00+00:00", "daily_change_pct": 0.5},
    {"symbol": "XYZ", "asset_type": "stock", "latest_price": None, "latest_timestamp": None},
]


def tick(symbol="BTC/USDT", age=1.0, price=81000.0):
    return {"symbol": symbol, "price": price, "change_pct_24h": 0.6,
            "time": int((NOW - age) * 1000), "received_at": NOW - age}


def quotes(ticks, connected=True, live=("BTC/USDT", "ETH/USDT")):
    return {q.symbol: q for q in market_service.build_quotes(list(live), ticks, connected, STORED, now=NOW)}


def test_a_fresh_tick_is_real_time_with_its_timestamps():
    btc = quotes({"BTC/USDT": tick()})["BTC/USDT"]

    assert btc.status == "real_time"
    assert btc.provider == "binance"
    assert btc.price == 81000.0
    assert btc.currency == "USDT"  # quoted in the stablecoin, not USD
    assert btc.change_window == "24h"
    assert btc.source_timestamp.timestamp() == pytest.approx(NOW - 1)
    assert btc.retrieved_at.timestamp() == pytest.approx(NOW - 1)
    assert btc.error is None


def test_an_old_tick_or_a_dropped_feed_is_stale():
    old = quotes({"BTC/USDT": tick(age=31)})["BTC/USDT"]
    assert old.status == "stale"
    assert "No update" in old.error

    dropped = quotes({"BTC/USDT": tick()}, connected=False)["BTC/USDT"]
    assert dropped.status == "stale"
    assert dropped.error == "Live feed disconnected"


def test_a_live_symbol_without_a_tick_falls_back_to_stored_or_unavailable():
    records = quotes({})

    assert records["BTC/USDT"].status == "historical"
    assert records["BTC/USDT"].provider == "database"
    assert records["BTC/USDT"].error == "No live tick received yet"

    assert records["ETH/USDT"].status == "unavailable"
    assert records["ETH/USDT"].price is None


def test_stored_instruments_are_historical_with_known_currency_or_none():
    records = quotes({})

    assert records["AAPL"].status == "historical"
    assert records["AAPL"].currency == "USD"
    assert records["AAPL"].interval == "1d"
    assert records["AAPL"].source_timestamp.isoformat() == "2026-10-14T00:00:00+00:00"
    assert records["^NSEI"].currency == "INR"
    assert records["^NSEI"].unit == "index points"

    assert records["XYZ"].status == "unavailable"
    assert records["XYZ"].currency is None  # unknown, not guessed


def test_every_record_validates_against_the_schema():
    for record in quotes({"BTC/USDT": tick()}).values():
        MarketRecord.model_validate(record.model_dump())


def test_quotes_endpoint_with_no_stored_history_and_no_feed(client, monkeypatch):
    monkeypatch.setattr(main.feed, "latest", {})
    monkeypatch.setattr(main.feed, "connected", False)

    body = client.get("/api/market/quotes").json()

    assert body["count"] == len(config.LIVE_SYMBOLS)
    assert {q["status"] for q in body["quotes"]} == {"unavailable"}


def test_the_sp500_is_quoted_in_usd_index_points():
    record = market_service.stored_record({
        "symbol": "^GSPC", "asset_type": "index", "latest_price": 7743.98,
        "latest_timestamp": "2026-10-28 00:00:00+00:00", "daily_change_pct": 0.4,
    })
    assert record.currency == "USD"
    assert record.unit == "index points"
    assert record.status == "historical"


@pytest.mark.parametrize("symbol, price", [("GC=F", 4051.6), ("SI=F", 53.457)])
def test_gold_and_silver_are_commodities_in_usd_per_troy_ounce(symbol, price):
    record = market_service.stored_record({
        "symbol": symbol, "asset_type": "commodity", "latest_price": price,
        "latest_timestamp": "2026-10-28 00:00:00+00:00", "daily_change_pct": -0.6,
    })
    assert record.instrument_id == f"commodity:{symbol}"
    assert record.asset_class == "commodity"
    assert record.currency == "USD"
    assert record.unit == "per troy ounce"
    assert record.status == "historical"
