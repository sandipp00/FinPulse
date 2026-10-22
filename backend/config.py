"""Backend settings, read from environment variables (and a local .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", PROJECT_ROOT / "data" / "finpulse.db")
)

CORS_ORIGINS = _csv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)

# Live crypto feed (Binance public WebSocket streams, no API key needed).
LIVE_FEED_ENABLED = _flag("LIVE_FEED_ENABLED", True)

LIVE_SYMBOLS = _csv(
    "LIVE_SYMBOLS",
    "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT",
)

# Tried in order; the second is Binance's market-data-only endpoint, which
# also works in regions where the main domain is blocked.
BINANCE_WS_URLS = _csv(
    "BINANCE_WS_URLS",
    "wss://stream.binance.com:9443,wss://data-stream.binance.vision",
)

# REST endpoints for historical candles; tried in order.
BINANCE_REST_URLS = _csv(
    "BINANCE_REST_URLS",
    "https://api.binance.com,https://data-api.binance.vision",
)

# Paper trading (virtual money only).
PAPER_STARTING_CASH = float(os.getenv("PAPER_STARTING_CASH", "100000"))
PAPER_FEE_PCT = float(os.getenv("PAPER_FEE_PCT", "0.1"))
# Orders are rejected if the live price is older than this.
PAPER_MAX_PRICE_AGE_SECONDS = float(os.getenv("PAPER_MAX_PRICE_AGE_SECONDS", "15"))
