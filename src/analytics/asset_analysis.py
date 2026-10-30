"""Per-asset analysis from daily closes: performance, risk, return distribution,
trend indicators, a monthly-returns table and the series behind the charts.

Every function takes a close series indexed by date (oldest first) and returns
plain numbers (fractions, not percent) or None where the history is too short to
say. Nothing is filled in: a 1-year return needs a year of history.
"""
from typing import Optional

import numpy as np
import pandas as pd

from src.analytics import quant
from src.signals import indicators

# Calendar-day look-backs for the performance table.
PERIODS = {"1W": 7, "1M": 30, "3M": 91, "6M": 182, "1Y": 365, "3Y": 3 * 365}
# A look-back is answered only if the history starts close enough to its start: within
# a seventh of the period (so weekends and holidays fit), at most SLACK_DAYS.
SLACK_DAYS = 5
TAIL_LEVEL = 0.95
MIN_RETURNS = 30
ROLLING_WINDOW = 30
HISTOGRAM_BINS = 30


def _f(value) -> Optional[float]:
    return quant._finite(value)


def period_return(closes: pd.Series, days: int) -> Optional[float]:
    """Return over the last `days` calendar days, or None if the history is shorter."""
    if len(closes) < 2:
        return None
    last_day = closes.index[-1]
    start = last_day - pd.Timedelta(days=days)
    slack = min(SLACK_DAYS, max(1, days // 7))
    if closes.index[0] > start + pd.Timedelta(days=slack):
        return None
    base = closes[closes.index <= start]
    base = base.iloc[-1] if len(base) else closes.iloc[0]
    return _f(closes.iloc[-1] / base - 1)


def year_to_date(closes: pd.Series) -> Optional[float]:
    last_day = closes.index[-1]
    before = closes[closes.index < pd.Timestamp(year=last_day.year, month=1, day=1)]
    if before.empty:
        return None
    return _f(closes.iloc[-1] / before.iloc[-1] - 1)


def performance(closes: pd.Series) -> dict:
    return {
        **{label: period_return(closes, days) for label, days in PERIODS.items()},
        "YTD": year_to_date(closes),
        "annualized": quant.annualized_return(closes),
    }


def risk(closes: pd.Series, periods: int) -> dict:
    returns = quant.simple_returns(closes)
    year = returns[returns.index > closes.index[-1] - pd.Timedelta(days=365)]
    enough = len(returns) >= MIN_RETURNS
    downside = returns[returns < 0]
    mean_annual = returns.mean() * periods if enough else None
    vol = quant.annualized_volatility(returns, periods)
    downside_vol = _f(downside.std(ddof=1) * np.sqrt(periods)) if len(downside) > 1 else None
    var = -float(returns.quantile(1 - TAIL_LEVEL)) if enough else None
    tail = returns[returns <= returns.quantile(1 - TAIL_LEVEL)] if enough else pd.Series(dtype=float)
    dd = quant.drawdown_stats(closes)
    return {
        "volatility_30d": quant.annualized_volatility(returns.tail(30), periods) if len(returns) >= 30 else None,
        "volatility_90d": quant.annualized_volatility(returns.tail(90), periods) if len(returns) >= 90 else None,
        "volatility_1y": quant.annualized_volatility(year, periods) if len(year) >= MIN_RETURNS else None,
        "volatility_all": vol,
        # Risk-free rate taken as zero, as on the rest of FinPulse.
        "sharpe": _f(mean_annual / vol) if mean_annual is not None and vol else None,
        "sortino": _f(mean_annual / downside_vol) if mean_annual is not None and downside_vol else None,
        "var_95": _f(var),
        "cvar_95": _f(-tail.mean()) if len(tail) else None,
        "best_day": _f(returns.max()) if len(returns) else None,
        "best_day_date": returns.idxmax().date().isoformat() if len(returns) else None,
        "worst_day": _f(returns.min()) if len(returns) else None,
        "worst_day_date": returns.idxmin().date().isoformat() if len(returns) else None,
        "positive_days": _f((returns > 0).mean()) if len(returns) else None,
        "max_drawdown": dd.max_drawdown,
        "max_drawdown_peak": dd.peak_date.date().isoformat() if dd.peak_date is not None else None,
        "max_drawdown_trough": dd.trough_date.date().isoformat() if dd.trough_date is not None else None,
        "recovered": dd.recovered,
        "current_drawdown": _f(quant.drawdown_series(closes).iloc[-1]),
    }


def distribution(closes: pd.Series) -> dict:
    returns = quant.simple_returns(closes).dropna()
    if len(returns) < MIN_RETURNS:
        return {"count": len(returns), "mean": None, "median": None, "skew": None, "kurtosis": None, "bins": []}
    counts, edges = np.histogram(returns, bins=HISTOGRAM_BINS)
    return {
        "count": len(returns),
        "mean": _f(returns.mean()),
        "median": _f(returns.median()),
        "skew": _f(returns.skew()),
        "kurtosis": _f(returns.kurt()),  # excess kurtosis: 0 for a normal distribution
        "bins": [{"from": _f(a), "to": _f(b), "count": int(c)} for a, b, c in zip(edges[:-1], edges[1:], counts)],
    }


def technicals(closes: pd.Series) -> dict:
    last = float(closes.iloc[-1])
    out = {"close": _f(last)}
    for period in (20, 50, 200):
        value = indicators.sma(closes, period).iloc[-1] if len(closes) >= period else None
        out[f"sma_{period}"] = _f(value)
        out[f"vs_sma_{period}"] = _f(last / value - 1) if value else None
    rsi = indicators.rsi(closes, 14) if len(closes) > 15 else None
    out["rsi_14"] = _f(rsi.iloc[-1]) if rsi is not None else None
    if len(closes) >= 35:
        macd_frame = indicators.macd(closes)
        line, signal = macd_frame["macd"].iloc[-1], macd_frame["macd_signal"].iloc[-1]
        out["macd"], out["macd_signal"] = _f(line), _f(signal)
        out["macd_state"] = "bullish" if line > signal else "bearish"
    else:
        out["macd"] = out["macd_signal"] = out["macd_state"] = None
    year = closes[closes.index > closes.index[-1] - pd.Timedelta(days=365)]
    if closes.index[0] <= closes.index[-1] - pd.Timedelta(days=365 - SLACK_DAYS):
        high, low = float(year.max()), float(year.min())
        out.update(high_52w=_f(high), low_52w=_f(low), from_high_52w=_f(last / high - 1), from_low_52w=_f(last / low - 1))
    else:
        out.update(high_52w=None, low_52w=None, from_high_52w=None, from_low_52w=None)
    out["trend"] = trend(out)
    out["last_cross"] = last_cross(closes)
    return out


def trend(t: dict) -> Optional[str]:
    """Up when price > 50-day > 200-day average, down when the reverse, else mixed."""
    close, s50, s200 = t["close"], t["sma_50"], t["sma_200"]
    if s50 is None or s200 is None:
        return None
    if close > s50 > s200:
        return "up"
    if close < s50 < s200:
        return "down"
    return "mixed"


def last_cross(closes: pd.Series) -> Optional[dict]:
    """The latest 50/200-day crossover: a golden cross (50 above 200) or a death cross."""
    if len(closes) < 201:
        return None
    above = (indicators.sma(closes, 50) > indicators.sma(closes, 200)).dropna()
    above = above[indicators.sma(closes, 200).notna()]
    changes = above.ne(above.shift())
    changes.iloc[0] = False
    if not changes.any():
        return None
    day = changes[changes].index[-1]
    return {"type": "golden" if above.loc[day] else "death", "date": day.date().isoformat()}


def monthly_returns(closes: pd.Series) -> list[dict]:
    """Return of each calendar month (first and partial last month use what exists)."""
    month_end = closes.groupby([closes.index.year, closes.index.month]).last()
    previous = month_end.shift(1)
    rows = []
    for (year, month), close in month_end.items():
        base = previous.loc[(year, month)]
        if pd.isna(base):
            continue  # the first month has no prior close to measure from
        rows.append({"year": int(year), "month": int(month), "return": _f(close / base - 1)})
    return rows


def series(closes: pd.Series, periods: int) -> dict:
    """Points for the charts: drawdown and 30-day rolling volatility."""
    drawdown = quant.drawdown_series(closes)
    vol = quant.rolling_volatility(quant.simple_returns(closes), ROLLING_WINDOW, periods)
    day = lambda ts: ts.date().isoformat()  # noqa: E731
    return {
        "drawdown": [{"date": day(d), "value": _f(v)} for d, v in drawdown.items()],
        "rolling_volatility": [{"date": day(d), "value": _f(v)} for d, v in vol.dropna().items()],
    }


def analyse(closes: pd.Series, periods: int) -> dict:
    closes = closes.dropna()
    return {
        "first_date": closes.index[0].date().isoformat(),
        "last_date": closes.index[-1].date().isoformat(),
        "observations": len(closes),
        "performance": performance(closes),
        "risk": risk(closes, periods),
        "distribution": distribution(closes),
        "technicals": technicals(closes),
        "monthly_returns": monthly_returns(closes),
        "series": series(closes, periods),
    }


def summary(closes: pd.Series, periods: int) -> dict:
    """The scoreboard row: a few headline figures."""
    closes = closes.dropna()
    perf = performance(closes)
    returns = quant.simple_returns(closes)
    tech = technicals(closes)
    return {
        "last_date": closes.index[-1].date().isoformat(),
        "close": _f(closes.iloc[-1]),
        "return_1w": perf["1W"], "return_1m": perf["1M"], "return_3m": perf["3M"],
        "return_ytd": perf["YTD"], "return_1y": perf["1Y"],
        "volatility_1y": risk(closes, periods)["volatility_1y"] if len(returns) >= MIN_RETURNS else None,
        "max_drawdown": quant.drawdown_stats(closes).max_drawdown,
        "from_high_52w": tech["from_high_52w"],
        "rsi_14": tech["rsi_14"],
        "trend": tech["trend"],
    }
