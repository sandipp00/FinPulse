"""Rule-based buy/sell signal engine.

Six transparent rules each vote bullish (+1), bearish (-1) or neutral (0) on
every candle. The weighted average of the votes is the score, from -1 (every
rule bearish) to +1 (every rule bullish), and the score maps to a rating.

There is no model and nothing is fitted to data: the rules are textbook
technical-analysis conventions, so every rating can be explained in plain
language and re-checked on the chart. Ratings describe what indicators say
about recent price action. They are not predictions.
"""
import numpy as np
import pandas as pd

from src.signals import indicators

# Rule name -> weight. Trend and momentum carry more weight than the
# mean-reversion (Bollinger) and volume rules.
RULE_WEIGHTS = {
    "trend": 1.0,
    "ma_cross": 1.0,
    "rsi": 1.0,
    "macd": 1.0,
    "bollinger": 0.75,
    "volume": 0.5,
}
TOTAL_WEIGHT = sum(RULE_WEIGHTS.values())

STRONG_THRESHOLD = 0.5
DIRECTIONAL_THRESHOLD = 0.2  # |score| below this is "Hold"

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
VOLUME_SPIKE = 1.5
# A MACD histogram smaller than this fraction of price is rounding noise, not
# momentum (a perfectly linear trend gives a histogram of about -1e-15).
MACD_NOISE_FRACTION = 1e-6

# The slowest indicator (SMA 50) needs 50 candles; the MACD signal line needs
# 34. Rows before this are not scored.
WARMUP_CANDLES = 50

RATINGS = ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")


def rating_for(score: float) -> str:
    if score >= STRONG_THRESHOLD:
        return "Strong Buy"
    if score >= DIRECTIONAL_THRESHOLD:
        return "Buy"
    if score > -DIRECTIONAL_THRESHOLD:
        return "Hold"
    if score > -STRONG_THRESHOLD:
        return "Sell"
    return "Strong Sell"


def add_indicators(candles: pd.DataFrame) -> pd.DataFrame:
    """Candles (open, high, low, close, volume) plus every indicator column."""
    frame = candles.copy()
    close = frame["close"]

    frame["sma20"] = indicators.sma(close, 20)
    frame["sma50"] = indicators.sma(close, 50)
    frame["rsi"] = indicators.rsi(close, 14)
    frame["volume_ratio"] = frame["volume"] / frame["volume"].rolling(20).mean()
    frame = frame.join(indicators.macd(close))
    frame = frame.join(indicators.bollinger(close))
    return frame


def compute_votes(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-rule votes (-1, 0, +1) for every row of an add_indicators() frame."""
    close = frame["close"]
    votes = pd.DataFrame(index=frame.index)

    votes["trend"] = np.sign(close - frame["sma50"])
    votes["ma_cross"] = np.sign(frame["sma20"] - frame["sma50"])
    votes["rsi"] = np.select(
        [frame["rsi"] <= RSI_OVERSOLD, frame["rsi"] >= RSI_OVERBOUGHT],
        [1, -1],
        default=0,
    )
    macd_hist = frame["macd_hist"]
    votes["macd"] = np.where(
        macd_hist.abs() <= close * MACD_NOISE_FRACTION, 0, np.sign(macd_hist)
    )
    votes["bollinger"] = np.select(
        [close < frame["bb_lower"], close > frame["bb_upper"]],
        [1, -1],
        default=0,
    )
    # Heavy volume confirms the direction of the candle it occurs on.
    votes["volume"] = np.where(
        frame["volume_ratio"] > VOLUME_SPIKE,
        np.sign(close - frame["open"]),
        0,
    )

    # Rules whose indicator is not defined yet (NaN) abstain.
    return votes.fillna(0).astype(int)


def score_frame(candles: pd.DataFrame) -> pd.DataFrame:
    """Indicators, votes, a -1..+1 `score` and a `ready` flag for each candle."""
    frame = add_indicators(candles)
    votes = compute_votes(frame)

    weights = pd.Series(RULE_WEIGHTS)
    frame["score"] = (votes * weights).sum(axis=1) / TOTAL_WEIGHT
    frame["ready"] = np.arange(len(frame)) >= WARMUP_CANDLES - 1
    frame.loc[~frame["ready"], "score"] = 0.0

    for rule in RULE_WEIGHTS:
        frame[f"vote_{rule}"] = votes[rule]
    return frame


def _price(value: float) -> str:
    return f"{value:,.4f}" if abs(value) < 10 else f"{value:,.2f}"


def explain(row: pd.Series) -> list[dict]:
    """Plain-language reason for each rule's vote on one scored row."""
    close = row["close"]
    texts = {}

    texts["trend"] = (
        f"Price {_price(close)} is "
        f"{'above' if row['vote_trend'] > 0 else 'below'} "
        f"the 50-candle average ({_price(row['sma50'])})"
    )
    texts["ma_cross"] = (
        f"20-candle average is {'above' if row['vote_ma_cross'] > 0 else 'below'} "
        f"the 50-candle average — {'uptrend' if row['vote_ma_cross'] > 0 else 'downtrend'}"
    )

    rsi_value = row["rsi"]
    if row["vote_rsi"] > 0:
        texts["rsi"] = f"RSI {rsi_value:.1f} is oversold (≤ {RSI_OVERSOLD}) — selling may be stretched"
    elif row["vote_rsi"] < 0:
        texts["rsi"] = f"RSI {rsi_value:.1f} is overbought (≥ {RSI_OVERBOUGHT}) — buying may be stretched"
    else:
        texts["rsi"] = f"RSI {rsi_value:.1f} is neutral ({RSI_OVERSOLD}–{RSI_OVERBOUGHT})"

    if row["vote_macd"] == 0:
        texts["macd"] = "MACD histogram is flat — no clear momentum"
    else:
        texts["macd"] = (
            f"MACD histogram is {'positive' if row['vote_macd'] > 0 else 'negative'} "
            f"— momentum is {'building up' if row['vote_macd'] > 0 else 'building down'}"
        )

    if row["vote_bollinger"] > 0:
        texts["bollinger"] = "Price closed below the lower Bollinger Band — stretched to the downside"
    elif row["vote_bollinger"] < 0:
        texts["bollinger"] = "Price closed above the upper Bollinger Band — stretched to the upside"
    else:
        texts["bollinger"] = "Price is inside its Bollinger Bands"

    ratio = row["volume_ratio"]
    if row["vote_volume"] != 0:
        side = "green (up)" if row["vote_volume"] > 0 else "red (down)"
        texts["volume"] = f"Volume is {ratio:.1f}× its 20-candle average on a {side} candle"
    else:
        texts["volume"] = f"Volume is normal ({ratio:.1f}× its 20-candle average)"

    return [
        {
            "rule": rule,
            "vote": int(row[f"vote_{rule}"]),
            "weight": weight,
            "text": texts[rule],
        }
        for rule, weight in RULE_WEIGHTS.items()
    ]


def latest_signal(candles: pd.DataFrame) -> dict:
    """The rating for the most recent candle in `candles`.

    Pass closed candles only, otherwise the rating flickers while the current
    candle is still forming.
    """
    if len(candles) < WARMUP_CANDLES:
        return {
            "rating": "Insufficient data",
            "score": None,
            "confidence": None,
            "reasons": [],
            "votes": None,
            "candles_available": len(candles),
            "candles_required": WARMUP_CANDLES,
        }

    scored = score_frame(candles)
    row = scored.iloc[-1]
    reasons = explain(row)

    weight_by_side = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    count_by_side = {"bullish": 0, "bearish": 0, "neutral": 0}
    for reason in reasons:
        side = "bullish" if reason["vote"] > 0 else "bearish" if reason["vote"] < 0 else "neutral"
        weight_by_side[side] += reason["weight"]
        count_by_side[side] += 1

    score = float(row["score"])
    rating = rating_for(score)

    # Confidence is the share of rule weight that agrees with a directional
    # call. A Hold is not a directional call, so it has none.
    confidence = None
    if score >= DIRECTIONAL_THRESHOLD:
        confidence = round(100 * weight_by_side["bullish"] / TOTAL_WEIGHT)
    elif score <= -DIRECTIONAL_THRESHOLD:
        confidence = round(100 * weight_by_side["bearish"] / TOTAL_WEIGHT)

    return {
        "rating": rating,
        "score": round(score * 100, 1),
        "confidence": confidence,
        "votes": count_by_side,
        "reasons": reasons,
        "price": float(row["close"]),
        "as_of": int(row["time"]) if "time" in row else None,
    }
