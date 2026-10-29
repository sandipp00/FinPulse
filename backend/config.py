"""Backend settings, read from environment variables (and a local .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str) -> str | None:
    """The variable's value, or None if it is unset or blank.

    Docker Compose passes an unset `${VAR:-}` as an empty string, which should
    mean "use the default", not "false" or "".
    """
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in (_env(name) or default).split(",") if item.strip()]


def _flag(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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

# US macro data from FRED (Federal Reserve Bank of St. Louis). Free key from
# https://fred.stlouisfed.org/docs/api/api_key.html; without it macro data is
# reported as not configured. The key is a secret: it stays on the server.
FRED_API_KEY = _env("FRED_API_KEY")
FRED_BASE_URL = (_env("FRED_BASE_URL") or "https://api.stlouisfed.org/fred").rstrip("/")

# Paper trading (virtual money only).
PAPER_STARTING_CASH = float(os.getenv("PAPER_STARTING_CASH", "100000"))
PAPER_FEE_PCT = float(os.getenv("PAPER_FEE_PCT", "0.1"))
# Orders are rejected if the live price is older than this.
PAPER_MAX_PRICE_AGE_SECONDS = float(os.getenv("PAPER_MAX_PRICE_AGE_SECONDS", "15"))

# Accounts and sessions.
ALLOW_REGISTRATION = _flag("ALLOW_REGISTRATION", True)
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
# Set true when serving over HTTPS so the session cookie is never sent in clear.
COOKIE_SECURE = _flag("COOKIE_SECURE", False)
# Set true only behind a reverse proxy you control that overwrites
# X-Forwarded-For (the bundled nginx does); otherwise clients could spoof their IP.
TRUST_PROXY = _flag("TRUST_PROXY", False)

# ---- Email (verification and password reset) ----------------------------------
# Any SMTP server works, including free tiers (Gmail app password, Brevo, Resend...).
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = int(_env("SMTP_PORT") or 587)
SMTP_USER = _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
# Port 587 normally upgrades with STARTTLS; port 465 is TLS from the first byte.
SMTP_SSL = _flag("SMTP_SSL", SMTP_PORT == 465)
SMTP_STARTTLS = _flag("SMTP_STARTTLS", not SMTP_SSL)
EMAIL_FROM = _env("EMAIL_FROM") or "FinPulse <no-reply@localhost>"

# smtp: really send. console: print the email (and its link) to the server log,
# for local development. off: no email at all.
EMAIL_BACKEND = (_env("EMAIL_BACKEND") or ("smtp" if SMTP_HOST else "off")).lower()

# Must users verify their email before paper trading? On whenever email works.
REQUIRE_EMAIL_VERIFICATION = _flag("REQUIRE_EMAIL_VERIFICATION", EMAIL_BACKEND != "off")

# The address used in the links inside emails. It is configured, never taken
# from the request, so a forged Host header cannot point a reset link elsewhere.
PUBLIC_URL = (_env("PUBLIC_URL") or "http://localhost:5173").rstrip("/")

VERIFY_TOKEN_HOURS = 24
RESET_TOKEN_MINUTES = 60
