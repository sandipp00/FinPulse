from pathlib import Path

import ccxt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "crypto"

SYMBOLS = ["BTC/USDT", "ETH/USDT"]


def fetch_crypto_data(
    symbol: str,
    timeframe: str = "1d",
    since: str = "2023-01-01",
) -> pd.DataFrame:
    """Download daily OHLCV candles from Binance's public market API."""
    exchange = ccxt.binance({"enableRateLimit": True})

    since_ms = exchange.parse8601(f"{since}T00:00:00Z")
    rows = []

    while True:
        batch = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=since_ms,
            limit=1000,
        )

        if not batch:
            break

        rows.extend(batch)
        next_since = batch[-1][0] + 1

        if next_since <= since_ms or len(batch) < 1000:
            break

        since_ms = next_since

    if not rows:
        raise ValueError(f"No crypto data returned for {symbol}")

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["symbol"] = symbol

    df = df.drop_duplicates(subset=["timestamp", "symbol"])
    df = df.sort_values("timestamp")

    return df


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for symbol in SYMBOLS:
        try:
            df = fetch_crypto_data(symbol)
            filename = symbol.replace("/", "_").lower() + ".csv"
            output_file = OUTPUT_DIR / filename
            df.to_csv(output_file, index=False)
            print(f"{symbol}: saved {len(df)} rows to {output_file}")
        except Exception as exc:
            print(f"ERROR downloading {symbol}: {exc}")


if __name__ == "__main__":
    main()
