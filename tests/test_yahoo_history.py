"""Yahoo FX candles: parsing, caching and the kept copy when Yahoo fails. No network."""
import asyncio

import httpx
import pytest

from backend import config, yahoo_history
from backend.yahoo_history import YahooHistoryError, parse_chart


def chart(times, opens, highs, lows, closes):
    return {"chart": {"result": [{"timestamp": times, "indicators": {"quote": [{
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": [0] * len(times),
    }]}}]}}


BODY = chart([100, 160, 220], [1.10, None, 1.12], [1.11, 1.12, 1.125], [1.09, 1.10, 1.115], [1.105, 1.11, 1.12])


def test_bars_with_a_missing_price_are_skipped():
    candles = parse_chart(BODY)
    assert [c["time"] for c in candles] == [100, 220]
    assert candles[1] == {"time": 220, "open": 1.12, "high": 1.125, "low": 1.115, "close": 1.12, "volume": 0.0}


def test_the_exchange_time_zone_comes_from_the_chart_meta():
    body = {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York"}}]}}
    assert yahoo_history.exchange_timezone(body) == "America/New_York"
    assert yahoo_history.exchange_timezone(BODY) is None
    assert yahoo_history.exchange_timezone({"chart": {"result": None}}) is None


def test_unexpected_shapes_are_errors():
    with pytest.raises(YahooHistoryError):
        parse_chart({"chart": {"result": None}})


@pytest.fixture
def yahoo(monkeypatch):
    yahoo_history.clear_cache()
    clock = {"mono": 1000.0}
    monkeypatch.setattr(yahoo_history, "_monotonic", lambda: clock["mono"])
    monkeypatch.setattr(config, "YAHOO_QUOTE_URL", "https://y.example")
    state = {"status": 200, "body": BODY, "requests": [], "clock": clock}

    def handle(request):
        state["requests"].append(request)
        return httpx.Response(state["status"], json=state["body"])

    monkeypatch.setattr(yahoo_history, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    yield state
    yahoo_history.clear_cache()


def fetch(interval="1m", limit=50):
    return asyncio.run(yahoo_history.fetch_candle_series("EUR/USD", interval, limit))


def test_fetch_asks_for_the_right_symbol_interval_and_range(yahoo):
    candles, meta = fetch("1h")
    request = yahoo["requests"][0]
    assert request.url.path in {"/v8/finance/chart/EURUSD%3DX", "/v8/finance/chart/EURUSD=X"}
    assert request.url.params["interval"] == "60m" and request.url.params["range"] == "2y"
    assert len(candles) == 2 and meta.provider == "yahoo" and meta.status == "historical"


def test_responses_are_cached_then_refreshed(yahoo):
    fetch()
    fetch()
    assert len(yahoo["requests"]) == 1
    yahoo["clock"]["mono"] += yahoo_history.CACHE_SECONDS + 1
    fetch()
    assert len(yahoo["requests"]) == 2


def test_a_failure_serves_the_kept_copy_labelled_cached(yahoo):
    fetch()
    yahoo["clock"]["mono"] += yahoo_history.CACHE_SECONDS + 1
    yahoo["status"] = 429
    candles, meta = fetch()
    assert len(candles) == 2 and meta.status == "cached" and "429" in meta.notes[0]

    yahoo["clock"]["mono"] += yahoo_history.STALE_MAX_SECONDS + 1
    with pytest.raises(YahooHistoryError, match="429"):
        fetch()


def test_limit_keeps_the_newest_bars(yahoo):
    candles, _ = fetch(limit=1)
    assert [c["time"] for c in candles] == [220]
