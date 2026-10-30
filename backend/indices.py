"""The world stock-market indices the terminal follows, with where and when they trade.

Prices come from the Yahoo quote poller (backend/quotes_live.py) and charts from
Yahoo's chart API (backend/yahoo_history.py); this module only says what each
index is. Yahoo delays some exchanges by about 15 minutes (Hong Kong, Shanghai,
Shenzhen, Singapore, Malaysia, the Sensex), which the quote's DELAYED tag shows.
Argentina's Merval is left out: Yahoo has no intraday data or currency for it.
"""
from fastapi import APIRouter

router = APIRouter(tags=["indices"])

REGIONS = ("Americas", "Europe", "Asia-Pacific", "Middle East & Africa")

# symbol, name, region, country, currency, exchange time zone. The VIX is a volatility
# index in points, not a price, so it has no currency.
WORLD_INDICES = [
    ("^GSPC", "S&P 500", "Americas", "United States", "USD", "America/New_York"),
    ("^DJI", "Dow Jones Industrial Average", "Americas", "United States", "USD", "America/New_York"),
    ("^IXIC", "Nasdaq Composite", "Americas", "United States", "USD", "America/New_York"),
    ("^GSPTSE", "S&P/TSX Composite", "Americas", "Canada", "CAD", "America/Toronto"),
    ("^RUT", "Russell 2000", "Americas", "United States", "USD", "America/New_York"),
    ("^NYA", "NYSE Composite", "Americas", "United States", "USD", "America/New_York"),
    ("^VIX", "Cboe Volatility Index (VIX)", "Americas", "United States", None, "America/Chicago"),
    ("^BVSP", "Ibovespa", "Americas", "Brazil", "BRL", "America/Sao_Paulo"),
    ("^MXX", "S&P/BMV IPC", "Americas", "Mexico", "MXN", "America/Mexico_City"),
    ("^FTSE", "FTSE 100", "Europe", "United Kingdom", "GBP", "Europe/London"),
    ("^GDAXI", "DAX", "Europe", "Germany", "EUR", "Europe/Berlin"),
    ("^FCHI", "CAC 40", "Europe", "France", "EUR", "Europe/Paris"),
    ("^STOXX50E", "Euro Stoxx 50", "Europe", "Eurozone", "EUR", "Europe/Berlin"),
    ("^STOXX", "STOXX Europe 600", "Europe", "Europe", "EUR", "Europe/Berlin"),
    ("^IBEX", "IBEX 35", "Europe", "Spain", "EUR", "Europe/Madrid"),
    ("FTSEMIB.MI", "FTSE MIB", "Europe", "Italy", "EUR", "Europe/Rome"),
    ("^AEX", "AEX", "Europe", "Netherlands", "EUR", "Europe/Amsterdam"),
    ("^SSMI", "SMI", "Europe", "Switzerland", "CHF", "Europe/Zurich"),
    ("^OMX", "OMX Stockholm 30", "Europe", "Sweden", "SEK", "Europe/Stockholm"),
    ("^N225", "Nikkei 225", "Asia-Pacific", "Japan", "JPY", "Asia/Tokyo"),
    ("^HSI", "Hang Seng", "Asia-Pacific", "Hong Kong", "HKD", "Asia/Hong_Kong"),
    ("000001.SS", "Shanghai Composite", "Asia-Pacific", "China", "CNY", "Asia/Shanghai"),
    ("399001.SZ", "Shenzhen Component", "Asia-Pacific", "China", "CNY", "Asia/Shanghai"),
    ("^TWII", "Taiwan Weighted", "Asia-Pacific", "Taiwan", "TWD", "Asia/Taipei"),
    ("^KS11", "KOSPI", "Asia-Pacific", "South Korea", "KRW", "Asia/Seoul"),
    ("^AXJO", "S&P/ASX 200", "Asia-Pacific", "Australia", "AUD", "Australia/Sydney"),
    ("^NSEI", "NIFTY 50", "Asia-Pacific", "India", "INR", "Asia/Kolkata"),
    ("^BSESN", "S&P BSE Sensex", "Asia-Pacific", "India", "INR", "Asia/Kolkata"),
    ("^NSEBANK", "Nifty Bank", "Asia-Pacific", "India", "INR", "Asia/Kolkata"),
    ("^STI", "Straits Times Index", "Asia-Pacific", "Singapore", "SGD", "Asia/Singapore"),
    ("^JKSE", "Jakarta Composite", "Asia-Pacific", "Indonesia", "IDR", "Asia/Jakarta"),
    ("^KLSE", "FTSE Bursa Malaysia KLCI", "Asia-Pacific", "Malaysia", "MYR", "Asia/Kuala_Lumpur"),
    ("^NZ50", "S&P/NZX 50", "Asia-Pacific", "New Zealand", "NZD", "Pacific/Auckland"),
    ("^TA125.TA", "TA-125", "Middle East & Africa", "Israel", "ILS", "Asia/Jerusalem"),
    ("^TASI.SR", "Tadawul All Share", "Middle East & Africa", "Saudi Arabia", "SAR", "Asia/Riyadh"),
    ("^J200.JO", "FTSE/JSE Top 40", "Middle East & Africa", "South Africa", "ZAR", "Africa/Johannesburg"),
]
INDEX_SYMBOLS = {row[0] for row in WORLD_INDICES}
CURRENCIES = {row[0]: row[4] for row in WORLD_INDICES if row[4]}


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
