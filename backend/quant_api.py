"""Benchmark-relative statistics for two instruments (src/analytics/quant.py).

Daily closes come from the same place as the instrument explorer
(backend/instruments.py): Binance for live crypto, stored history otherwise, with
each series' source and metadata passed through.
"""
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend import instruments
from src.analytics import quant

router = APIRouter(prefix="/api/quant", tags=["quant"])

HISTORY_BARS = 1000

METHODOLOGY = {
    "alignment": "Both series are compared on the dates they share; returns are taken between those dates.",
    "beta": "cov(r_asset, r_benchmark) / var(r_benchmark), sample (n-1) estimates.",
    "correlation": "Pearson correlation of daily returns on shared dates.",
    "annualized_return": "(last / first) ** (365.25 / calendar days) - 1 over the shared window.",
    "excess_return": "Asset's annualized return minus the benchmark's.",
    "tracking_error": "Standard deviation of (r_asset - r_benchmark), annualized with sqrt(periods per year).",
    "information_ratio": "Mean of (r_asset - r_benchmark) x periods per year / tracking error.",
    "periods_per_year": "365 when both series are crypto (trading every day), otherwise 252.",
    "caveat": "These describe how the two series moved together in the past. Correlation is not causation, "
              "and none of it predicts future returns.",
}


def _pct(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(value * 100, digits)


def _num(value: Optional[float], digits: int = 3) -> Optional[float]:
    return None if value is None else round(value, digits)


def _day(ts) -> Optional[str]:
    return None if ts is None else pd.Timestamp(ts).strftime("%Y-%m-%d")


def _closes(history: dict) -> pd.Series:
    candles = history["candles"]
    index = pd.to_datetime([c["time"] for c in candles], unit="s", utc=True)
    return pd.Series([c["close"] for c in candles], index=index, dtype=float)


def _single(closes: pd.Series, periods: int) -> dict:
    stats = quant.drawdown_stats(closes)
    return {
        "annualized_return_pct": _pct(quant.annualized_return(closes)),
        "volatility_pct": _pct(quant.annualized_volatility(quant.simple_returns(closes), periods)),
        "max_drawdown_pct": _pct(stats.max_drawdown),
        "drawdown_peak": _day(stats.peak_date),
        "drawdown_trough": _day(stats.trough_date),
        "drawdown_recovery": _day(stats.recovery_date),
        "drawdown_days": stats.duration_days,
        "recovered": stats.recovered,
    }


@router.get("/relative")
async def relative(
    symbol: str = Query(..., min_length=1, max_length=32),
    benchmark: str = Query(..., min_length=1, max_length=32),
    window: int = Query(default=60, ge=20, le=250, description="Rolling window, in shared trading days"),
):
    """How `symbol` moved against `benchmark` over their shared daily history."""
    if symbol == benchmark:
        raise HTTPException(status_code=400, detail="Choose two different instruments.")
    catalogue = instruments.catalogue()
    for name in (symbol, benchmark):
        if name not in catalogue:
            raise HTTPException(status_code=404, detail=f"Unknown instrument: {name}")

    histories = {}
    for name in (symbol, benchmark):
        histories[name] = await instruments.history(symbol=name, interval="1d", limit=HISTORY_BARS, source="auto")

    periods = quant.periods_for(catalogue[symbol].asset_class, catalogue[benchmark].asset_class)
    joined = quant.align({symbol: _closes(histories[symbol]), benchmark: _closes(histories[benchmark])})
    stats = quant.relative_stats(joined[symbol], joined[benchmark], periods)

    rolling = []
    if stats.overlap > window:
        returns = joined.pct_change().dropna()
        corr = quant.rolling_correlation(returns[symbol], returns[benchmark], window)
        vol_a = quant.rolling_volatility(returns[symbol], window, periods)
        vol_b = quant.rolling_volatility(returns[benchmark], window, periods)
        frame = pd.DataFrame({"correlation": corr, "asset": vol_a, "benchmark": vol_b}).dropna()
        rolling = [
            {"date": _day(day), "correlation": round(float(row.correlation), 4),
             "asset_volatility_pct": round(float(row.asset) * 100, 2),
             "benchmark_volatility_pct": round(float(row.benchmark) * 100, 2)}
            for day, row in frame.iterrows()
        ]

    window_note = None
    if stats.overlap < quant.MIN_OVERLAP:
        window_note = f"Only {stats.overlap} shared dates; at least {quant.MIN_OVERLAP} are needed."

    return {
        "symbol": symbol,
        "benchmark": benchmark,
        "window": window,
        "periods_per_year": periods,
        "overlap": stats.overlap,
        "start_date": _day(stats.start_date),
        "end_date": _day(stats.end_date),
        "note": window_note,
        "metrics": {
            "correlation": _num(stats.correlation),
            "r_squared": _num(stats.r_squared),
            "beta": _num(stats.beta),
            "asset_return_pct": _pct(stats.asset_return),
            "benchmark_return_pct": _pct(stats.benchmark_return),
            "excess_return_pct": _pct(stats.excess_return),
            "tracking_error_pct": _pct(stats.tracking_error),
            "information_ratio": _num(stats.information_ratio, 2),
        },
        "assets": {
            symbol: _single(joined[symbol], periods) if stats.overlap >= 2 else None,
            benchmark: _single(joined[benchmark], periods) if stats.overlap >= 2 else None,
        },
        "rolling": rolling,
        "sources": {
            name: {"source": h["source"], "currency": h["currency"], "meta": h["meta"]}
            for name, h in histories.items()
        },
        "methodology": METHODOLOGY,
    }
