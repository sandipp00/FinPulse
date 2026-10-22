"""Risk measures computed from daily closing prices.

Everything here is descriptive: it summarizes how an asset behaved in the data
provided. None of it predicts what will happen next.
"""
import numpy as np
import pandas as pd

from src.analytics.financial_metrics import (
    annualized_volatility,
    max_drawdown,
    periods_per_year,
    sharpe_ratio,
)

MIN_OBSERVATIONS = 30
RECENT_WINDOW = 30
VAR_QUANTILE = 0.05  # "1 day in 20"
MIN_OVERLAP = 30


def normalize_daily(closes: pd.Series) -> pd.Series:
    """A close series indexed by naive midnight dates, oldest first, one value per day."""
    index = pd.to_datetime(closes.index, utc=True).tz_convert(None).normalize()
    series = pd.Series(closes.to_numpy(dtype=float), index=index)
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series.dropna()


def _pct(value) -> float | None:
    return None if value is None or not np.isfinite(value) else round(float(value) * 100, 2)


def _date(timestamp) -> str:
    return pd.Timestamp(timestamp).strftime("%Y-%m-%d")


def risk_metrics(closes: pd.Series, asset_type: str) -> dict | None:
    """Risk summary for one asset, or None when there is too little history.

    All "pct" fields are percentages. Daily-return measures (VaR, worst day) use
    the series' own consecutive observations, so a stock's Monday return covers
    the weekend.
    """
    closes = normalize_daily(closes)
    if len(closes) < MIN_OBSERVATIONS:
        return None

    returns = closes.pct_change().dropna()
    periods = periods_per_year(asset_type)

    drawdown = closes / closes.cummax() - 1
    trough = drawdown.idxmin()
    var_95 = returns.quantile(VAR_QUANTILE)
    tail = returns[returns <= var_95]
    recent = returns.tail(RECENT_WINDOW)

    return {
        "observations": int(len(closes)),
        "start_date": _date(closes.index[0]),
        "end_date": _date(closes.index[-1]),
        "latest_close": round(float(closes.iloc[-1]), 4),
        "annualized_volatility_pct": _pct(annualized_volatility(returns, periods)),
        "recent_volatility_pct": _pct(annualized_volatility(recent, periods)) if len(recent) >= 20 else None,
        "max_drawdown_pct": _pct(max_drawdown(closes)),
        "max_drawdown_date": _date(trough),
        "current_drawdown_pct": _pct(drawdown.iloc[-1]),
        "var_95_pct": _pct(var_95),
        "expected_shortfall_pct": _pct(tail.mean()) if len(tail) else None,
        "worst_day_pct": _pct(returns.min()),
        "worst_day_date": _date(returns.idxmin()),
        "best_day_pct": _pct(returns.max()),
        "sharpe_ratio": (
            None if not np.isfinite(sharpe_ratio(returns, periods))
            else round(float(sharpe_ratio(returns, periods)), 2)
        ),
    }


def correlation_matrix(closes_by_symbol: dict[str, pd.Series]) -> tuple[list[str], list[list[float | None]]]:
    """Pairwise correlation of daily returns.

    Each pair is measured on the dates both assets have in common, and returns
    are taken between those shared dates. That keeps the holding periods equal
    even when one asset trades 7 days a week and the other only on weekdays.
    A pair with too little overlap is None.
    """
    symbols = list(closes_by_symbol)
    series = {symbol: normalize_daily(closes) for symbol, closes in closes_by_symbol.items()}
    size = len(symbols)
    matrix: list[list[float | None]] = [[None] * size for _ in range(size)]

    for i in range(size):
        matrix[i][i] = 1.0
        for j in range(i + 1, size):
            joined = pd.concat([series[symbols[i]], series[symbols[j]]], axis=1, join="inner").dropna()
            value = None
            if len(joined) > MIN_OVERLAP:
                corr = joined.pct_change().dropna().corr().iloc[0, 1]
                value = round(float(corr), 3) if np.isfinite(corr) else None
            matrix[i][j] = matrix[j][i] = value

    return symbols, matrix
