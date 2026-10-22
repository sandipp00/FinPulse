import asyncio

import pytest

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
