"""Return, risk and benchmark-relative measures for daily closing prices.

Every function here is descriptive and deterministic: it summarizes the data it is
given and predicts nothing. Formulas and assumptions are listed in
docs/METHODOLOGY.md; the key ones:

  * Simple return r_t = P_t / P_{t-1} - 1; log return l_t = ln(P_t / P_{t-1}).
  * Annualized return (CAGR) uses calendar time: (P_end / P_start) ** (365.25 / days) - 1,
    so it means the same thing for a 7-day crypto series and a weekday stock series.
  * Volatility, tracking error and the information ratio annualize with the
    observation frequency: 365 periods a year when every series in the calculation
    trades daily (crypto), otherwise 252.
  * Two assets are compared only on the dates both have, and returns are taken
    between those shared dates, so both cover the same holding periods.
  * Standard deviations and covariances use the sample formula (ddof=1).

When a measure is undefined (too little data, a zero variance, no overlap) the
result is None, never a filler number.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src.analytics.risk import normalize_daily

DAYS_PER_YEAR = 365.25
MIN_OVERLAP = 30
MIN_DAYS_FOR_CAGR = 30


def _finite(value) -> Optional[float]:
    return float(value) if value is not None and np.isfinite(value) else None


def periods_for(*asset_types: str) -> int:
    """365 if every series is crypto (trades daily), else 252 trading days."""
    return 365 if asset_types and all(str(t).lower() == "crypto" for t in asset_types) else 252


# ---- returns -------------------------------------------------------------------

def simple_returns(closes: pd.Series) -> pd.Series:
    return closes.pct_change().dropna()


def log_returns(closes: pd.Series) -> pd.Series:
    return np.log(closes / closes.shift(1)).dropna()


def total_return(closes: pd.Series) -> Optional[float]:
    """P_end / P_start - 1, as a fraction."""
    closes = closes.dropna()
    if len(closes) < 2 or closes.iloc[0] <= 0:
        return None
    return _finite(closes.iloc[-1] / closes.iloc[0] - 1)


def annualized_return(closes: pd.Series) -> Optional[float]:
    """Compound annual growth rate over the calendar time the series covers.

    None for spans shorter than MIN_DAYS_FOR_CAGR days, where annualizing would
    turn a few days' move into a meaningless yearly figure.
    """
    closes = closes.dropna()
    if len(closes) < 2 or closes.iloc[0] <= 0 or closes.iloc[-1] <= 0:
        return None
    days = (closes.index[-1] - closes.index[0]).days
    if days < MIN_DAYS_FOR_CAGR:
        return None
    return _finite((closes.iloc[-1] / closes.iloc[0]) ** (DAYS_PER_YEAR / days) - 1)


def annualized_volatility(returns: pd.Series, periods: int) -> Optional[float]:
    returns = returns.dropna()
    if len(returns) < 2:
        return None
    return _finite(returns.std(ddof=1) * np.sqrt(periods))


def rolling_volatility(returns: pd.Series, window: int, periods: int) -> pd.Series:
    """Annualized volatility over each trailing window; NaN until the window is full."""
    return returns.rolling(window).std(ddof=1) * np.sqrt(periods)


# ---- drawdowns ---------------------------------------------------------------

def drawdown_series(closes: pd.Series) -> pd.Series:
    """Fall from the running peak, as a fraction (0 at a new high, negative below it)."""
    return closes / closes.cummax() - 1


@dataclass
class DrawdownStats:
    max_drawdown: Optional[float]
    peak_date: Optional[pd.Timestamp]
    trough_date: Optional[pd.Timestamp]
    recovery_date: Optional[pd.Timestamp]
    duration_days: Optional[int]  # peak to recovery, or peak to the last date if not recovered
    recovered: bool


def drawdown_stats(closes: pd.Series) -> DrawdownStats:
    """The deepest drawdown: where it peaked, bottomed and (if it did) recovered."""
    closes = closes.dropna()
    if len(closes) < 2:
        return DrawdownStats(None, None, None, None, None, False)

    drawdown = drawdown_series(closes)
    trough = drawdown.idxmin()
    depth = float(drawdown.loc[trough])
    if depth >= 0:
        return DrawdownStats(0.0, None, None, None, 0, True)

    peak = closes.loc[:trough].idxmax()
    after = closes.loc[trough:]
    recovered_at = after[after >= closes.loc[peak]]
    recovery = recovered_at.index[0] if len(recovered_at) else None
    end = recovery if recovery is not None else closes.index[-1]
    return DrawdownStats(depth, peak, trough, recovery, int((end - peak).days), recovery is not None)


# ---- comparing two assets ----------------------------------------------------

def align(closes_by_symbol: dict[str, pd.Series]) -> pd.DataFrame:
    """Daily closes on the dates every series has (one column per symbol)."""
    frames = {symbol: normalize_daily(closes) for symbol, closes in closes_by_symbol.items()}
    return pd.concat(frames, axis=1, join="inner").dropna()


def rolling_correlation(asset_returns: pd.Series, benchmark_returns: pd.Series, window: int) -> pd.Series:
    """Pearson correlation of the two return series over each trailing window."""
    return asset_returns.rolling(window).corr(benchmark_returns)


@dataclass
class RelativeStats:
    overlap: int
    start_date: Optional[pd.Timestamp]
    end_date: Optional[pd.Timestamp]
    periods_per_year: int
    correlation: Optional[float]
    r_squared: Optional[float]
    beta: Optional[float]
    asset_return: Optional[float]
    benchmark_return: Optional[float]
    excess_return: Optional[float]  # difference of the two annualized returns
    tracking_error: Optional[float]
    information_ratio: Optional[float]


def relative_stats(asset: pd.Series, benchmark: pd.Series, periods: int) -> RelativeStats:
    """How `asset` moved relative to `benchmark` on their shared dates.

    beta = cov(r_a, r_b) / var(r_b); tracking error = sd(r_a - r_b) * sqrt(periods);
    information ratio = mean(r_a - r_b) * periods / tracking error. Measures need at
    least MIN_OVERLAP shared dates; with fewer, every measure is None.
    """
    joined = align({"asset": asset, "benchmark": benchmark})
    overlap = len(joined)
    empty = RelativeStats(overlap, None, None, periods, None, None, None, None, None, None, None, None)
    if overlap < MIN_OVERLAP:
        return empty

    returns = joined.pct_change().dropna()
    ra, rb = returns["asset"], returns["benchmark"]
    var_b = rb.var(ddof=1)
    beta = _finite(ra.cov(rb, ddof=1) / var_b) if var_b > 0 else None
    correlation = _finite(ra.corr(rb)) if ra.std(ddof=1) > 0 and rb.std(ddof=1) > 0 else None

    active = ra - rb
    te_daily = active.std(ddof=1)
    tracking_error = _finite(te_daily * np.sqrt(periods)) if te_daily > 0 else None
    information_ratio = (
        _finite(active.mean() * periods / tracking_error) if tracking_error else None
    )

    asset_return = annualized_return(joined["asset"])
    benchmark_return = annualized_return(joined["benchmark"])
    excess = asset_return - benchmark_return if asset_return is not None and benchmark_return is not None else None

    return RelativeStats(
        overlap=overlap,
        start_date=joined.index[0],
        end_date=joined.index[-1],
        periods_per_year=periods,
        correlation=correlation,
        r_squared=correlation ** 2 if correlation is not None else None,
        beta=beta,
        asset_return=asset_return,
        benchmark_return=benchmark_return,
        excess_return=_finite(excess) if excess is not None else None,
        tracking_error=tracking_error,
        information_ratio=information_ratio,
    )
