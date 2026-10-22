import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "finpulse.db"
OUTPUT_DIR = ROOT / "data" / "processed"


def periods_per_year(asset_type):
    """Crypto trades every day; stocks and indices use a 252-day year."""
    return 365 if str(asset_type).lower() == "crypto" else 252


def annualized_volatility(returns, periods):
    """Annualized standard deviation of periodic returns (NaN if undefined)."""
    daily_std = returns.std(ddof=1)
    return daily_std * np.sqrt(periods) if pd.notna(daily_std) else np.nan


def sharpe_ratio(returns, periods):
    """Annualized Sharpe ratio assuming a zero risk-free rate."""
    daily_std = returns.std(ddof=1)
    if pd.isna(daily_std) or daily_std <= 0:
        return np.nan
    return returns.mean() / daily_std * np.sqrt(periods)


def max_drawdown(closes):
    """Largest peak-to-trough decline as a fraction (e.g. -0.25)."""
    return (closes / closes.cummax() - 1).min()


def load_market_data():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT timestamp, symbol, asset_type, close
            FROM market_prices
            ORDER BY symbol, timestamp
            """,
            conn,
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["close"] = pd.to_numeric(df["close"], errors="raise")
    return df


def calculate_daily_returns(df):
    df = df.sort_values(["symbol", "timestamp"]).copy()

    df["daily_return"] = df.groupby("symbol")["close"].pct_change()
    first_close = df.groupby("symbol")["close"].transform("first")
    df["growth_of_1"] = df["close"] / first_close

    running_peak = df.groupby("symbol")["close"].cummax()
    df["drawdown"] = df["close"] / running_peak - 1
    return df


def calculate_summary(df):
    results = []

    for (symbol, asset_type), group in df.groupby(["symbol", "asset_type"]):
        group = group.sort_values("timestamp")
        returns = group["daily_return"].dropna()
        periods = periods_per_year(asset_type)

        first_close = group["close"].iloc[0]
        last_close = group["close"].iloc[-1]

        results.append({
            "symbol": symbol,
            "asset_type": asset_type,
            "observations": len(group),
            "start_date": group["timestamp"].iloc[0].date(),
            "end_date": group["timestamp"].iloc[-1].date(),
            "total_return_pct": (last_close / first_close - 1) * 100,
            "annualized_volatility_pct": (
                annualized_volatility(returns, periods) * 100
            ),
            "sharpe_ratio_rf_zero": sharpe_ratio(returns, periods),
            "max_drawdown_pct": group["drawdown"].min() * 100,
        })

    return pd.DataFrame(results)


def asset_snapshot(group):
    """Latest price plus performance and risk metrics for one asset.

    Expects the columns timestamp, symbol, asset_type and close. Used by the
    API; returns an empty dict when the asset has no usable closes.
    """
    group = group.sort_values("timestamp")
    closes = pd.to_numeric(group["close"], errors="coerce").dropna()

    if closes.empty:
        return {}

    asset_type = str(group["asset_type"].iloc[0]).lower()
    periods = periods_per_year(asset_type)
    returns = closes.pct_change().dropna()

    first_close = float(closes.iloc[0])
    latest_close = float(closes.iloc[-1])
    previous_close = float(closes.iloc[-2]) if len(closes) > 1 else None

    volatility = sharpe = None
    if len(returns) > 1:
        volatility = float(annualized_volatility(returns, periods))
        sharpe = float(sharpe_ratio(returns, periods))

    total_return = None
    if first_close != 0:
        total_return = (latest_close / first_close - 1) * 100

    daily_change = None
    if previous_close not in (None, 0):
        daily_change = (latest_close / previous_close - 1) * 100

    return {
        "symbol": str(group["symbol"].iloc[0]),
        "asset_type": asset_type,
        "latest_timestamp": str(group["timestamp"].iloc[-1]),
        "latest_price": latest_close,
        "daily_change_pct": daily_change,
        "total_return_pct": total_return,
        "annualized_volatility_pct": (
            volatility * 100 if volatility is not None else None
        ),
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": float(max_drawdown(closes)) * 100,
        "observations": int(len(closes)),
        "first_date": str(group["timestamp"].iloc[0]),
        "last_date": str(group["timestamp"].iloc[-1]),
    }


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data = load_market_data()
    daily = calculate_daily_returns(data)
    summary = calculate_summary(daily)

    daily.to_csv(OUTPUT_DIR / "daily_returns.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "financial_summary.csv", index=False)

    print("\nFINPULSE FINANCIAL SUMMARY")
    print(summary.round(3).to_string(index=False))
    print("\nSaved reports to:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
