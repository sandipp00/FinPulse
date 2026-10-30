"""The Yahoo quote poller: ticks, market sessions, delays and failures.

Yahoo is replaced by an httpx mock transport, so no network is used.
"""
import asyncio
from datetime import datetime, timedelta, timezone

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


def test_no_bar_yet_shows_the_last_close_closed_or_delayed():
    empty = {"timestamp": [], "close": [], "previousClose": 17.2}
    closed = build_tick("^VIX", empty, US, NOW)
    assert closed["price"] == 17.2 and closed["market_open"] is False and closed["time"] is None
    assert closed["delayed"] is False
    just_opened = build_tick("^VIX", empty, NSE, NOW)  # open, but Yahoo has no bar yet
    assert just_opened["price"] == 17.2 and just_opened["delayed"] is True
    assert build_tick("^VIX", empty, None, NOW) is None  # hours unknown: nothing is shown


def test_closed_markets_are_fetched_every_five_minutes_but_re_sent_every_round(monkeypatch):
    clock = {"wall": NOW}
    monkeypatch.setattr(quotes_live, "_wall", lambda: clock["wall"])
    asked = []

    def handle(request):
        if request.url.path.startswith("/v8/finance/chart/"):
            session = NSE if "NSEI" in request.url.path else US  # NIFTY open, AAPL closed
            return httpx.Response(200, json={"chart": {"result": [{"meta": {"currentTradingPeriod": {
                "regular": {"start": session[0], "end": session[1]}}}}]}})
        names = request.url.params["symbols"].split(",")
        asked.append(names)
        return httpx.Response(200, json={name: spark(100.0, previous=99.0) for name in names})

    quotes = poller(handle, symbols=("^NSEI", "AAPL"))
    asyncio.run(quotes.poll())
    clock["wall"] += 15
    queue = quotes.subscribe()
    asyncio.run(quotes.poll())

    assert asked == [["^NSEI", "AAPL"], ["^NSEI"]]  # AAPL's market is closed: not asked again yet
    resent = [m for m in (queue.get_nowait() for _ in range(queue.qsize())) if m.get("symbol") == "AAPL"]
    assert resent and resent[0]["received_at"] == NOW + 15  # but its last price is re-sent, fresh

    clock["wall"] += quotes_live.CLOSED_POLL_SECONDS
    asyncio.run(quotes.poll())
    assert asked[-1] == ["^NSEI", "AAPL"]


# ---- previous close from daily bars ----------------------------------------------------

def test_previous_close_is_the_session_before_the_newest_bars_local_day():
    # NIFTY on Oct 30 (IST, +5:30). Yahoo's spark previousClose is a day too old (Oct 28).
    daily = quotes_live.DailyCloses(19800, [("2026-10-28", 22698.8), ("2026-10-29", 22936.75), ("2026-10-30", 23030.0)])
    tick = build_tick("^NSEI", spark(23096.8, previous=22698.8), NSE, NOW, daily)
    assert tick["previous_close"] == 22936.75
    assert tick["change_pct_24h"] == pytest.approx((23096.8 / 22936.75 - 1) * 100, abs=1e-4)


def test_without_daily_bars_the_spark_previous_close_is_kept():
    assert build_tick("^NSEI", spark(23096.8, previous=22698.8), NSE, NOW)["previous_close"] == 22698.8


def test_daily_bars_are_dated_by_the_exchanges_local_day():
    tokyo_midnight = 1_793_286_000  # 2026-10-29 15:00 UTC = Oct 30 00:00 JST
    body = {"chart": {"result": [{"meta": {"gmtoffset": 32400}, "timestamp": [tokyo_midnight - 86400, tokyo_midnight],
                                  "indicators": {"quote": [{"close": [64659.47, None]}]}}]}}
    daily = quotes_live.parse_daily(body)
    assert daily.closes == [("2026-10-29", 64659.47)]  # the empty bar is skipped


def test_no_bar_today_uses_the_last_daily_close_and_the_one_before():
    daily = quotes_live.DailyCloses(-14400, [("2026-10-28", 7743.98), ("2026-10-29", 7720.39)])
    tick = build_tick("^GSPC", {"timestamp": [], "close": [], "previousClose": 1.0}, US, NOW, daily)
    assert tick["price"] == 7720.39 and tick["previous_close"] == 7743.98 and tick["market_open"] is False


# ---- Tencent for Shanghai, Shenzhen and Hang Seng -----------------------------------------

from backend import tencent_quotes  # noqa: E402

TENCENT = (
    'v_sh000001="1~name~000001~3599.02~3651.43~3640.00~' + "~".join(["0"] * 24) + '~20261030102001~-52.41~-1.44";\n'
    'v_hkHSI="100~name~HSI~23294.42~22958.65~23000~' + "~".join(["0"] * 24) + '~2026/10/30 10:20:30~0~0";\n'
    'v_sz399001="1~broken";\n'
)


def test_tencent_quotes_parse_price_previous_close_and_china_time():
    quotes = tencent_quotes.parse(TENCENT)
    assert set(quotes) == {"sh000001", "hkHSI"}  # the broken line is skipped
    assert quotes["sh000001"]["price"] == 3599.02 and quotes["sh000001"]["previous_close"] == 3651.43
    assert quotes["sh000001"]["time"] == datetime(2026, 10, 30, 2, 20, 1, tzinfo=timezone.utc).timestamp()
    assert quotes["hkHSI"]["time"] == datetime(2026, 10, 30, 2, 20, 30, tzinfo=timezone.utc).timestamp()


def test_a_newer_tencent_quote_replaces_yahoos_and_keeps_honest_freshness():
    yahoo_tick = build_tick("000001.SS", spark(3590.0, minutes_ago=16, previous=3681.47), NSE, NOW)
    assert yahoo_tick["delayed"] is True
    fresh = {"price": 3599.02, "previous_close": 3651.43, "time": NOW - 20}
    tick = tencent_quotes.apply(yahoo_tick, fresh, quotes_live.DELAYED_AFTER_SECONDS, NOW)
    assert tick["provider"] == "tencent" and tick["price"] == 3599.02 and tick["delayed"] is False
    assert tick["change_pct_24h"] == pytest.approx((3599.02 / 3651.43 - 1) * 100, abs=1e-4)
    stale = {"price": 3599.02, "previous_close": 3651.43, "time": NOW - 900}  # Tencent delayed too
    assert tencent_quotes.apply(yahoo_tick, stale, quotes_live.DELAYED_AFTER_SECONDS, NOW)["delayed"] is True


def test_the_poller_prefers_tencent_only_when_newer_and_survives_its_failure(monkeypatch):
    monkeypatch.setattr(config, "TENCENT_QUOTES_ENABLED", True)
    monkeypatch.setattr(config, "TENCENT_QUOTE_URL", "https://t.example")
    state = {"tencent": "ok"}

    def handle(request):
        if request.url.host == "t.example":
            if state["tencent"] == "down":
                return httpx.Response(503)
            body = (f'v_hkHSI="100~n~HSI~23300.00~22958.65~0~' + "~".join(["0"] * 24)
                    + f'~{datetime.fromtimestamp(NOW - 10, timezone(timedelta(hours=8))).strftime("%Y/%m/%d %H:%M:%S")}~0";')
            return httpx.Response(200, content=body.encode("gbk"))
        if request.url.path.startswith("/v8/finance/chart/"):
            return httpx.Response(200, json={"chart": {"result": [{"meta": {"currentTradingPeriod": {
                "regular": {"start": NSE[0], "end": NSE[1]}}}}]}})
        return httpx.Response(200, json={"^HSI": spark(23290.0, minutes_ago=16, previous=23094.8)})

    quotes = poller(handle, symbols=("^HSI",))
    asyncio.run(quotes.poll())
    assert quotes.latest["^HSI"]["provider"] == "tencent" and quotes.latest["^HSI"]["price"] == 23300.0

    state["tencent"] = "down"
    quotes._fetched_at.clear()
    asyncio.run(quotes.poll())
    assert quotes.latest["^HSI"]["provider"] == "yahoo"  # Tencent failing: Yahoo stays
