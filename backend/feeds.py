"""Every live price source behind one set of helpers for the socket and quotes.

Binance crypto (`live.feed`), Binance TradFi futures (`live.tradfi_feed`) and the
Yahoo quote poller (`quotes_live`) run independently. Each tick and status message
names its market, so one source failing does not mark the others offline.
"""
import asyncio

from backend import config
from backend.live import SUBSCRIBER_QUEUE_SIZE, feed, tradfi_feed
from backend.quotes_live import YahooQuotes

yahoo_quotes = YahooQuotes(config.YAHOO_LIVE_SYMBOLS)
FEEDS = [f for f in (feed, tradfi_feed, yahoo_quotes) if f.symbols]


def all_latest() -> dict[str, dict]:
    return {s: t for f in FEEDS for s, t in f.latest.items()}


def all_symbols() -> list[str]:
    return [s for f in FEEDS for s in f.symbols]


def connected_for(symbol: str) -> bool:
    return any(f.connected for f in FEEDS if symbol in f.symbols)


def markets() -> dict[str, bool]:
    return {f.market: f.connected for f in FEEDS}


def subscribe_all() -> asyncio.Queue:
    """One queue fed by every source, so a client gets all ticks in one stream."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
    for f in FEEDS:
        f._subscribers.add(queue)
    return queue


def unsubscribe_all(queue: asyncio.Queue) -> None:
    for f in FEEDS:
        f.unsubscribe(queue)
