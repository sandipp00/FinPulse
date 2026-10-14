
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "finpulse.db"
OUTPUT_DIR = ROOT / "data" / "processed"


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

        periods = 365 if asset_type == "crypto" else 252
        daily_volatility = returns.std(ddof=1)

        annualized_volatility = (
            daily_volatility * np.sqrt(periods)
            if pd.notna(daily_volatility)
            else np.nan
        )

        sharpe = (
            returns.mean() / daily_volatility * np.sqrt(periods)
            if pd.notna(daily_volatility) and daily_volatility > 0
            else np.nan
        )

        first_close = group["close"].iloc[0]
        last_close = group["close"].iloc[-1]

        results.append({
            "symbol": symbol,
            "asset_type": asset_type,
            "observations": len(group),
            "start_date": group["timestamp"].iloc[0].date(),
            "end_date": group["timestamp"].iloc[-1].date(),
            "total_return_pct": (last_close / first_close - 1) * 100,
            "annualized_volatility_pct": annualized_volatility * 100,
            "sharpe_ratio_rf_zero": sharpe,
            "max_drawdown_pct": group["drawdown"].min() * 100,
        })

    return pd.DataFrame(results)


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
