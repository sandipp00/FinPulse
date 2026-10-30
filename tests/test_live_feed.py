import asyncio

import pytest

from backend import live
from backend.live import LiveFeed, to_stream_name

TICKER = {
    "e": "24hrTicker", "E": 1700000000000, "s": "BTCUSDT",
    "c": "65000.10", "P": "-1.25", "o": "65820.00",
    "h": "66000.00", "l": "64500.00", "v": "1234.5", "q": "80000000.0",
}


def kline(closed):
    return {
        "e": "kline", "s": "ETHUSDT",
        "k": {
            "t": 1700000060000, "x": closed,
            "o": "2400.0", "h": "2410.0", "l": "2395.0",
            "c": "2405.5", "v": "50.2",
        },
    }


@pytest.fixture
def feed():
    return LiveFeed(["BTC/USDT", "ETH/USDT"], ["wss://example.invalid"])


def test_stream_name():
    assert to_stream_name("BTC/USDT") == "btcusdt"


def test_stream_url_subscribes_ticker_and_kline_per_symbol(feed):
    url = feed._stream_url("wss://example.invalid/")

    assert url.startswith("wss://example.invalid/stream?streams=")
    for stream in ("btcusdt@ticker", "btcusdt@kline_1m",
                   "ethusdt@ticker", "ethusdt@kline_1m"):
        assert stream in url


def test_ticker_updates_latest_and_broadcasts(feed):
    queue = feed.subscribe()
    feed._handle_ticker(TICKER)

    tick = feed.latest["BTC/USDT"]
    assert tick["price"] == pytest.approx(65000.10)
    assert tick["change_pct_24h"] == pytest.approx(-1.25)
    assert queue.get_nowait() == {"type": "tick", **tick}


def test_unknown_symbol_is_ignored(feed):
    feed._handle_ticker({**TICKER, "s": "DOGEUSDT"})

    assert feed.latest == {}


def test_slow_subscriber_drops_oldest_instead_of_blocking(feed):
    queue = feed.subscribe()
    for index in range(queue.maxsize):
        queue.put_nowait({"n": index})

    feed._broadcast({"n": "newest"})

    assert queue.qsize() == queue.maxsize
    assert queue.get_nowait() == {"n": 1}  # oldest ({"n": 0}) was dropped


def test_only_closed_candles_are_buffered(feed):
    asyncio.run(feed._handle_kline(kline(closed=False)))
    assert feed._candle_buffer == []

    asyncio.run(feed._handle_kline(kline(closed=True)))
    # Buffer is flushed once it holds one candle per symbol (2), so it
    # stays queued here with a single candle.
    assert feed._candle_buffer == [
        (1700000060000, "ETH/USDT", "1m", 2400.0, 2410.0, 2395.0, 2405.5, 50.2)
    ]


def test_status_reports_disconnected_before_start(feed):
    status = feed.status()

    assert status["connected"] is False
    assert status["last_message_age_seconds"] is None
    assert status["symbols"] == ["BTC/USDT", "ETH/USDT"]


class FakeUpstream:
    """Hands out queued raw messages, then ends the connection."""

    def __init__(self, messages):
        self.messages = list(messages)

    async def recv(self):
        if not self.messages:
            raise ConnectionError("closed")
        return self.messages.pop(0)


def test_malformed_messages_are_dropped_without_dropping_the_connection(feed):
    import json

    good = json.dumps({"data": TICKER})
    upstream = FakeUpstream([
        "not json",
        json.dumps(["a", "list"]),
        json.dumps({"data": {**TICKER, "c": "abc"}}),
        json.dumps({"data": {**TICKER, "c": "-5"}}),
        json.dumps({"data": {**TICKER, "c": "NaN"}}),
        json.dumps({"data": {"e": "24hrTicker", "s": "BTCUSDT"}}),  # no price at all
        good,
    ])

    with pytest.raises(ConnectionError):
        asyncio.run(feed._consume(upstream))

    # The good message after six bad ones still got through.
    assert feed.latest["BTC/USDT"]["price"] == pytest.approx(65000.10)
    assert feed.rejected_messages == 6
    assert feed.status()["rejected_messages"] == 6


# ---- live gold and silver (Binance futures) ------------------------------------

def test_metal_ticks_and_status_say_which_market_they_belong_to():
    metals = LiveFeed(["XAU/USDT"], ["wss://example.invalid/market"], market="metals", asset_class="commodity")
    queue = metals.subscribe()

    metals._handle_ticker({**TICKER, "s": "XAUUSDT", "c": "4000.55"})

    tick = queue.get_nowait()
    assert tick["symbol"] == "XAU/USDT" and tick["asset_class"] == "commodity"
    assert tick["price"] == pytest.approx(4000.55)
    assert metals._status_message() == {"type": "status", "market": "metals", "connected": False}
    assert metals._stream_url("wss://example.invalid/market") == (
        "wss://example.invalid/market/stream?streams=xauusdt@ticker/xauusdt@kline_1m"
    )


def test_one_client_queue_receives_ticks_from_both_feeds(monkeypatch):
    crypto = LiveFeed(["BTC/USDT"], ["wss://example.invalid"])
    metals = LiveFeed(["XAU/USDT"], ["wss://example.invalid/market"], market="metals", asset_class="commodity")
    monkeypatch.setattr(live, "FEEDS", [crypto, metals])

    queue = live.subscribe_all()
    crypto._handle_ticker(TICKER)
    metals._handle_ticker({**TICKER, "s": "XAUUSDT", "c": "4000.55"})

    assert [queue.get_nowait()["symbol"] for _ in range(2)] == ["BTC/USDT", "XAU/USDT"]
    assert set(live.all_latest()) == {"BTC/USDT", "XAU/USDT"}
    assert live.all_symbols() == ["BTC/USDT", "XAU/USDT"]

    metals.connected = True
    assert live.connected_for("XAU/USDT") is True
    assert live.connected_for("BTC/USDT") is False
    assert live.markets() == {"crypto": False, "metals": True}

    live.unsubscribe_all(queue)
    assert not crypto._subscribers and not metals._subscribers
