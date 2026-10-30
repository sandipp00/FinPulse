"""Commitments of Traders: how speculators are positioned in key futures, weekly, from the CFTC.

The CFTC publishes each Tuesday's positions on Friday (public domain; the CFTC asks
to be acknowledged). Two of its reports, from its public reporting API (Socrata, no
key), cover the markets here:
  * Disaggregated (72hh-3qpy) for metals and energy: "managed money", i.e. hedge
    funds and commodity trading advisers;
  * Traders in Financial Futures (gpe5-46if) for stock indices, crypto, currencies
    and Treasuries: "leveraged funds" (hedge funds), with "asset managers" alongside.

Net = long - short contracts (spreads left out). Where today's net sits among the
last three years' weekly values is a percentile. Two requests per refresh, cached
CACHE_SECONDS (the data changes once a week); the last good answer is kept for
STALE_MAX_SECONDS when the CFTC fails.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException

from backend import config

log = logging.getLogger("finpulse.cftc")

router = APIRouter(prefix="/api/cftc", tags=["cftc"])

PROVIDER = "cftc"
SOURCE_URL = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"
CACHE_SECONDS = 6 * 3600
STALE_MAX_SECONDS = 14 * 86_400
REQUEST_TIMEOUT_SECONDS = 30
HISTORY_WEEKS = 156
DISAGGREGATED, FINANCIAL = "72hh-3qpy", "gpe5-46if"

# id, name, CFTC contract code, report, group, the FinPulse asset it relates to.
MARKETS = [
    ("gold", "Gold (COMEX)", "088691", DISAGGREGATED, "Metals & energy", "gold"),
    ("silver", "Silver (COMEX)", "084691", DISAGGREGATED, "Metals & energy", "silver"),
    ("wti", "WTI crude oil (NYMEX)", "067651", DISAGGREGATED, "Metals & energy", "wti"),
    ("natgas", "Natural gas (NYMEX)", "023651", DISAGGREGATED, "Metals & energy", None),
    ("spx", "E-mini S&P 500", "13874A", FINANCIAL, "Stock indices", "spx"),
    ("ndx", "E-mini Nasdaq-100", "209742", FINANCIAL, "Stock indices", "ixic"),
    ("btc", "Bitcoin (CME)", "133741", FINANCIAL, "Crypto", "btc"),
    ("eth", "Ether (CME)", "146021", FINANCIAL, "Crypto", "eth"),
    ("eur", "Euro FX", "099741", FINANCIAL, "Currencies", "eurusd"),
    ("jpy", "Japanese yen", "097741", FINANCIAL, "Currencies", "usdjpy"),
    ("gbp", "British pound", "096742", FINANCIAL, "Currencies", "gbpusd"),
    ("ust10", "10-year Treasury note", "043602", FINANCIAL, "Rates", None),
]
GROUPS = ("Metals & energy", "Stock indices", "Crypto", "Currencies", "Rates")
# Who counts as "speculators" in each report, and its long/short fields.
SPECULATORS = {
    DISAGGREGATED: ("Managed money", "m_money_positions_long_all", "m_money_positions_short_all"),
    FINANCIAL: ("Leveraged funds", "lev_money_positions_long", "lev_money_positions_short"),
}
ASSET_MANAGERS = ("asset_mgr_positions_long", "asset_mgr_positions_short")

_monotonic = time.monotonic
_wall = time.time


class CftcError(Exception):
    pass


@dataclass
class _Entry:
    body: dict
    fetched_mono: float
    fetched_wall: float


_cache: Optional[_Entry] = None
_lock: Optional[asyncio.Lock] = None
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
    global _cache
    _cache = None


def _int(value) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _net(row: dict, long_key: str, short_key: str) -> Optional[int]:
    long_, short = _int(row.get(long_key)), _int(row.get(short_key))
    return None if long_ is None or short is None else long_ - short


def percentile(value: int, history: list[int]) -> Optional[int]:
    """Share of the history at or below `value`, in percent: 100 is the most net-long in the window."""
    if not history:
        return None
    return round(sum(v <= value for v in history) / len(history) * 100)


def summarize(market: tuple, rows: list[dict]) -> Optional[dict]:
    """One market's weekly rows (any order) -> its latest positioning, change and history."""
    id_, name, code, report, group, asset = market
    label, long_key, short_key = SPECULATORS[report]
    weeks = []
    for row in rows:
        net = _net(row, long_key, short_key)
        day = str(row.get("report_date_as_yyyy_mm_dd", ""))[:10]
        if net is not None and len(day) == 10:
            weeks.append((day, net, row))
    if not weeks:
        return None
    weeks.sort(key=lambda w: w[0])
    day, net, row = weeks[-1]
    open_interest = _int(row.get("open_interest_all"))
    history = [n for _, n, _ in weeks]
    latest = {
        "date": day,
        "long": _int(row.get(long_key)),
        "short": _int(row.get(short_key)),
        "net": net,
        "net_pct_open_interest": round(net / open_interest * 100, 1) if open_interest else None,
        "change_1w": net - weeks[-2][1] if len(weeks) > 1 else None,
        "open_interest": open_interest,
    }
    if report == FINANCIAL:
        latest["asset_managers_net"] = _net(row, *ASSET_MANAGERS)
    return {
        "id": id_, "name": name, "code": code, "group": group, "asset": asset,
        "traders": label, "units": row.get("contract_units"),
        "latest": latest,
        "percentile_3y": percentile(net, history),
        "range_3y": {"min": min(history), "max": max(history), "weeks": len(history)},
        "history": [{"time": d, "value": n} for d, n, _ in weeks],
    }


async def _report(dataset: str, codes: list[str], since: str) -> list[dict]:
    quoted = ",".join(f"'{c}'" for c in codes)
    params = {
        "$where": f"cftc_contract_market_code in({quoted}) and report_date_as_yyyy_mm_dd >= '{since}'",
        "$order": "report_date_as_yyyy_mm_dd", "$limit": 5000,
    }
    try:
        response = await get_client().get(f"{config.CFTC_API_URL}/{dataset}.json", params=params)
    except httpx.HTTPError as exc:
        raise CftcError(f"Could not reach the CFTC ({type(exc).__name__})") from None
    if response.status_code == 429:
        raise CftcError("The CFTC is rate-limiting requests")
    if response.status_code != 200:
        raise CftcError(f"The CFTC answered {response.status_code}")
    try:
        rows = response.json()
    except ValueError:
        raise CftcError("The CFTC sent a response that is not JSON") from None
    if not isinstance(rows, list):
        raise CftcError("The CFTC sent data in an unexpected shape")
    return rows


async def _fetch() -> dict:
    since = (datetime.now(timezone.utc) - timedelta(weeks=HISTORY_WEEKS)).date().isoformat()
    datasets = (DISAGGREGATED, FINANCIAL)
    results = await asyncio.gather(*(
        _report(ds, [m[2] for m in MARKETS if m[3] == ds], since) for ds in datasets
    ))
    by_code: dict[str, list[dict]] = {}
    for rows in results:
        for row in rows:
            if isinstance(row, dict):
                by_code.setdefault(row.get("cftc_contract_market_code"), []).append(row)
    markets = [m for m in (summarize(market, by_code.get(market[2], [])) for market in MARKETS) if m]
    if not markets:
        raise CftcError("The CFTC returned no positions for the followed markets")
    return {"markets": markets, "as_of": max(m["latest"]["date"] for m in markets)}


async def report() -> dict:
    """The positioning summary, from cache when fresh. Raises CftcError with no usable copy."""
    global _cache, _lock
    _lock = _lock or asyncio.Lock()
    async with _lock:
        if _cache and _monotonic() - _cache.fetched_mono < CACHE_SECONDS:
            return _stamp(_cache, None)
        try:
            body = await _fetch()
        except CftcError as exc:
            if _cache and _monotonic() - _cache.fetched_mono <= STALE_MAX_SECONDS:
                log.warning("Serving cached CFTC positions: %s", exc)
                return _stamp(_cache, str(exc))
            raise
        _cache = _Entry(body, _monotonic(), _wall())
        return _stamp(_cache, None)


NOTES = [
    "Source: U.S. Commodity Futures Trading Commission, Commitments of Traders (futures only). Positions are as of "
    "each Tuesday and published on Friday.",
    "Net = long minus short contracts held by the speculative group shown (managed money for metals and energy, "
    "leveraged funds for financial futures). The 3-year percentile says where this week's net sits among the last "
    "three years' weekly values: 100 is the most net-long (most bullish), 0 the most net-short. It is relative "
    "to the market's own history, so a market can be at its most bullish while still net short.",
    "Currency futures are priced in dollars per foreign unit: net long yen means betting the yen rises against the "
    "dollar, i.e. USD/JPY falls.",
    "Positioning describes who holds what. It is not a forecast; crowded positions can stay crowded.",
]


def _stamp(entry: _Entry, stale: Optional[str]) -> dict:
    return {
        **entry.body,
        "groups": list(GROUPS),
        "provider": PROVIDER,
        "source_url": SOURCE_URL,
        "fetched_at": datetime.fromtimestamp(entry.fetched_wall, tz=timezone.utc).isoformat(),
        "stale": stale,
        "notes": NOTES,
    }


@router.get("")
async def cftc_positions():
    """Speculative positioning in 12 futures markets, latest week and three years of history."""
    if not config.CFTC_ENABLED:
        raise HTTPException(status_code=503, detail="CFTC positioning is turned off (CFTC_ENABLED=false)")
    try:
        return await report()
    except CftcError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
