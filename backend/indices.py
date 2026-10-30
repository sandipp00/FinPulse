"""The world stock-market indices the terminal follows, with where and when they trade.

Prices come from the Yahoo quote poller (backend/quotes_live.py) and charts from
Yahoo's chart API (backend/yahoo_history.py); this module only says what each
index is. Yahoo delays some exchanges (Hong Kong and Shanghai by about 15
minutes), which the quote's DELAYED tag shows.
"""
from fastapi import APIRouter

router = APIRouter(tags=["indices"])

REGIONS = ("Americas", "Europe", "Asia-Pacific")

# symbol, name, region, country, currency, exchange time zone
WORLD_INDICES = [
    ("^GSPC", "S&P 500", "Americas", "United States", "USD", "America/New_York"),
    ("^DJI", "Dow Jones Industrial Average", "Americas", "United States", "USD", "America/New_York"),
    ("^IXIC", "Nasdaq Composite", "Americas", "United States", "USD", "America/New_York"),
    ("^GSPTSE", "S&P/TSX Composite", "Americas", "Canada", "CAD", "America/Toronto"),
    ("^BVSP", "Ibovespa", "Americas", "Brazil", "BRL", "America/Sao_Paulo"),
    ("^FTSE", "FTSE 100", "Europe", "United Kingdom", "GBP", "Europe/London"),
    ("^GDAXI", "DAX", "Europe", "Germany", "EUR", "Europe/Berlin"),
    ("^FCHI", "CAC 40", "Europe", "France", "EUR", "Europe/Paris"),
    ("^STOXX50E", "Euro Stoxx 50", "Europe", "Eurozone", "EUR", "Europe/Berlin"),
    ("^N225", "Nikkei 225", "Asia-Pacific", "Japan", "JPY", "Asia/Tokyo"),
    ("^HSI", "Hang Seng", "Asia-Pacific", "Hong Kong", "HKD", "Asia/Hong_Kong"),
    ("000001.SS", "Shanghai Composite", "Asia-Pacific", "China", "CNY", "Asia/Shanghai"),
    ("^KS11", "KOSPI", "Asia-Pacific", "South Korea", "KRW", "Asia/Seoul"),
    ("^AXJO", "S&P/ASX 200", "Asia-Pacific", "Australia", "AUD", "Australia/Sydney"),
    ("^NSEI", "NIFTY 50", "Asia-Pacific", "India", "INR", "Asia/Kolkata"),
]
INDEX_SYMBOLS = {row[0] for row in WORLD_INDICES}
CURRENCIES = {row[0]: row[4] for row in WORLD_INDICES}


@router.get("/api/world-indices")
def world_indices():
    """The followed indices by region; live values arrive on the price socket."""
    return {
        "regions": list(REGIONS),
        "count": len(WORLD_INDICES),
        "indices": [
            {"symbol": s, "name": n, "region": r, "country": c, "currency": cur, "timezone": tz}
            for s, n, r, c, cur, tz in WORLD_INDICES
        ],
    }
