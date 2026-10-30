"""The US stocks the terminal follows: the 30 largest US companies by market cap.

Chosen on 2026-10-31 from Yahoo Finance's market caps (foreign companies listed in
the US, such as TSMC and ASML, left out). Names and sectors are Yahoo's. Prices
come from the Yahoo quote poller (backend/quotes_live.py), charts and daily
history from Yahoo's chart API, news from each stock's Yahoo headline feed; this
module only says what each stock is. Every symbol here must also be in
config.YAHOO_LIVE_SYMBOLS (a test checks it).
"""

# Sector tabs, in this order (Yahoo's sector names).
SECTORS = (
    "Technology", "Communication Services", "Consumer Cyclical", "Consumer Defensive",
    "Financial Services", "Healthcare", "Energy",
)

# symbol, name, sector, headline keywords (regexes; a headline must match one). Tickers
# that are common words or letters (V, MA, KO, PG, MU, COST) are not keywords.
US_STOCKS = [
    ("AAPL", "Apple Inc.", "Technology", (r"\bapple\b", r"\bAAPL\b", r"\biphone\b")),
    ("NVDA", "NVIDIA Corporation", "Technology", (r"\bnvidia\b", r"\bNVDA\b")),
    ("MSFT", "Microsoft Corporation", "Technology", (r"\bmicrosoft\b", r"\bMSFT\b")),
    ("GOOGL", "Alphabet Inc.", "Communication Services", (r"\balphabet\b", r"\bgoogle\b", r"\bGOOGL?\b")),
    ("AMZN", "Amazon.com, Inc.", "Consumer Cyclical", (r"\bamazon\b", r"\bAMZN\b", r"\bAWS\b")),
    ("META", "Meta Platforms, Inc.", "Communication Services",
     (r"\bmeta\b", r"\bfacebook\b", r"\binstagram\b", r"\bwhatsapp\b")),
    ("TSLA", "Tesla, Inc.", "Consumer Cyclical", (r"\btesla\b", r"\bTSLA\b")),
    ("AVGO", "Broadcom Inc.", "Technology", (r"\bbroadcom\b", r"\bAVGO\b")),
    ("LLY", "Eli Lilly and Company", "Healthcare", (r"\blilly\b", r"\bLLY\b")),
    ("BRK-B", "Berkshire Hathaway Inc.", "Financial Services", (r"\bberkshire\b", r"\bbuffett\b")),
    ("WMT", "Walmart Inc.", "Consumer Defensive", (r"\bwalmart\b", r"\bWMT\b")),
    ("MU", "Micron Technology, Inc.", "Technology", (r"\bmicron\b",)),
    ("JPM", "JPMorgan Chase & Co.", "Financial Services", (r"\bjpmorgan\b", r"\bJPM\b", r"\bdimon\b")),
    ("AMD", "Advanced Micro Devices, Inc.", "Technology", (r"\bAMD\b", r"\badvanced micro\b")),
    ("V", "Visa Inc.", "Financial Services", (r"\bvisa\b",)),
    ("XOM", "ExxonMobil Holdings Corporation", "Energy", (r"\bexxon", r"\bXOM\b")),
    ("JNJ", "Johnson & Johnson", "Healthcare", (r"\bjohnson & johnson\b", r"\bJ&J\b", r"\bJNJ\b")),
    ("MA", "Mastercard Incorporated", "Financial Services", (r"\bmastercard\b",)),
    ("ABBV", "AbbVie Inc.", "Healthcare", (r"\babbvie\b", r"\bABBV\b")),
    ("CVX", "Chevron Corporation", "Energy", (r"\bchevron\b", r"\bCVX\b")),
    ("COST", "Costco Wholesale Corporation", "Consumer Defensive", (r"\bcostco\b",)),
    ("PLTR", "Palantir Technologies Inc.", "Technology", (r"\bpalantir\b", r"\bPLTR\b")),
    ("CSCO", "Cisco Systems, Inc.", "Technology", (r"\bcisco\b", r"\bCSCO\b")),
    ("KO", "The Coca-Cola Company", "Consumer Defensive", (r"\bcoca-cola\b", r"\bcoke\b")),
    ("ORCL", "Oracle Corporation", "Technology", (r"\boracle\b", r"\bORCL\b")),
    ("PG", "The Procter & Gamble Company", "Consumer Defensive", (r"\bprocter\b", r"\bP&G\b")),
    ("MRK", "Merck & Co., Inc.", "Healthcare", (r"\bmerck\b", r"\bMRK\b")),
    ("UNH", "UnitedHealth Group Incorporated", "Healthcare", (r"\bunitedhealth\b", r"\bUNH\b")),
    ("BAC", "Bank of America Corporation", "Financial Services", (r"\bbank of america\b", r"\bBofA\b")),
    ("INTC", "Intel Corporation", "Technology", (r"\bintel\b", r"\bINTC\b")),
]
STOCK_SYMBOLS = [row[0] for row in US_STOCKS]
SECTOR_OF = {row[0]: row[2] for row in US_STOCKS}
CURRENCIES = dict.fromkeys(STOCK_SYMBOLS, "USD")
