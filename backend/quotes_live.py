"""Near-real-time quotes for stocks, indices and FX from Yahoo Finance.

Yahoo has no free streaming API, so this polls. Every POLL_SECONDS, batch requests
(`/v8/finance/spark`, 1-minute bars for today, at most 20 symbols each) return the
latest price of every symbol; each symbol's trading session comes from
`/v8/finance/chart`, refreshed every SESSION_REFRESH_SECONDS. With the 23 default
symbols that is about 500 requests an hour in all.

Each tick says whether the market is open and, if it is, whether Yahoo's newest
bar is older than DELAYED_AFTER_SECONDS (then it is `delayed`, never called
live). When the market is closed the price is the last regular-session price.
Yahoo Finance data is for personal use; FinPulse is run as a personal terminal.
"""
import asyncio
import logging
import math
import time
from typing import Optional

import httpx

from backend import config
from backend.indices import INDEX_SYMBOLS
from backend.live import LiveFeed

log = logging.getLogger("finpulse.quotes")

PROVIDER = "yahoo"
POLL_SECONDS = 15
# The most symbols Yahoo accepts in one spark request.
SPARK_BATCH = 20
SESSION_REFRESH_SECONDS = 600
DELAYED_AFTER_SECONDS = 180
REQUEST_TIMEOUT_SECONDS = 10
RETRY_MAX_SECONDS = 120
HEADERS = {"User-Agent": "Mozilla/5.0 (FinPulse personal terminal)"}

# FinPulse symbol -> Yahoo symbol, for FX pairs written "BASE/QUOTE".
FX_TO_YAHOO = {
    "USD/INR": "INR=X", "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X",
    "EUR/INR": "EURINR=X", "EUR/GBP": "EURGBP=X", "EUR/JPY": "EURJPY=X",
}

_monotonic = time.monotonic
_wall = time.time


def yahoo_symbol(symbol: str) -> str:
    return FX_TO_YAHOO.get(symbol, symbol)


def asset_class_for(symbol: str) -> str:
    if "/" in symbol:
        return "fx"
    return "index" if symbol.startswith("^") or symbol in INDEX_SYMBOLS else "stock"


def latest_bar(series: dict) -> Optional[tuple[int, float]]:
    """(unix seconds, close) of the newest bar with a price, or None."""
    times, closes = series.get("timestamp") or [], series.get("close") or []
    for when, close in zip(reversed(times), reversed(closes)):
        if isinstance(close, (int, float)) and math.isfinite(close) and close > 0 and isinstance(when, int):
            return when, float(close)
    return None


def build_tick(symbol: str, series: dict, session: Optional[tuple[int, int]], now: float) -> Optional[dict]:
    """A tick from one symbol's spark series, or None if it has no usable price."""
    bar = latest_bar(series)
    if bar is None:
        return None
    bar_time, price = bar
    previous = series.get("previousClose") or series.get("chartPreviousClose")
    previous = float(previous) if isinstance(previous, (int, float)) and previous > 0 else None

    # Unknown session (its lookup failed): open/closed is None and only the age counts.
    market_open = None if session is None else session[0] <= now < session[1]
    delayed = market_open is not False and now - bar_time > DELAYED_AFTER_SECONDS
    return {
        "symbol": symbol,
        "asset_class": asset_class_for(symbol),
        "market": "quotes",
        "provider": PROVIDER,
        "price": price,
        "previous_close": previous,
        "change_pct_24h": round((price / previous - 1) * 100, 4) if previous else None,
        "change_window": "1d",
        "market_open": market_open,
        "delayed": delayed,
        "time": bar_time * 1000,
        "received_at": now,
    }


def parse_session(body) -> Optional[tuple[int, int]]:
    """(start, end) of the current regular session from a chart response."""
    try:
        regular = body["chart"]["result"][0]["meta"]["currentTradingPeriod"]["regular"]
        return int(regular["start"]), int(regular["end"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


class YahooQuotes(LiveFeed):
    """Polls Yahoo and publishes ticks through the same subscriber queues as LiveFeed."""

    def __init__(self, symbols: list[str]):
        super().__init__(symbols, [], market="quotes", asset_class="stock")
        self.source = config.YAHOO_QUOTE_URL
        self._sessions: dict[str, tuple[int, int]] = {}
        self._sessions_at: dict[str, float] = {}
        self._client: Optional[httpx.AsyncClient] = None

    def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
        self._task = asyncio.create_task(self._run(), name="finpulse-yahoo-quotes")

    async def stop(self) -> None:
        await super().stop()
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _run(self) -> None:
        delay = POLL_SECONDS
        while True:
            try:
                await self.poll()
                delay = POLL_SECONDS
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network errors, rate limits, malformed responses
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("Yahoo quotes failed: %s", self.last_error)
                if self.connected:
                    self.connected = False
                    self._broadcast(self._status_message())
                delay = min(delay * 2, RETRY_MAX_SECONDS)
            await asyncio.sleep(delay)

    async def _get(self, path: str, params: dict) -> dict:
        response = await self._client.get(f"{config.YAHOO_QUOTE_URL}{path}", params=params)
        if response.status_code != 200:
            raise RuntimeError(f"Yahoo answered {response.status_code}")
        return response.json()

    async def _refresh_sessions(self, now_mono: float) -> None:
        for symbol in self.symbols:
            if now_mono - self._sessions_at.get(symbol, -math.inf) < SESSION_REFRESH_SECONDS:
                continue
            try:
                session = parse_session(await self._get(
                    f"/v8/finance/chart/{yahoo_symbol(symbol)}", {"range": "1d", "interval": "1d"},
                ))
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                log.warning("Yahoo session lookup for %s failed: %s", symbol, exc)
                session = None
            if session:
                self._sessions[symbol] = session
            self._sessions_at[symbol] = now_mono

    async def poll(self) -> None:
        """One round: refresh due sessions, fetch every price, publish the ticks."""
        await self._refresh_sessions(_monotonic())
        body: dict = {}
        wanted = [yahoo_symbol(s) for s in self.symbols]
        for start in range(0, len(wanted), SPARK_BATCH):  # Yahoo takes at most 20 symbols a request
            part = await self._get("/v8/finance/spark", {
                "symbols": ",".join(wanted[start:start + SPARK_BATCH]), "range": "1d", "interval": "1m",
            })
            if not isinstance(part, dict):
                raise ValueError("Yahoo sent a response that is not a JSON object")
            body.update(part)

        now = _wall()
        published = 0
        for symbol in self.symbols:
            series = body.get(yahoo_symbol(symbol))
            if not isinstance(series, dict):
                continue
            session = self._sessions.get(symbol)
            if session and now >= session[1]:
                self._sessions_at.pop(symbol, None)  # the session ended: look up the next one
            tick = build_tick(symbol, series, session, now)
            if tick is None:
                continue
            self.latest[symbol] = tick
            self._broadcast({"type": "tick", **tick})
            published += 1

        self.last_message_at = now
        if published and not self.connected:
            self.connected = True
            self.last_error = None
            self._broadcast(self._status_message())
