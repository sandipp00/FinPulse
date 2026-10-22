"""SQLite schema for historical market data, shared by the loader and the API."""

MARKET_PRICES_DDL = """
CREATE TABLE IF NOT EXISTS market_prices (
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (timestamp, symbol, asset_type)
)
"""

MARKET_PRICES_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_market_symbol_timestamp
ON market_prices (symbol, timestamp)
"""
