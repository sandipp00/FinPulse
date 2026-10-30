"""Quotes for the Shanghai, Shenzhen and Hang Seng indices from Tencent Finance.

Yahoo runs these about 15 minutes behind. Tencent's public quote endpoint
(qt.gtimg.cn, no key) is unofficial: it can change or stop without notice, and
it is used here for personal use only. Each quote carries the exchange's own
timestamp, so the quote poller (backend/quotes_live.py) only prefers it when it
is newer than Yahoo's, and judges its freshness by that timestamp: if Tencent is
delayed too, the quote is still tagged DELAYED. When Tencent fails, Yahoo stays.
"""
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from backend import config

log = logging.getLogger("finpulse.tencent")

PROVIDER = "tencent"
REQUEST_TIMEOUT_SECONDS = 8
CHINA_TIME = timezone(timedelta(hours=8))  # Shanghai, Shenzhen and Hong Kong (no daylight saving)

# FinPulse symbol -> Tencent code.
TENCENT_CODES = {"000001.SS": "sh000001", "399001.SZ": "sz399001", "^HSI": "hkHSI"}


def parse_time(raw: str) -> Optional[float]:
    """'20261030150002' (mainland) or '2026/10/30 16:08:01' (Hong Kong), China time -> unix seconds."""
    for fmt in ("%Y%m%d%H%M%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=CHINA_TIME).timestamp()
        except ValueError:
            continue
    return None


def _number(raw: str) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def parse(text: str) -> dict[str, dict]:
    """Tencent's response -> {tencent code: {"price", "previous_close", "time"}}; bad lines are skipped.

    Each line looks like v_sh000001="1~name~000001~price~previous close~open~...";
    the price is field 3, the previous close field 4 and the time field 30.
    """
    quotes = {}
    for line in text.split(";"):
        if "=" not in line or '"' not in line:
            continue
        code = line.split("=", 1)[0].strip().removeprefix("v_")
        fields = line.split('"')[1].split("~")
        if len(fields) <= 30:
            continue
        price, previous, when = _number(fields[3]), _number(fields[4]), parse_time(fields[30])
        if price is None or when is None:
            continue
        quotes[code] = {"price": price, "previous_close": previous, "time": when}
    return quotes


async def fetch(client: httpx.AsyncClient, symbols: list[str]) -> dict[str, dict]:
    """FinPulse symbol -> quote for those with a Tencent code. Raises httpx errors to the caller."""
    codes = {TENCENT_CODES[s]: s for s in symbols if s in TENCENT_CODES}
    if not codes:
        return {}
    response = await client.get(f"{config.TENCENT_QUOTE_URL}/q={','.join(codes)}", timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    # Tencent answers in GBK (the index names are Chinese); only numbers are used.
    quotes = parse(response.content.decode("gbk", errors="replace"))
    return {codes[code]: quote for code, quote in quotes.items() if code in codes}


def apply(tick: dict, quote: dict, delayed_after: float, now: float) -> dict:
    """The Yahoo tick with Tencent's newer price and time; freshness from Tencent's own timestamp."""
    price, previous = quote["price"], quote["previous_close"] or tick.get("previous_close")
    return {
        **tick,
        "provider": PROVIDER,
        "price": price,
        "previous_close": previous,
        "change_pct_24h": round((price / previous - 1) * 100, 4) if previous else None,
        "delayed": tick.get("market_open") is not False and now - quote["time"] > delayed_after,
        "time": int(quote["time"] * 1000),
    }
