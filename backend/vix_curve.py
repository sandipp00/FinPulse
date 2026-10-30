"""The VIX term structure: Cboe's volatility indices for five horizons, from Yahoo.

Each index is the stock market's expected volatility (S&P 500 options, annualized,
in points) over a different horizon: 9 days, 30 days (the VIX), 3 months, 6 months
and a year. Normally the longer horizons are higher (contango: calm now, uncertainty
further out). When near-term fear spikes, the short end rises above the long end
(backwardation). The usual gauge is VIX3M / VIX: above 1 is contango.

Values come from Yahoo's chart API (personal use), the same as the VIX elsewhere in
FinPulse; Cboe's own data is not used, since its terms require consent to store and
display it. Yahoo has only today's value for the 1-year index, so it has no history.
The whole answer is cached for CACHE_SECONDS.
"""
import asyncio
import time
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from backend import yahoo_history
from backend.analysis_api import to_closes

router = APIRouter(prefix="/api/vix-curve", tags=["vix"])

CACHE_SECONDS = 60
DAILY_BARS = 600
# symbol, label, horizon in days.
TENORS = [("^VIX9D", "9 days", 9), ("^VIX", "30 days (VIX)", 30), ("^VIX3M", "3 months", 93),
          ("^VIX6M", "6 months", 182), ("^VIX1Y", "1 year", 365)]
CONTANGO_BAND = 0.03  # a ratio within 3% of 1 is called flat

_monotonic = time.monotonic
_cache: Optional[tuple[float, dict]] = None
_lock: Optional[asyncio.Lock] = None


def clear_cache() -> None:
    global _cache
    _cache = None


def shape(ratio: Optional[float]) -> Optional[str]:
    """'contango', 'flat' or 'backwardation' from VIX3M / VIX."""
    if ratio is None:
        return None
    if ratio > 1 + CONTANGO_BAND:
        return "contango"
    if ratio < 1 - CONTANGO_BAND:
        return "backwardation"
    return "flat"


def ratio_history(vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    """VIX3M / VIX on the days both have a completed close."""
    joined = pd.concat([vix.rename("vix"), vix3m.rename("vix3m")], axis=1, join="inner").dropna()
    joined = joined[joined["vix"] > 0]
    return (joined["vix3m"] / joined["vix"]).round(4)


def percentile(value: float, history: pd.Series) -> Optional[int]:
    if history.empty:
        return None
    return round(float((history <= value).mean()) * 100)


async def _load(symbol: str) -> tuple[Optional[dict], pd.Series, Optional[str]]:
    """(latest point, completed daily closes, error) for one index."""
    try:
        candles, meta = await yahoo_history.fetch_candle_series(symbol, "1d", DAILY_BARS)
    except yahoo_history.YahooHistoryError as exc:
        return None, pd.Series(dtype=float), str(exc)
    if not candles:
        return None, pd.Series(dtype=float), "no values"
    last = candles[-1]
    # Yahoo stamps a daily bar at its session's open; the trading date is the meaningful part.
    stamp = pd.Timestamp(last["time"], unit="s", tz="UTC")
    day = (stamp.tz_convert(meta.exchange_timezone) if meta.exchange_timezone else stamp).date().isoformat()
    latest = {"value": round(float(last["close"]), 2), "date": day}
    return latest, to_closes(candles, meta.exchange_timezone), None


async def _build() -> dict:
    results = await asyncio.gather(*(_load(symbol) for symbol, _, _ in TENORS))
    curve, closes, errors = [], {}, []
    for (symbol, label, days), (latest, series, error) in zip(TENORS, results):
        closes[symbol] = series
        if error:
            errors.append(f"{symbol}: {error}")
        curve.append({"symbol": symbol, "label": label, "days": days,
                      "value": latest["value"] if latest else None, "date": latest["date"] if latest else None,
                      "history_days": len(series)})
    if all(point["value"] is None for point in curve):
        raise HTTPException(status_code=502, detail="Yahoo has no VIX values right now: " + "; ".join(errors))

    values = {p["symbol"]: p["value"] for p in curve}
    ratio = round(values["^VIX3M"] / values["^VIX"], 4) if values.get("^VIX") and values.get("^VIX3M") else None
    history = ratio_history(closes["^VIX"], closes["^VIX3M"])
    return {
        "curve": curve,
        "ratio": ratio,
        "shape": shape(ratio),
        "ratio_percentile": percentile(ratio, history) if ratio is not None else None,
        "ratio_backwardation_share": round(float((history < 1).mean()) * 100) if not history.empty else None,
        "ratio_history": [{"time": d.date().isoformat(), "value": float(v)} for d, v in history.items()],
        "errors": errors,
        "provider": "yahoo",
        "notes": [
            "Cboe volatility indices (expected S&P 500 volatility, annualized, in points) via Yahoo Finance; "
            "Yahoo runs the VIX about 15 minutes behind. The 1-year index has no history on Yahoo.",
            "VIX3M / VIX above 1 (contango) is the usual state: calm now, more uncertainty further out. Below 1 "
            "(backwardation) means near-term fear is higher than longer-term fear, as in sell-offs.",
            "A description of option prices, not a forecast.",
        ],
    }


@router.get("")
async def vix_curve():
    """The five-horizon VIX curve now, VIX3M / VIX and its history."""
    global _cache, _lock
    _lock = _lock or asyncio.Lock()
    async with _lock:
        if _cache and _monotonic() - _cache[0] < CACHE_SECONDS:
            return _cache[1]
        body = await _build()
        _cache = (_monotonic(), body)
        return body
