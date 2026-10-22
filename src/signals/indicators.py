"""Technical indicators over pandas Series.

Every function returns a Series aligned with its input, with NaN where the
value is not yet defined. The conventions match the browser charts
(frontend/src/lib/indicators.js) so the signals describe exactly what the
chart shows: EMA is seeded with the SMA of its first `period` values, RSI uses
Wilder's smoothing, and Bollinger Bands use the population standard deviation.

All indicators are causal: the value at row i depends only on rows <= i.
"""
import numpy as np
import pandas as pd


def sma(values: pd.Series, period: int) -> pd.Series:
    return values.rolling(period).mean()


def ema(values: pd.Series, period: int) -> pd.Series:
    data = values.to_numpy(dtype=float)
    result = np.full(len(data), np.nan)

    # Start at the first defined value so chained indicators (the MACD
    # signal line) work on a series with leading NaNs.
    defined = np.flatnonzero(~np.isnan(data))
    if len(defined) == 0:
        return pd.Series(result, index=values.index)

    start = defined[0]
    if len(data) - start >= period:
        k = 2 / (period + 1)
        previous = data[start:start + period].mean()
        result[start + period - 1] = previous
        for i in range(start + period, len(data)):
            previous = data[i] * k + previous * (1 - k)
            result[i] = previous

    return pd.Series(result, index=values.index)


def rsi(values: pd.Series, period: int = 14) -> pd.Series:
    data = values.to_numpy(dtype=float)
    result = np.full(len(data), np.nan)
    if len(data) <= period:
        return pd.Series(result, index=values.index)

    changes = np.diff(data)
    average_gain = np.maximum(changes[:period], 0).mean()
    average_loss = np.maximum(-changes[:period], 0).mean()

    def to_rsi() -> float:
        if average_loss == 0:
            return 100.0
        return 100 - 100 / (1 + average_gain / average_loss)

    result[period] = to_rsi()
    for i in range(period + 1, len(data)):
        change = changes[i - 1]
        average_gain = (average_gain * (period - 1) + max(change, 0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0)) / period
        result[i] = to_rsi()

    return pd.Series(result, index=values.index)


def macd(
    values: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> pd.DataFrame:
    line = ema(values, fast) - ema(values, slow)
    signal = ema(line, signal_period)
    return pd.DataFrame({
        "macd": line,
        "macd_signal": signal,
        "macd_hist": line - signal,
    })


def bollinger(
    values: pd.Series, period: int = 20, multiplier: float = 2.0
) -> pd.DataFrame:
    middle = sma(values, period)
    deviation = values.rolling(period).std(ddof=0)
    return pd.DataFrame({
        "bb_upper": middle + multiplier * deviation,
        "bb_middle": middle,
        "bb_lower": middle - multiplier * deviation,
    })
