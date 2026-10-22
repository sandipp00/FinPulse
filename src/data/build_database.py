import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # lets `python src/data/build_database.py` import src.*

from src.data.schema import MARKET_PRICES_DDL, MARKET_PRICES_INDEX_DDL  # noqa: E402
DB_PATH = ROOT / "data" / "finpulse.db"

DATASETS = [
    (ROOT / "data/raw/stocks/nifty50.csv", "index"),
    (ROOT / "data/raw/stocks/apple.csv", "stock"),
    (ROOT / "data/raw/crypto/btc_usdt.csv", "crypto"),
    (ROOT / "data/raw/crypto/eth_usdt.csv", "crypto"),
]

REQUIRED_COLUMNS = [
    "timestamp", "symbol", "open", "high",
    "low", "close", "volume",
]


def load_dataset(path: Path, asset_type: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    df = pd.read_csv(path)

    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    df["asset_type"] = asset_type
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce"
    )

    numeric_columns = ["open", "high", "low", "close", "volume"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[["timestamp"] + numeric_columns].isna().any().any():
        raise ValueError(f"{path.name}: invalid or missing values found")

    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"{path.name}: non-positive price found")

    if (df["volume"] < 0).any():
        raise ValueError(f"{path.name}: negative volume found")

    if (df["high"] < df["low"]).any():
        raise ValueError(f"{path.name}: high is below low")

    df["timestamp"] = df["timestamp"].dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    df = df.drop_duplicates(
        subset=["timestamp", "symbol", "asset_type"]
    )

    return df


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(MARKET_PRICES_DDL)
        conn.execute(MARKET_PRICES_INDEX_DDL)

        total_loaded = 0

        for path, asset_type in DATASETS:
            df = load_dataset(path, asset_type)

            records = list(
                df[[
                    "timestamp", "symbol", "asset_type",
                    "open", "high", "low", "close", "volume"
                ]].itertuples(index=False, name=None)
            )

            conn.executemany("""
                INSERT OR REPLACE INTO market_prices
                (timestamp, symbol, asset_type, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, records)

            total_loaded += len(records)
            print(f"{path.name}: processed {len(records)} records")

        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM market_prices"
        ).fetchone()[0]

        print(f"\nDatabase: {DB_PATH}")
        print(f"Records processed: {total_loaded}")
        print(f"Unique records in database: {count}")


if __name__ == "__main__":
    main()
