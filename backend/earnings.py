"""Earnings dates and results for the followed US stocks, from Nasdaq's website API.

Two requests per stock (api.nasdaq.com, no key; unofficial, used for personal use):
  * /analyst/{symbol}/earnings-date: the next report, as a sentence. Nasdaq's vendor
    (Zacks) either "expects" a date (with before/after the market, the consensus EPS
    forecast and how many analysts it rests on) or "estimates" one from past
    reporting dates, or has none yet (usually just after a report);
  * /company/{symbol}/earnings-surprise: the last four quarters' reported EPS against
    the consensus forecast.

Nothing is invented: a figure Nasdaq does not give is None, and every date says how
sure it is. Each stock is cached for CACHE_SECONDS, and its last good answer is kept
for STALE_MAX_SECONDS (marked stale) when Nasdaq fails.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from backend import config
from backend.stocks import STOCK_SYMBOLS, US_STOCKS

log = logging.getLogger("finpulse.earnings")

router = APIRouter(prefix="/api/earnings", tags=["earnings"])

PROVIDER = "nasdaq"
SOURCE_URL = "https://www.nasdaq.com/market-activity/earnings"
CACHE_SECONDS = 6 * 3600
STALE_MAX_SECONDS = 3 * 86_400
REQUEST_TIMEOUT_SECONDS = 15
CONCURRENCY = 4
# Nasdaq's API answers browsers; a plain client is refused.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
NAMES = {row[0]: row[1] for row in US_STOCKS}

_DATE = re.compile(r"(expected\*?|estimated) to report earnings on\s+(\d{1,2})/(\d{1,2})/(\d{4})"
                   r"(?:\s+(before market open|after market close))?", re.I)
_QUARTER = re.compile(r"fiscal Quarter ending\s+([A-Za-z]{3} \d{4})")
_ANALYSTS = re.compile(r"based on\s+(\d+)\s+analysts")
_FORECAST = re.compile(r"consensus EPS forecast for the quarter is \$(-?\d+(?:\.\d+)?)")
_LAST_YEAR = re.compile(r"reported EPS for the same quarter last year was \$(-?\d+(?:\.\d+)?)")

_monotonic = time.monotonic
_wall = time.time


class EarningsError(Exception):
    pass


@dataclass
class _Entry:
    body: dict
    fetched_mono: float
    fetched_wall: float


_cache: dict[str, _Entry] = {}
_lock: Optional[asyncio.Lock] = None
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    _cache.clear()


def nasdaq_symbol(symbol: str) -> str:
    return symbol.replace("-", ".")  # BRK-B is BRK.B on Nasdaq


def _float(value) -> Optional[float]:
    try:
        number = float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _match(pattern: re.Pattern, text: str) -> Optional[str]:
    found = pattern.search(text)
    return found.group(1) if found else None


def parse_next(text: str) -> Optional[dict]:
    """Nasdaq's sentence about the next report -> its date and figures, or None if it has no date."""
    text = re.sub(r"\s+", " ", text or "")
    found = _DATE.search(text)
    if not found:
        return None
    kind, month, day, year, timing = found.groups()
    try:
        when = date(int(year), int(month), int(day))
    except ValueError:
        return None
    analysts = _match(_ANALYSTS, text)
    return {
        "date": when.isoformat(),
        # "expected": Nasdaq's vendor lists the date; "estimated": derived from past reporting dates.
        "certainty": "estimated" if kind.lower() == "estimated" else "expected",
        "timing": {"before market open": "before_open", "after market close": "after_close"}.get((timing or "").lower()),
        "fiscal_quarter": _match(_QUARTER, text),
        "eps_forecast": _float(_match(_FORECAST, text)),
        "analysts": int(analysts) if analysts else None,
        "eps_last_year": _float(_match(_LAST_YEAR, text)),
    }


def parse_history(body) -> list[dict]:
    """The earnings-surprise table -> past quarters, newest first; [] when Nasdaq has none."""
    rows = ((((body or {}).get("data") or {}).get("earningsSurpriseTable") or {}).get("rows")) or []
    history = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            reported = datetime.strptime(str(row.get("dateReported")), "%m/%d/%Y").date().isoformat()
        except ValueError:
            reported = None
        history.append({
            "fiscal_quarter": row.get("fiscalQtrEnd"),
            "date": reported,
            "eps": _float(row.get("eps")),
            "eps_forecast": _float(row.get("consensusForecast")),
            "surprise_pct": _float(row.get("percentageSurprise")),
        })
    return history


async def _get(path: str):
    try:
        response = await get_client().get(f"{config.NASDAQ_API_URL}{path}")
    except httpx.HTTPError as exc:
        raise EarningsError(f"Could not reach Nasdaq ({type(exc).__name__})") from None
    if response.status_code != 200:
        raise EarningsError(f"Nasdaq answered {response.status_code}")
    try:
        return response.json()
    except ValueError:
        raise EarningsError("Nasdaq sent a response that is not JSON") from None


async def _fetch(symbol: str) -> dict:
    code = nasdaq_symbol(symbol)
    next_body, history_body = await asyncio.gather(
        _get(f"/analyst/{code}/earnings-date"), _get(f"/company/{code}/earnings-surprise"),
    )
    text = ((next_body or {}).get("data") or {}).get("reportText")
    if not isinstance(text, str):
        raise EarningsError("Nasdaq sent earnings data in an unexpected shape")
    return {"symbol": symbol, "name": NAMES.get(symbol, symbol), "next": parse_next(text), "history": parse_history(history_body)}


def _stamp(entry: _Entry, stale: Optional[str]) -> dict:
    fetched = datetime.fromtimestamp(entry.fetched_wall, tz=timezone.utc).isoformat()
    return {**entry.body, "fetched_at": fetched, "stale": stale}


async def stock(symbol: str) -> dict:
    """One stock's earnings, from cache when fresh. Raises EarningsError with no usable copy."""
    cached = _cache.get(symbol)
    if cached and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
        return _stamp(cached, None)
    try:
        body = await _fetch(symbol)
    except EarningsError as exc:
        if cached and _monotonic() - cached.fetched_mono <= STALE_MAX_SECONDS:
            log.warning("Serving cached Nasdaq earnings for %s: %s", symbol, exc)
            return _stamp(cached, str(exc))
        raise
    entry = _Entry(body, _monotonic(), _wall())
    _cache[symbol] = entry
    return _stamp(entry, None)


async def all_stocks() -> tuple[list[dict], list[str]]:
    """Every followed stock (in market-cap order) and the symbols that could not be loaded."""
    global _lock
    _lock = _lock or asyncio.Lock()
    async with _lock:  # one refresh at a time: viewers arriving together share it
        gate = asyncio.Semaphore(CONCURRENCY)

        async def limited(symbol):
            async with gate:
                return await stock(symbol)

        results = await asyncio.gather(*(limited(s) for s in STOCK_SYMBOLS), return_exceptions=True)
    stocks, failed = [], []
    for symbol, result in zip(STOCK_SYMBOLS, results):
        if isinstance(result, EarningsError):
            failed.append(symbol)
        elif isinstance(result, Exception):
            raise result
        else:
            stocks.append(result)
    return stocks, failed


def upcoming(stocks: list[dict], today: date) -> list[dict]:
    """Next reports from today on, soonest first."""
    rows = [{"symbol": s["symbol"], "name": s["name"], **s["next"]} for s in stocks
            if s["next"] and s["next"]["date"] >= today.isoformat()]
    return sorted(rows, key=lambda r: (r["date"], r["timing"] != "before_open", r["symbol"]))


NOTES = [
    "Dates and figures from Nasdaq's website (its vendor is Zacks Investment Research); unofficial, personal use.",
    "Expected: the date Nasdaq lists. Estimated: worked out from the company's past reporting dates, so it may move.",
    "No date: Nasdaq has none yet, usually because the company has just reported.",
    "EPS figures are as Nasdaq reports them; analysts usually forecast adjusted EPS, which can differ from the "
    "GAAP figure in the company's filing.",
]


@router.get("")
async def earnings(symbol: Optional[str] = Query(None, max_length=10)):
    """Upcoming earnings for the followed stocks, or one stock's next report and last quarters."""
    if not config.EARNINGS_ENABLED:
        raise HTTPException(status_code=503, detail="Earnings data is turned off (EARNINGS_ENABLED=false)")
    if symbol is not None:
        if symbol not in STOCK_SYMBOLS:
            raise HTTPException(status_code=404, detail=f"No earnings data for {symbol}: only the followed US stocks")
        try:
            return {**await stock(symbol), "provider": PROVIDER, "source_url": SOURCE_URL, "notes": NOTES}
        except EarningsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    stocks, failed = await all_stocks()
    if not stocks:
        raise HTTPException(status_code=502, detail="Nasdaq earnings data is unavailable for every stock")
    notes = NOTES + ([f"Could not load: {', '.join(failed)}."] if failed else [])
    return {
        "count": len(stocks),
        "upcoming": upcoming(stocks, datetime.now(timezone.utc).date()),
        "stocks": stocks,
        "failed": failed,
        "provider": PROVIDER,
        "source_url": SOURCE_URL,
        "notes": notes,
    }
