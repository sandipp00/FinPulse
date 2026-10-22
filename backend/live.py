"""Live crypto market feed.

A background task keeps one WebSocket open to Binance's public streams
(24h ticker + 1m klines for each symbol), keeps the latest tick per symbol in
memory, fans ticks out to connected browser clients, and stores closed 1-minute
candles in SQLite so charts survive restarts.
"""
import asyncio
import json
import logging
import sqlite3
import time
from typing import Optional

import websockets

from backend import config

log = logging.getLogger("finpulse.live")

SUBSCRIBER_QUEUE_SIZE = 200
RECONNECT_MIN_SECONDS = 1
RECONNECT_MAX_SECONDS = 30
# Binance drops a stream silently now and then; reconnect if nothing arrives.
STALE_AFTER_SECONDS = 30


def to_stream_name(symbol: str) -> str:
    return symbol.replace("/", "").lower()


class LiveFeed:
    def __init__(self, symbols: list[str], ws_urls: list[str]):
        self.symbols = symbols
        self.ws_urls = ws_urls
        # Binance symbol ("BTCUSDT") -> display symbol ("BTC/USDT")
        self._by_binance = {s.replace("/", ""): s for s in symbols}

        self.latest: dict[str, dict] = {}
        self.connected = False
        self.source: Optional[str] = None
        self.last_message_at: Optional[float] = None
        self.last_error: Optional[str] = None

        self._subscribers: set[asyncio.Queue] = set()
        self._task: Optional[asyncio.Task] = None
        self._candle_buffer: list[tuple] = []

    # ---- lifecycle -----------------------------------------------------

    def start(self) -> None:
        self._ensure_table()
        self._task = asyncio.create_task(self._run(), name="finpulse-live-feed")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush_candles()

    def status(self) -> dict:
        age = (
            round(time.time() - self.last_message_at, 1)
            if self.last_message_at
            else None
        )
        return {
            "connected": self.connected,
            "source": self.source,
            "symbols": self.symbols,
            "last_message_age_seconds": age,
            "subscribers": len(self._subscribers),
            "last_error": self.last_error,
        }

    # ---- subscribers (browser clients) ---------------------------------

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self, message: dict) -> None:
        for queue in self._subscribers:
            if queue.full():
                # Slow client: drop its oldest message rather than block the feed.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(message)

    # ---- upstream connection -------------------------------------------

    def _stream_url(self, base: str) -> str:
        streams = []
        for symbol in self.symbols:
            name = to_stream_name(symbol)
            streams += [f"{name}@ticker", f"{name}@kline_1m"]
        return f"{base.rstrip('/')}/stream?streams={'/'.join(streams)}"

    async def _run(self) -> None:
        delay = RECONNECT_MIN_SECONDS
        url_index = 0

        while True:
            base = self.ws_urls[url_index % len(self.ws_urls)]
            try:
                async with websockets.connect(
                    self._stream_url(base),
                    ping_interval=20,
                    ping_timeout=20,
                    open_timeout=10,
                ) as upstream:
                    self.connected = True
                    self.source = base
                    self.last_error = None
                    delay = RECONNECT_MIN_SECONDS
                    log.info("Live feed connected: %s", base)
                    self._broadcast(self._status_message())
                    await self._consume(upstream)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network errors, HTTP 451, timeouts...
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("Live feed error on %s: %s", base, self.last_error)
            finally:
                if self.connected:
                    self.connected = False
                    self._broadcast(self._status_message())

            # Rotate to the next endpoint so a blocked region can recover.
            url_index += 1
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)

    async def _consume(self, upstream) -> None:
        while True:
            raw = await asyncio.wait_for(
                upstream.recv(), timeout=STALE_AFTER_SECONDS
            )
            self.last_message_at = time.time()
            payload = json.loads(raw).get("data", {})

            event = payload.get("e")
            if event == "24hrTicker":
                self._handle_ticker(payload)
            elif event == "kline":
                await self._handle_kline(payload)

    def _status_message(self) -> dict:
        return {"type": "status", "connected": self.connected}

    def _handle_ticker(self, data: dict) -> None:
        symbol = self._by_binance.get(data["s"])
        if symbol is None:
            return

        tick = {
            "symbol": symbol,
            "price": float(data["c"]),
            "change_pct_24h": float(data["P"]),
            "open_24h": float(data["o"]),
            "high_24h": float(data["h"]),
            "low_24h": float(data["l"]),
            "volume_24h": float(data["v"]),
            "quote_volume_24h": float(data["q"]),
            "time": data["E"],
        }
        self.latest[symbol] = tick
        self._broadcast({"type": "tick", **tick})

    async def _handle_kline(self, data: dict) -> None:
        kline = data["k"]
        if not kline["x"]:  # only persist closed candles
            return

        symbol = self._by_binance.get(data["s"])
        if symbol is None:
            return

        self._candle_buffer.append((
            kline["t"], symbol, "1m",
            float(kline["o"]), float(kline["h"]), float(kline["l"]),
            float(kline["c"]), float(kline["v"]),
        ))
        if len(self._candle_buffer) >= len(self.symbols):
            await self._flush_candles()

    # ---- persistence ---------------------------------------------------

    def _ensure_table(self) -> None:
        try:
            config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(config.DATABASE_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS live_candles (
                        open_time INTEGER NOT NULL,
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume REAL NOT NULL,
                        PRIMARY KEY (symbol, interval, open_time)
                    )
                """)
        except sqlite3.Error as exc:
            log.error("Could not prepare live_candles table: %s", exc)

    async def _flush_candles(self) -> None:
        if not self._candle_buffer:
            return
        rows, self._candle_buffer = self._candle_buffer, []
        try:
            await asyncio.to_thread(self._write_candles, rows)
        except sqlite3.Error as exc:
            log.error("Could not store live candles: %s", exc)

    @staticmethod
    def _write_candles(rows: list[tuple]) -> None:
        with sqlite3.connect(config.DATABASE_PATH, timeout=10) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO live_candles
                (open_time, symbol, interval, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )


feed = LiveFeed(config.LIVE_SYMBOLS, config.BINANCE_WS_URLS)
