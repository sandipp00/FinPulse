"""Fama-French factors (Kenneth R. French Data Library) and each US stock's exposure to them.

Two daily files, in percent: the three research factors with the risk-free rate
(Mkt-RF, SMB, HML, RF) and momentum (Mom). They are free to download, published
monthly with a lag of about a month, and can be revised; they are cached for
CACHE_SECONDS and kept for STALE_MAX_SECONDS when the library cannot be reached.

GET /api/factors?symbol=NVDA regresses the stock's daily excess return on the four
factors over the last WINDOW_DAYS trading days the two share (src/analytics/factor_model).
The asset's daily closes come from Yahoo, dated in the exchange's time zone.
"""
import asyncio
import io
import logging
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend import config, yahoo_history
from backend.analysis_api import YAHOO_DAILY_BARS, to_closes
from backend.stocks import STOCK_SYMBOLS
from src.analytics import factor_model

log = logging.getLogger("finpulse.famafrench")

router = APIRouter(prefix="/api/factors", tags=["factors"])

PROVIDER = "famafrench"
LIBRARY_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"
FILES = ("F-F_Research_Data_Factors_daily_CSV.zip", "F-F_Momentum_Factor_daily_CSV.zip")
CACHE_SECONDS = 24 * 3600
STALE_MAX_SECONDS = 45 * 86_400
REQUEST_TIMEOUT_SECONDS = 30
WINDOW_DAYS = 756  # about three years of trading days
# US stocks and the US indices the factors describe; they are built from US stocks.
SYMBOLS = (*STOCK_SYMBOLS, "^GSPC", "^DJI", "^IXIC", "^RUT", "^NYA")
MISSING = (-99.99, -999.0)

_monotonic = time.monotonic
_wall = time.time


class FactorError(Exception):
    pass


@dataclass
class _Factors:
    frame: pd.DataFrame
    fetched_mono: float
    fetched_wall: float


_cache: Optional[_Factors] = None
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


def parse_daily_csv(text: str) -> pd.DataFrame:
    """A library CSV -> its daily table (dates as the index, columns as named).

    The file has a free-text header, then a ",Name1,Name2" line and YYYYMMDD rows;
    the daily table ends at the first line that is not a dated row. Missing values
    (-99.99, -999) become NaN.
    """
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(","))
    except StopIteration:
        raise FactorError("The factor file has no table") from None
    columns = [c.strip() for c in lines[start].split(",")[1:]]
    rows, index = [], []
    for line in lines[start + 1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(columns) + 1 or not (len(parts[0]) == 8 and parts[0].isdigit()):
            break
        try:
            values = [float(p) for p in parts[1:]]
        except ValueError:
            break
        index.append(pd.Timestamp(parts[0]))
        rows.append([None if v in MISSING else v for v in values])
    if not rows:
        raise FactorError("The factor file has no daily rows")
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index), columns=columns, dtype=float)


async def _download(name: str) -> pd.DataFrame:
    url = f"{config.FAMA_FRENCH_URL}/{name}"
    try:
        response = await get_client().get(url)
    except httpx.HTTPError as exc:
        raise FactorError(f"Could not reach the Kenneth French Data Library ({type(exc).__name__})") from None
    if response.status_code != 200:
        raise FactorError(f"The Kenneth French Data Library answered {response.status_code}")
    try:
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        text = archive.read(archive.namelist()[0]).decode("latin-1")
    except (zipfile.BadZipFile, IndexError, KeyError) as exc:
        raise FactorError(f"The factor file {name} could not be opened") from exc
    return parse_daily_csv(text)


async def factors() -> tuple[pd.DataFrame, Optional[str]]:
    """The daily factors (Mkt-RF, SMB, HML, RF, Mom) and a staleness note, or FactorError."""
    global _cache, _lock
    _lock = _lock or asyncio.Lock()
    async with _lock:
        if _cache and _monotonic() - _cache.fetched_mono < CACHE_SECONDS:
            return _cache.frame, None
        try:
            three, momentum = await asyncio.gather(*(_download(name) for name in FILES))
        except FactorError as exc:
            if _cache and _monotonic() - _cache.fetched_mono <= STALE_MAX_SECONDS:
                log.warning("Serving cached Fama-French factors: %s", exc)
                return _cache.frame, str(exc)
            raise
        frame = three.join(momentum, how="inner").dropna()
        if not set(factor_model.FACTORS) | {"RF"} <= set(frame.columns):
            raise FactorError("The factor files are missing expected columns")
        _cache = _Factors(frame, _monotonic(), _wall())
        return frame, None


async def asset_returns(symbol: str) -> pd.Series:
    """Daily simple returns in percent from Yahoo's completed daily closes."""
    candles, meta = await yahoo_history.fetch_candle_series(symbol, "1d", YAHOO_DAILY_BARS)
    closes = to_closes(candles, meta.exchange_timezone)
    return closes.pct_change().dropna() * 100


NOTES = [
    "Factors: Kenneth R. French Data Library (Fama and French, 1993; momentum, Carhart 1997), daily, in percent. "
    "Published monthly with a lag, so the window ends at the factors' latest date.",
    "Market: the stock market's excess return. Size (SMB): small minus big companies. Value (HML): cheap minus "
    "expensive companies by book-to-market. Momentum: recent winners minus recent losers.",
    "A beta of 1.2 on the market means the asset moved 1.2% for each 1% excess move of the market, holding the other "
    "factors fixed. |t| above about 2 means the exposure is unlikely to be chance.",
    "Asset returns are price returns from Yahoo, without dividends (the factors include them), so alpha reads low "
    "by roughly the dividend yield. A description of the past window, not a forecast.",
]


@router.get("")
async def factor_exposure(symbol: str = Query(..., max_length=10)):
    """How one US stock or index moved with the market, size, value and momentum factors."""
    if not config.FAMA_FRENCH_ENABLED:
        raise HTTPException(status_code=503, detail="Factor exposure is turned off (FAMA_FRENCH_ENABLED=false)")
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Factor exposure covers the US stocks and US indices, not {symbol}")
    try:
        frame, stale = await factors()
    except FactorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        returns = await asset_returns(symbol)
    except yahoo_history.YahooHistoryError as exc:
        raise HTTPException(status_code=502, detail=f"Yahoo history for {symbol} is unavailable: {exc}") from exc
    shared = returns.index.intersection(frame.index)
    window = returns.loc[shared].sort_index().tail(WINDOW_DAYS)
    fit = factor_model.regress(window, frame)
    if fit is None:
        raise HTTPException(status_code=422, detail=f"Not enough shared daily history for {symbol}")
    return {
        "symbol": symbol,
        **fit,
        "factors_through": frame.index[-1].date().isoformat(),
        "fetched_at": datetime.fromtimestamp(_cache.fetched_wall, tz=timezone.utc).isoformat() if _cache else None,
        "stale": stale,
        "provider": PROVIDER,
        "source_url": LIBRARY_URL,
        "notes": NOTES,
    }
