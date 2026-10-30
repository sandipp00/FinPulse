"""The Yahoo quote poller: ticks, market sessions, delays and failures.

Yahoo is replaced by an httpx mock transport, so no network is used.
"""
import asyncio

import httpx
import pytest

from backend import config, market_service, quotes_live
from backend.quotes_live import YahooQuotes, build_tick, parse_session

NOW = 1_793_335_200.0  # 2026-10-30 04:40 UTC: NSE open, US closed
NSE = (1_793_331_900, 1_793_354_400)  # 09:15-15:30 IST
US = (1_793_367_000, 1_793_390_400)  # later today, not yet open


def spark(price, minutes_ago=1, previous=22936.75):
    bar = int(NOW) - minutes_ago * 60
    return {"timestamp": [bar - 60, bar], "close": [price - 1, price], "previousClose": previous}


def test_an_open_market_with_a_fresh_bar_is_live():
    tick = build_tick("^NSEI", spark(22930.45), NSE, NOW)

    assert tick["price"] == 22930.45
    assert tick["asset_class"] == "index" and tick["market"] == "quotes" and tick["provider"] == "yahoo"
    assert tick["market_open"] is True and tick["delayed"] is False
    assert tick["change_pct_24h"] == pytest.approx(-0.0275, abs=1e-4)
    assert tick["change_window"] == "1d"
    assert tick["time"] == (int(NOW) - 60) * 1000


def test_an_old_bar_while_open_is_delayed():
    assert build_tick("^NSEI", spark(22930.45, minutes_ago=10), NSE, NOW)["delayed"] is True


def test_a_closed_market_keeps_the_last_price_and_is_not_delayed():
    tick = build_tick("AAPL", spark(348.91, minutes_ago=600, previous=343.83), US, NOW)
    assert tick["market_open"] is False and tick["delayed"] is False
    assert tick["price"] == 348.91
    assert tick["asset_class"] == "stock"


def test_an_unknown_session_is_judged_by_age_only():
    tick = build_tick("EUR/USD", spark(1.1193, minutes_ago=10, previous=1.1181), None, NOW)
    assert tick["market_open"] is None and tick["delayed"] is True
    assert tick["asset_class"] == "fx"


def test_missing_prices_are_skipped_not_invented():
    assert build_tick("AAPL", {"timestamp": [1, 2], "close": [None, None]}, US, NOW) is None
    series = {"timestamp": [int(NOW) - 120, int(NOW) - 60], "close": [348.0, None], "previousClose": 343.83}
    assert build_tick("AAPL", series, US, NOW)["price"] == 348.0  # newest bar with a price


def test_session_parsing():
    body = {"chart": {"result": [{"meta": {"currentTradingPeriod": {"regular": {"start": NSE[0], "end": NSE[1]}}}}]}}
    assert parse_session(body) == NSE
    assert parse_session({"chart": {"result": None}}) is None


def poller(handler, symbols=("^NSEI", "USD/INR")):
    quotes = YahooQuotes(list(symbols))
    quotes._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://y.example")
    return quotes


def yahoo(request: httpx.Request):
    if request.url.path.startswith("/v8/finance/chart/"):
        return httpx.Response(200, json={"chart": {"result": [{"meta": {"currentTradingPeriod": {
            "regular": {"start": NSE[0], "end": NSE[1]}}}}]}})
    assert request.url.params["symbols"] == "^NSEI,INR=X"  # one batch request, Yahoo's FX symbol
    return httpx.Response(200, json={"^NSEI": spark(22930.45), "INR=X": spark(95.23, previous=95.21)})


@pytest.fixture(autouse=True)
def clocks(monkeypatch):
    monkeypatch.setattr(quotes_live, "_wall", lambda: NOW)
    monkeypatch.setattr(config, "YAHOO_QUOTE_URL", "https://y.example")


def test_a_poll_publishes_one_tick_per_symbol_and_connects():
    quotes = poller(yahoo)
    queue = quotes.subscribe()

    asyncio.run(quotes.poll())

    messages = [queue.get_nowait() for _ in range(queue.qsize())]
    ticks = {m["symbol"]: m for m in messages if m["type"] == "tick"}
    assert set(ticks) == {"^NSEI", "USD/INR"}
    assert ticks["USD/INR"]["price"] == 95.23 and ticks["USD/INR"]["asset_class"] == "fx"
    assert {"type": "status", "market": "quotes", "connected": True} in messages
    assert quotes.connected and set(quotes.latest) == {"^NSEI", "USD/INR"}


def test_a_failed_poll_raises_and_publishes_nothing():
    quotes = poller(lambda request: httpx.Response(429, json={}))
    queue = quotes.subscribe()

    with pytest.raises(RuntimeError, match="429"):
        asyncio.run(quotes.poll())
    assert queue.empty() and quotes.latest == {}


def test_a_failed_session_lookup_does_not_stop_prices(monkeypatch):
    def flaky(request):
        if request.url.path.startswith("/v8/finance/chart/"):
            return httpx.Response(500)
        return yahoo(request)

    quotes = poller(flaky)
    asyncio.run(quotes.poll())

    assert quotes.latest["^NSEI"]["market_open"] is None  # session unknown, price still shown


# ---- quote records -----------------------------------------------------------------

def test_yahoo_ticks_become_real_time_delayed_or_closed_records():
    def record(**tick):
        base = build_tick("^NSEI", spark(22930.45), NSE, NOW)
        return market_service.live_record("^NSEI", {**base, **tick}, True, NOW)

    live = record()
    assert live.status == "real_time" and live.provider == "yahoo" and live.interval == "1m"
    assert live.asset_class == "index" and live.unit == "index points" and live.change_window == "1d"
    assert record(delayed=True).status == "delayed"
    closed = record(market_open=False)
    assert closed.status == "historical" and "Market closed" in closed.error


def test_oil_is_quoted_per_barrel():
    assert market_service.unit_for("CL/USDT", "commodity") == "per barrel"
    assert market_service.unit_for("XAU/USDT", "commodity") == "per troy ounce"


def test_more_than_twenty_symbols_are_split_into_batches():
    symbols = [f"S{i}" for i in range(23)]
    sizes = []

    def handle(request):
        if request.url.path.startswith("/v8/finance/chart/"):
            return httpx.Response(200, json={"chart": {"result": [{"meta": {"currentTradingPeriod": {
                "regular": {"start": NSE[0], "end": NSE[1]}}}}]}})
        names = request.url.params["symbols"].split(",")
        sizes.append(len(names))
        if len(names) > quotes_live.SPARK_BATCH:
            return httpx.Response(400, json={})  # what Yahoo does
        return httpx.Response(200, json={name: spark(100.0, previous=99.0) for name in names})

    quotes = poller(handle, symbols=symbols)
    asyncio.run(quotes.poll())

    assert sizes == [20, 3]
    assert set(quotes.latest) == set(symbols)
