"""Trading hours of the world's stock exchanges, with today's or the next session.

Each exchange is represented by its benchmark index. Today's regular session comes
from Yahoo (the quote poller already looks it up for every index, see
backend/quotes_live.py). Once a session has ended, Yahoo keeps reporting it until
the next local day, so the next one is estimated: same local hours on the next
trading day. Estimates do not know exchange holidays, and lunch breaks (Tokyo,
Hong Kong, mainland China, Singapore, Jakarta, Kuala Lumpur) are not shown; both
are said in the response.
"""
import time
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from backend import feeds
from backend.indices import WORLD_INDICES

router = APIRouter(tags=["market-hours"])

MON_FRI = (0, 1, 2, 3, 4)
SUN_THU = (6, 0, 1, 2, 3)
LUNCH_BREAK = {"Tokyo", "Hong Kong", "Shanghai", "Shenzhen", "Singapore", "Jakarta", "Kuala Lumpur"}

# id, exchange, city, benchmark index, trading days (Python weekday numbers)
EXCHANGES = [
    ("nyse", "NYSE / Nasdaq", "New York", "^GSPC", MON_FRI),
    ("tsx", "Toronto Stock Exchange", "Toronto", "^GSPTSE", MON_FRI),
    ("bmv", "Bolsa Mexicana", "Mexico City", "^MXX", MON_FRI),
    ("b3", "B3", "São Paulo", "^BVSP", MON_FRI),
    ("lse", "London Stock Exchange", "London", "^FTSE", MON_FRI),
    ("xetra", "Xetra", "Frankfurt", "^GDAXI", MON_FRI),
    ("epa", "Euronext Paris", "Paris", "^FCHI", MON_FRI),
    ("ams", "Euronext Amsterdam", "Amsterdam", "^AEX", MON_FRI),
    ("bme", "Bolsa de Madrid", "Madrid", "^IBEX", MON_FRI),
    ("mil", "Borsa Italiana", "Milan", "FTSEMIB.MI", MON_FRI),
    ("six", "SIX Swiss Exchange", "Zurich", "^SSMI", MON_FRI),
    ("sto", "Nasdaq Stockholm", "Stockholm", "^OMX", MON_FRI),
    ("tase", "Tel Aviv Stock Exchange", "Tel Aviv", "^TA125.TA", MON_FRI),
    ("tadawul", "Saudi Exchange (Tadawul)", "Riyadh", "^TASI.SR", SUN_THU),
    ("jse", "Johannesburg Stock Exchange", "Johannesburg", "^J200.JO", MON_FRI),
    ("nse", "NSE / BSE", "Mumbai", "^NSEI", MON_FRI),
    ("sgx", "Singapore Exchange", "Singapore", "^STI", MON_FRI),
    ("idx", "Indonesia Stock Exchange", "Jakarta", "^JKSE", MON_FRI),
    ("bursa", "Bursa Malaysia", "Kuala Lumpur", "^KLSE", MON_FRI),
    ("sse", "Shanghai Stock Exchange", "Shanghai", "000001.SS", MON_FRI),
    ("szse", "Shenzhen Stock Exchange", "Shenzhen", "399001.SZ", MON_FRI),
    ("hkex", "Hong Kong Exchanges", "Hong Kong", "^HSI", MON_FRI),
    ("twse", "Taiwan Stock Exchange", "Taipei", "^TWII", MON_FRI),
    ("krx", "Korea Exchange", "Seoul", "^KS11", MON_FRI),
    ("tse", "Tokyo Stock Exchange", "Tokyo", "^N225", MON_FRI),
    ("asx", "ASX", "Sydney", "^AXJO", MON_FRI),
    ("nzx", "NZX", "Wellington", "^NZ50", MON_FRI),
]
_INDEX = {row[0]: row for row in WORLD_INDICES}

_wall = time.time


def next_session(session: tuple[int, int], timezone: str, trading_days: tuple[int, ...],
                 now: float) -> Optional[dict]:
    """The session to show: Yahoo's own if it has not ended, else the same local hours
    on the next trading day (an estimate)."""
    start, end = session
    if now < end:
        return {"start": start, "end": end, "estimated": False}
    zone = ZoneInfo(timezone)
    local_start = datetime.fromtimestamp(start, zone)
    local_end = datetime.fromtimestamp(end, zone)
    span_days = (local_end.date() - local_start.date()).days
    for days in range(1, 8):
        day = local_start.date() + timedelta(days=days)
        if day.weekday() in trading_days:
            # From the local wall-clock times, so a daylight-saving change is respected.
            opens = datetime.combine(day, local_start.time(), zone)
            closes = datetime.combine(day + timedelta(days=span_days), local_end.time(), zone)
            return {"start": int(opens.timestamp()), "end": int(closes.timestamp()), "estimated": True}
    return None


@router.get("/api/market-hours")
def market_hours():
    """Every exchange with its hours; status and countdowns are worked out from `as_of`."""
    now = _wall()
    sessions = feeds.yahoo_quotes.sessions()
    exchanges = []
    for id_, name, city, symbol, days in EXCHANGES:
        _, index_name, region, country, _, timezone = _INDEX[symbol]
        session = sessions.get(symbol)
        exchanges.append({
            "id": id_, "name": name, "city": city, "country": country, "region": region, "timezone": timezone,
            "benchmark": symbol, "benchmark_name": index_name,
            "trading_days": list(days),
            "session": next_session(session, timezone, days, now) if session else None,
            "lunch_break": city in LUNCH_BREAK,
        })
    return {
        "as_of": now,
        "count": len(exchanges),
        "exchanges": exchanges,
        "notes": [
            "Regular sessions from Yahoo Finance; the next session after one ends is estimated from the same "
            "local hours on the next trading day.",
            "Exchange holidays are not known, and lunch breaks are not shown.",
        ],
    }
