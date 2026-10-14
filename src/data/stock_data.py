from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "stocks"

SYMBOLS = {
    "^NSEI": "nifty50",
    "AAPL": "apple",
}


def fetch_stock_data(
    symbol: str,
    start: str = "2023-01-01",
    end: str | None = None,
) -> pd.DataFrame:
    """Download and validate historical daily stock-market data."""
    df = yf.download(
        symbol,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    if df.empty:
        raise ValueError(f"No stock data returned for {symbol}")

    # yfinance may return MultiIndex columns even for a single ticker.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required.difference(df.columns)

    if missing:
        raise ValueError(f"{symbol}: missing columns {sorted(missing)}")

    df = df.reset_index()
    df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
    df = df.rename(columns={"date": "timestamp", "datetime": "timestamp"})

    df["symbol"] = symbol
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    df = df.drop_duplicates(subset=["timestamp", "symbol"])
    df = df.sort_values("timestamp")

    return df


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for symbol, filename in SYMBOLS.items():
        try:
            df = fetch_stock_data(symbol)
            output_file = OUTPUT_DIR / f"{filename}.csv"
            df.to_csv(output_file, index=False)
            print(f"{symbol}: saved {len(df)} rows to {output_file}")
        except Exception as exc:
            print(f"ERROR downloading {symbol}: {exc}")


if __name__ == "__main__":
    main()
