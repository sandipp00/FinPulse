from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    ROOT / "data" / "raw" / "stocks" / "nifty50.csv",
    ROOT / "data" / "raw" / "stocks" / "apple.csv",
]


def validate_file(path: Path) -> None:
    print(f"\n{'=' * 60}")
    print(f"File: {path.name}")

    if not path.exists():
        print("ERROR: File not found")
        return

    df = pd.read_csv(path)
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")

    required = {"timestamp", "open", "high", "low", "close", "volume", "symbol"}
    missing_columns = required - set(df.columns)

    if missing_columns:
        print(f"FAIL: Missing columns: {sorted(missing_columns)}")
        return

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    numeric = ["open", "high", "low", "close", "volume"]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")

    print(f"Missing values:\n{df[sorted(required)].isna().sum().to_string()}")
    print(f"Duplicate timestamp/symbol pairs: {df.duplicated(['timestamp', 'symbol']).sum()}")

    invalid_prices = (
        (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (df["high"] < df["low"])
        | (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
    )

    print(f"Invalid price rows: {invalid_prices.sum()}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print("\nLatest 5 records:")
    print(df.tail(5).to_string(index=False))


if __name__ == "__main__":
    for file in FILES:
        validate_file(file)
