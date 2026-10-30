"""Normalized latest quotes: one MarketRecord per tracked instrument.

A live symbol uses its latest tick: real_time, or stale once the tick is too old
or its feed is down. Yahoo quotes can also be `delayed` (Yahoo's newest bar is old
while the market is open) or, while the market is closed, `historical` with the
last regular-session price. Anything else uses its latest stored daily close
(historical). An instrument with neither is reported as unavailable.
"""
import time
from datetime import datetime, timezone
from typing import Optional

from backend import config
from backend.live import STALE_AFTER_SECONDS
from backend.quotes_live import asset_class_for as yahoo_asset_class
from backend.schemas.market import MarketRecord

# Quote currency of stored instruments that are not "BASE/QUOTE" pairs. An
# instrument missing here gets currency None rather than a guess.
STORED_CURRENCIES = {"AAPL": "USD", "^NSEI": "INR", "^GSPC": "USD", "GC=F": "USD", "SI=F": "USD"}

# Gold (GC=F) and silver (SI=F) are COMEX futures, both quoted per troy ounce.
UNITS = {
    "crypto": "per coin", "stock": "per share", "index": "index points", "commodity": "per troy ounce",
    "fx": "quote currency per unit of base",
}
# Commodities not priced per troy ounce.
SYMBOL_UNITS = {"CL/USDT": "per barrel", "BZ/USDT": "per barrel"}


def unit_for(symbol: str, asset_class: str) -> str:
    return SYMBOL_UNITS.get(symbol, UNITS[asset_class])


def _utc(seconds: Optional[float]) -> Optional[datetime]:
    return None if seconds is None else datetime.fromtimestamp(seconds, tz=timezone.utc)


def currency_of(symbol: str) -> Optional[str]:
    if "/" in symbol:
        return symbol.split("/", 1)[1]
    return STORED_CURRENCIES.get(symbol)


def live_asset_class(symbol: str) -> str:
    """Crypto, unless the symbol is a Binance TradFi future or a Yahoo quote."""
    if symbol in config.TRADFI_LIVE_SYMBOLS:
        return "commodity"
    if symbol in config.YAHOO_LIVE_SYMBOLS:
        return yahoo_asset_class(symbol)
    return "crypto"


def asset_class_of(value: str) -> str:
    value = str(value).lower()
    return value if value in UNITS else "stock"


def _parse_stored_time(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def live_record(symbol: str, tick: dict, feed_connected: bool, now: float) -> MarketRecord:
    received_at = tick.get("received_at")
    fresh = feed_connected and received_at is not None and now - received_at <= STALE_AFTER_SECONDS
    event_ms = tick.get("time")
    asset_class = live_asset_class(symbol)
    polled = tick.get("provider") == "yahoo"

    status, error = "real_time", None
    if not fresh:
        status = "stale"
        error = "Live feed disconnected" if not feed_connected else f"No update for more than {STALE_AFTER_SECONDS}s"
    elif tick.get("market_open") is False:
        status, error = "historical", "Market closed; last regular-session price"
    elif tick.get("delayed"):
        status, error = "delayed", "The provider's newest price is more than a few minutes old"

    return MarketRecord(
        instrument_id=f"{asset_class}:{symbol}",
        symbol=symbol,
        asset_class=asset_class,
        price=tick.get("price"),
        currency=currency_of(symbol),
        unit=unit_for(symbol, asset_class),
        provider=tick.get("provider", "binance"),
        status=status,
        source_timestamp=_utc(event_ms / 1000) if isinstance(event_ms, (int, float)) else None,
        retrieved_at=_utc(received_at),
        interval="1m" if polled else "tick",
        change_pct=tick.get("change_pct_24h"),
        change_window=tick.get("change_window", "24h"),
        error=error,
    )


def stored_record(asset: dict, error: Optional[str] = None) -> MarketRecord:
    asset_class = asset_class_of(asset.get("asset_type"))
    symbol = asset["symbol"]
    price = asset.get("latest_price")
    return MarketRecord(
        instrument_id=f"{asset_class}:{symbol}",
        symbol=symbol,
        asset_class=asset_class,
        price=price,
        currency=currency_of(symbol),
        unit=UNITS[asset_class],
        provider="database",
        status="historical" if price is not None else "unavailable",
        source_timestamp=_parse_stored_time(asset.get("latest_timestamp")),
        interval="1d",
        change_pct=asset.get("daily_change_pct"),
        change_window="1d",
        error=error,
    )


def build_quotes(
    live_symbols: list[str],
    ticks: dict[str, dict],
    feed_connected: bool | dict[str, bool],
    stored_assets: list[dict],
    now: Optional[float] = None,
) -> list[MarketRecord]:
    """`feed_connected` is one flag for every live symbol, or one per symbol."""
    now = time.time() if now is None else now
    stored = {asset["symbol"]: asset for asset in stored_assets}
    records = []

    for symbol in live_symbols:
        tick = ticks.get(symbol)
        connected = feed_connected.get(symbol, False) if isinstance(feed_connected, dict) else feed_connected
        if tick and tick.get("price") is not None:
            records.append(live_record(symbol, tick, connected, now))
        elif symbol in stored:
            records.append(stored_record(stored[symbol], error="No live tick received yet"))
        else:
            asset_class = live_asset_class(symbol)
            records.append(MarketRecord(
                instrument_id=f"{asset_class}:{symbol}",
                symbol=symbol,
                asset_class=asset_class,
                currency=currency_of(symbol),
                unit=unit_for(symbol, asset_class),
                provider="yahoo" if symbol in config.YAHOO_LIVE_SYMBOLS else "binance",
                status="unavailable",
                interval="tick",
                error="No live tick received yet",
            ))

    live = set(live_symbols)
    for symbol, asset in sorted(stored.items()):
        if symbol not in live:
            records.append(stored_record(asset))
    return records
