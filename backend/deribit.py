"""Crypto derivatives for Bitcoin and Ethereum from Deribit's public market-data API.

Four views per coin, from five requests (no key, no account):
  * DVOL: Deribit's 30-day implied-volatility index, a year of daily closes;
  * the perpetual: funding rate (now, and 30 days of hourly history) and open interest;
  * the futures curve: each dated future's premium over the index, annualized;
  * options: put/call open interest and at-the-money implied volatility by expiry.

Deribit rate-limits public requests per IP and may ban an IP that sends too many,
so each coin is fetched at most once per CACHE_SECONDS, shared by every viewer,
and the last good result is kept for STALE_MAX_SECONDS (labelled `cached`) when
Deribit fails. Expiries come from the instrument names (BTC-27NOV26), which
Deribit settles at 08:00 UTC. Everything is descriptive market data, not advice.
"""
import asyncio
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query

from backend import config
from backend.schemas.market import SourceMeta

log = logging.getLogger("finpulse.deribit")

router = APIRouter(prefix="/api/crypto", tags=["crypto"])

PROVIDER = "deribit"
CACHE_SECONDS = 60
STALE_MAX_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 15
DAY_MS = 86_400_000
DVOL_DAYS = 366
FUNDING_DAYS = 30
# A premium annualized over less than this many days is mostly noise; it is not annualized.
MIN_ANNUALIZE_DAYS = 2.0
MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}
NAME = re.compile(r"^(?P<coin>[A-Z]+)-(?P<day>\d{1,2})(?P<month>[A-Z]{3})(?P<year>\d{2})(?:-(?P<strike>[\d.]+)-(?P<kind>[CP]))?$")

_monotonic = time.monotonic
_wall = time.time


class DeribitError(Exception):
    pass


@dataclass
class _Entry:
    body: dict
    fetched_mono: float
    fetched_wall: float


_cache: dict[str, _Entry] = {}
_locks: dict[str, asyncio.Lock] = {}
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": config.FEED_USER_AGENT})
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    _cache.clear()


def _number(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _pct(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(value * 100, digits)


def _date(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def parse_name(name: str) -> Optional[dict]:
    """'BTC-27NOV26' or 'BTC-27NOV26-80000-C' -> expiry (08:00 UTC, ms), strike, kind; None otherwise."""
    match = NAME.match(name or "")
    if not match or match["month"] not in MONTHS:
        return None
    try:
        expiry = datetime(2000 + int(match["year"]), MONTHS[match["month"]], int(match["day"]), 8, tzinfo=timezone.utc)
    except ValueError:
        return None
    return {
        "expiry_ms": expiry.timestamp() * 1000,
        "strike": float(match["strike"]) if match["strike"] else None,
        "kind": {"C": "call", "P": "put"}.get(match["kind"]),
    }


def dvol_summary(rows) -> dict:
    """DVOL daily candles [time, open, high, low, close] -> the latest value, its year and history."""
    points = [(r[0], _number(r[4])) for r in rows or [] if isinstance(r, list) and len(r) >= 5]
    points = [(t, v) for t, v in points if v is not None and v > 0]
    if not points:
        raise DeribitError("Deribit returned no DVOL values")
    values = [v for _, v in points]
    latest = values[-1]
    return {
        "value": round(latest, 2),
        "date": _date(points[-1][0]),
        "change_1d": round(latest - values[-2], 2) if len(values) > 1 else None,
        "high_1y": round(max(values), 2),
        "low_1y": round(min(values), 2),
        # Share of the year's daily closes at or below today's: 90 means higher than on 9 days in 10.
        "percentile_1y": round(sum(v <= latest for v in values) / len(values) * 100),
        "history": [{"time": _date(t), "value": round(v, 2)} for t, v in points],
    }


def funding_summary(ticker: dict, history) -> dict:
    """The perpetual's funding now and per day over the history, annualized, in percent.

    Deribit reports funding per 8 hours (`funding_8h`) and per hour (`interest_1h`).
    A day's figure is the mean hourly rate x 24 x 365, so a partial day still compares.
    """
    mark, index = _number(ticker.get("mark_price")), _number(ticker.get("index_price"))
    funding_8h = _number(ticker.get("funding_8h"))
    if mark is None or index is None or index <= 0:
        raise DeribitError("Deribit sent a perpetual ticker without prices")
    by_day: dict[str, list[float]] = {}
    for row in history or []:
        rate = _number(row.get("interest_1h")) if isinstance(row, dict) else None
        stamp = _number(row.get("timestamp")) if isinstance(row, dict) else None
        if rate is not None and stamp is not None:
            by_day.setdefault(_date(stamp), []).append(rate)
    return {
        "mark_price": mark,
        "index_price": index,
        "premium_pct": _pct(mark / index - 1, 3),
        "funding_8h_pct": _pct(funding_8h, 4),
        "funding_annualized_pct": _pct(None if funding_8h is None else funding_8h * 3 * 365),
        "open_interest_usd": _number(ticker.get("open_interest")),
        "history": [
            {"time": day, "value": round(sum(rates) / len(rates) * 24 * 365 * 100, 2)}
            for day, rates in sorted(by_day.items())
        ],
    }


def futures_curve(summaries, index_price: float, now_ms: float) -> list[dict]:
    """Dated futures, nearest first, with their premium over the index (annualized when far enough out)."""
    curve = []
    for row in summaries or []:
        parsed = parse_name(row.get("instrument_name")) if isinstance(row, dict) else None
        mark = _number(row.get("mark_price")) if parsed else None
        if parsed is None or parsed["strike"] is not None or mark is None or mark <= 0:
            continue  # the perpetual, an option or a bad row
        days = (parsed["expiry_ms"] - now_ms) / DAY_MS
        if days <= 0:
            continue
        basis = mark / index_price - 1
        curve.append({
            "instrument": row["instrument_name"],
            "expiry": _date(parsed["expiry_ms"]),
            "days": round(days, 1),
            "mark_price": mark,
            "basis_pct": _pct(basis, 3),
            "annualized_pct": _pct(basis * 365 / days) if days >= MIN_ANNUALIZE_DAYS else None,
            "open_interest_usd": _number(row.get("open_interest")),
        })
    return sorted(curve, key=lambda r: r["days"])


def options_summary(summaries, now_ms: float) -> dict:
    """Put/call open interest, and at-the-money implied volatility per expiry.

    At the money is the strike nearest the expiry's underlying price; its IV is the
    mean of the call's and the put's mark IV there (whichever exist).
    """
    calls = puts = 0.0
    expiries: dict[float, dict] = {}
    for row in summaries or []:
        parsed = parse_name(row.get("instrument_name")) if isinstance(row, dict) else None
        if parsed is None or parsed["kind"] is None:
            continue
        oi = _number(row.get("open_interest")) or 0.0
        if parsed["kind"] == "call":
            calls += oi
        else:
            puts += oi
        iv, underlying = _number(row.get("mark_iv")), _number(row.get("underlying_price"))
        if iv is None or iv <= 0 or underlying is None or parsed["expiry_ms"] <= now_ms:
            continue
        group = expiries.setdefault(parsed["expiry_ms"], {"underlying": underlying, "strikes": {}})
        group["strikes"].setdefault(parsed["strike"], []).append(iv)

    term = []
    for expiry_ms, group in sorted(expiries.items()):
        strike = min(group["strikes"], key=lambda k: abs(k - group["underlying"]))
        ivs = group["strikes"][strike]
        term.append({
            "expiry": _date(expiry_ms),
            "days": round((expiry_ms - now_ms) / DAY_MS, 1),
            "atm_strike": strike,
            "atm_iv": round(sum(ivs) / len(ivs), 2),
        })
    return {
        "call_open_interest": round(calls, 2),
        "put_open_interest": round(puts, 2),
        "put_call_ratio": round(puts / calls, 3) if calls > 0 else None,
        "term_structure": term,
    }


async def _call(method: str, **params):
    try:
        response = await get_client().get(f"{config.DERIBIT_API_URL}/public/{method}", params=params)
    except httpx.HTTPError as exc:
        raise DeribitError(f"Could not reach Deribit ({type(exc).__name__})") from None
    if response.status_code == 429:
        raise DeribitError("Deribit is rate-limiting requests")
    if response.status_code != 200:
        raise DeribitError(f"Deribit answered {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        raise DeribitError("Deribit sent a response that is not JSON") from None
    if not isinstance(body, dict) or "result" not in body:
        raise DeribitError("Deribit sent data in an unexpected shape")
    return body["result"]


async def _fetch(currency: str) -> dict:
    now_ms = _wall() * 1000
    perpetual = f"{currency}-PERPETUAL"
    dvol, ticker, funding, futures, options = await asyncio.gather(
        _call("get_volatility_index_data", currency=currency, resolution="1D",
              start_timestamp=int(now_ms - DVOL_DAYS * DAY_MS), end_timestamp=int(now_ms)),
        _call("ticker", instrument_name=perpetual),
        _call("get_funding_rate_history", instrument_name=perpetual,
              start_timestamp=int(now_ms - FUNDING_DAYS * DAY_MS), end_timestamp=int(now_ms)),
        _call("get_book_summary_by_currency", currency=currency, kind="future"),
        _call("get_book_summary_by_currency", currency=currency, kind="option"),
    )
    if not isinstance(dvol, dict) or not isinstance(ticker, dict):
        raise DeribitError("Deribit sent data in an unexpected shape")
    perp = funding_summary(ticker, funding)
    return {
        "currency": currency,
        "dvol": dvol_summary(dvol.get("data")),
        "perpetual": {"instrument": perpetual, **perp},
        "futures": futures_curve(futures, perp["index_price"], now_ms),
        "options": options_summary(options, now_ms),
        "source_timestamp": _number(ticker.get("timestamp")),
    }


def _meta(entry: _Entry, status: str, notes: list[str]) -> dict:
    stamp = entry.body.get("source_timestamp")
    return SourceMeta(
        provider=PROVIDER,
        endpoint=urlparse(config.DERIBIT_API_URL).netloc or None,
        status=status,
        retrieved_at=datetime.fromtimestamp(entry.fetched_wall, tz=timezone.utc),
        source_timestamp=datetime.fromtimestamp(stamp / 1000, tz=timezone.utc) if stamp else None,
        cache_age_seconds=round(_monotonic() - entry.fetched_mono, 1),
        notes=notes,
    ).model_dump(mode="json")


async def derivatives(currency: str) -> dict:
    """The derivatives summary for one coin, from cache when fresh. Raises DeribitError."""
    cached = _cache.get(currency)
    if cached and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
        return {**cached.body, "meta": _meta(cached, "real_time", [])}
    # One fetch per coin at a time: viewers arriving together share it.
    async with _locks.setdefault(currency, asyncio.Lock()):
        cached = _cache.get(currency)
        if cached and _monotonic() - cached.fetched_mono < CACHE_SECONDS:
            return {**cached.body, "meta": _meta(cached, "real_time", [])}
        try:
            body = await _fetch(currency)
        except DeribitError as exc:
            if cached and _monotonic() - cached.fetched_mono <= STALE_MAX_SECONDS:
                log.warning("Serving cached Deribit %s data: %s", currency, exc)
                return {**cached.body, "meta": _meta(cached, "cached", [f"Deribit unavailable, showing the last response. {exc}"])}
            raise
        entry = _Entry(body, _monotonic(), _wall())
        _cache[currency] = entry
        return {**body, "meta": _meta(entry, "real_time", [])}


@router.get("/derivatives")
async def derivatives_route(currency: str = Query("BTC", pattern="^(BTC|ETH)$")):
    """DVOL, funding, the futures curve and options positioning for BTC or ETH (Deribit)."""
    if not config.DERIBIT_ENABLED:
        raise HTTPException(status_code=503, detail="Deribit derivatives data is turned off (DERIBIT_ENABLED=false)")
    try:
        return await derivatives(currency)
    except DeribitError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
