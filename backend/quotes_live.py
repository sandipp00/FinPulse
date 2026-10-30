"""Near-real-time quotes for stocks, indices and FX from Yahoo Finance.

Yahoo has no free streaming API, so this polls. Every POLL_SECONDS, batch requests
(`/v8/finance/spark`, 1-minute bars for today, at most 20 symbols each) return the
latest price of every symbol; each symbol's trading session comes from
`/v8/finance/chart`, refreshed every SESSION_REFRESH_SECONDS. A market that is
closed is only re-fetched every CLOSED_POLL_SECONDS (its price cannot move); its last
price is re-sent every round so it does not look stale. With the 44 default symbols
that is roughly 300 to 900 requests an hour, depending on how many markets are open.

Each tick says whether the market is open and, if it is, whether Yahoo's newest
bar is older than DELAYED_AFTER_SECONDS (then it is `delayed`, never called
live). When the market is closed the price is the last regular-session price.
Yahoo Finance data is for personal use; FinPulse is run as a personal terminal.
"""
import asyncio
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend import config, tencent_quotes
from backend.indices import INDEX_SYMBOLS
from backend.live import LiveFeed

log = logging.getLogger("finpulse.quotes")

PROVIDER = "yahoo"
POLL_SECONDS = 15
# The most symbols Yahoo accepts in one spark request.
SPARK_BATCH = 20
# A closed market is re-fetched this often; its last price is re-sent every round.
CLOSED_POLL_SECONDS = 300
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


def local_day(when: float, gmtoffset: int) -> str:
    """The exchange-local date of a unix time, as YYYY-MM-DD."""
    return datetime.fromtimestamp(when + gmtoffset, tz=timezone.utc).date().isoformat()


def close_before(daily: Optional["DailyCloses"], day: str) -> Optional[float]:
    """The last daily close dated before `day` (the previous session's close)."""
    if daily is None:
        return None
    earlier = [close for date, close in daily.closes if date < day]
    return earlier[-1] if earlier else None


def build_tick(symbol: str, series: dict, session: Optional[tuple[int, int]], now: float,
               daily: Optional["DailyCloses"] = None) -> Optional[dict]:
    """A tick from one symbol's spark series, or None if it has no usable price.

    The previous close comes from the daily bars (`daily`): the close of the session
    before the newest bar's local day. Yahoo's spark `previousClose` is used only
    without them; it can be a day older than it should be.
    """
    spark_previous = series.get("previousClose") or series.get("chartPreviousClose")
    spark_previous = float(spark_previous) if isinstance(spark_previous, (int, float)) and spark_previous > 0 else None
    # Unknown session (its lookup failed): open/closed is None and only the age counts.
    market_open = None if session is None else session[0] <= now < session[1]

    bar = latest_bar(series)
    if bar is None:
        # No bar yet today: the last close is the newest value there is. While the market
        # is closed that is its current value; just after the open (Yahoo runs some
        # exchanges ~15 minutes behind) it is shown as delayed. Hours unknown: nothing.
        last = daily.closes[-1] if daily and daily.closes else None
        if market_open is None or (last is None and spark_previous is None):
            return None
        bar_time = None
        price = last[1] if last else spark_previous
        previous = close_before(daily, last[0]) if last else None
        delayed = market_open
    else:
        bar_time, price = bar
        previous = close_before(daily, local_day(bar_time, daily.gmtoffset)) if daily else None
        previous = previous or spark_previous
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
        "time": bar_time * 1000 if bar_time is not None else None,
        "received_at": now,
    }


def parse_session(body) -> Optional[tuple[int, int]]:
    """(start, end) of the current regular session from a chart response."""
    try:
        regular = body["chart"]["result"][0]["meta"]["currentTradingPeriod"]["regular"]
        return int(regular["start"]), int(regular["end"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


@dataclass
class DailyCloses:
    gmtoffset: int  # the exchange's offset from UTC, seconds
    closes: list[tuple[str, float]]  # (local date, close), oldest first


def parse_daily(body) -> Optional[DailyCloses]:
    """The recent daily closes (by exchange-local date) from a chart response."""
    try:
        result = body["chart"]["result"][0]
        offset = int(result["meta"].get("gmtoffset") or 0)
        times, closes = result.get("timestamp") or [], result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    rows = {}
    for when, close in zip(times, closes):
        if isinstance(when, int) and isinstance(close, (int, float)) and math.isfinite(close) and close > 0:
            rows[local_day(when, offset)] = float(close)
    return DailyCloses(offset, sorted(rows.items())) if rows else None


class YahooQuotes(LiveFeed):
    """Polls Yahoo and publishes ticks through the same subscriber queues as LiveFeed."""

    def __init__(self, symbols: list[str]):
        super().__init__(symbols, [], market="quotes", asset_class="stock")
        self.source = config.YAHOO_QUOTE_URL
        self._sessions: dict[str, tuple[int, int]] = {}
        self._daily: dict[str, DailyCloses] = {}
        self._sessions_at: dict[str, float] = {}
        self._fetched_at: dict[str, float] = {}
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
                # Five daily bars: the session times and the closes the previous close comes from.
                body = await self._get(f"/v8/finance/chart/{yahoo_symbol(symbol)}", {"range": "5d", "interval": "1d"})
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                log.warning("Yahoo session lookup for %s failed: %s", symbol, exc)
                body = None
            session, daily = (parse_session(body), parse_daily(body)) if body else (None, None)
            if session:
                self._sessions[symbol] = session
            if daily:
                self._daily[symbol] = daily
            self._sessions_at[symbol] = now_mono

    def sessions(self) -> dict[str, tuple[int, int]]:
        """symbol -> (start, end) of its current regular session, as Yahoo last reported."""
        return dict(self._sessions)

    async def _tencent(self, symbols: list[str]) -> dict[str, dict]:
        """Tencent quotes for the symbols it covers; empty (Yahoo stays) if off or failing."""
        if not config.TENCENT_QUOTES_ENABLED:
            return {}
        try:
            return await tencent_quotes.fetch(self._client, symbols)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Tencent quotes failed, using Yahoo: %s", exc)
            return {}

    def _due(self, symbol: str, now: float) -> bool:
        """Fetch every round while the market is open (or its hours are unknown);
        a closed market only every CLOSED_POLL_SECONDS, since its price cannot move."""
        session = self._sessions.get(symbol)
        if session is None or session[0] <= now < session[1] or symbol not in self.latest:
            return True
        return now - self._fetched_at.get(symbol, -math.inf) >= CLOSED_POLL_SECONDS

    async def poll(self) -> None:
        """One round: refresh due sessions, fetch every price, publish the ticks."""
        await self._refresh_sessions(_monotonic())
        now = _wall()
        due = [s for s in self.symbols if self._due(s, now)]
        body: dict = {}
        wanted = [yahoo_symbol(s) for s in due]
        for start in range(0, len(wanted), SPARK_BATCH):  # Yahoo takes at most 20 symbols a request
            part = await self._get("/v8/finance/spark", {
                "symbols": ",".join(wanted[start:start + SPARK_BATCH]), "range": "1d", "interval": "1m",
            })
            if not isinstance(part, dict):
                raise ValueError("Yahoo sent a response that is not a JSON object")
            body.update(part)
        fresher = await self._tencent(due)

        now = _wall()
        published = 0
        for symbol in self.symbols:
            if symbol not in due:
                # A closed market between checks: its last price still stands, so re-send it
                # (otherwise browsers would mark it stale after 30 seconds).
                if symbol in self.latest:
                    tick = {**self.latest[symbol], "received_at": now}
                    self.latest[symbol] = tick
                    self._broadcast({"type": "tick", **tick})
                continue
            self._fetched_at[symbol] = now
            series = body.get(yahoo_symbol(symbol))
            if not isinstance(series, dict):
                continue
            session = self._sessions.get(symbol)
            if session and now >= session[1]:
                self._sessions_at.pop(symbol, None)  # the session ended: look up the next one
            tick = build_tick(symbol, series, session, now, self._daily.get(symbol))
            if tick is None:
                continue
            quote = fresher.get(symbol)
            if quote and (tick["time"] is None or quote["time"] * 1000 > tick["time"]):
                tick = tencent_quotes.apply(tick, quote, DELAYED_AFTER_SECONDS, now)
            self.latest[symbol] = tick
            self._broadcast({"type": "tick", **tick})
            published += 1

        self.last_message_at = now
        if published and not self.connected:
            self.connected = True
            self.last_error = None
            self._broadcast(self._status_message())
