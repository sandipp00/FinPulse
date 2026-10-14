
from pathlib import Path
import sqlite3
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "finpulse.db"

app = FastAPI(
    title="FinPulse API",
    description="Financial market data and analytics API",
    version="1.0.0",
)

# Allow the local React/Vite frontend to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_connection():
    """Open the existing SQLite database in read-only mode."""
    if not DATABASE_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="Database not found: data/finpulse.db",
        )

    try:
        return sqlite3.connect(
            DATABASE_PATH.as_uri() + "?mode=ro",
            uri=True,
            timeout=10,
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not open database: {exc}",
        ) from exc


def fetch_prices(symbol: Optional[str] = None) -> pd.DataFrame:
    """Fetch historical market prices from SQLite."""
    connection = get_connection()

    try:
        query = """
            SELECT timestamp, symbol, asset_type,
                   open, high, low, close, volume
            FROM market_prices
        """
        params = ()

        if symbol:
            query += " WHERE symbol = ?"
            params = (symbol,)

        query += " ORDER BY symbol, timestamp"

        return pd.read_sql_query(
            query,
            connection,
            params=params,
            parse_dates=["timestamp"],
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {exc}",
        ) from exc
    finally:
        connection.close()


def safe_number(value, digits=4):
    """Convert a numeric value to a JSON-safe Python number."""
    if value is None or pd.isna(value) or not np.isfinite(value):
        return None
    return round(float(value), digits)


def calculate_metrics(group: pd.DataFrame) -> dict:
    """Calculate descriptive performance and risk metrics."""
    group = group.sort_values("timestamp").copy()
    closes = pd.to_numeric(
        group["close"], errors="coerce"
    ).dropna()

    if closes.empty:
        return {}

    first_close = float(closes.iloc[0])
    latest_close = float(closes.iloc[-1])

    previous_close = (
        float(closes.iloc[-2]) if len(closes) > 1 else None
    )

    returns = closes.pct_change().dropna()
    asset_type = str(group["asset_type"].iloc[0]).lower()

    # Annualization assumptions: crypto trades every day;
    # stocks and indices use a conventional 252-day year.
    periods_per_year = 365 if asset_type == "crypto" else 252

    volatility = None
    sharpe = None

    if len(returns) > 1:
        daily_std = float(returns.std(ddof=1))
        volatility = daily_std * np.sqrt(periods_per_year)

        # Descriptive Sharpe ratio assuming a zero risk-free rate.
        if daily_std > 0:
            sharpe = (
                float(returns.mean())
                / daily_std
                * np.sqrt(periods_per_year)
            )

    drawdowns = closes / closes.cummax() - 1
    max_drawdown = float(drawdowns.min())

    total_return = None
    if first_close != 0:
        total_return = (latest_close / first_close - 1) * 100

    daily_change = None
    if previous_close not in (None, 0):
        daily_change = (
            latest_close / previous_close - 1
        ) * 100

    return {
        "symbol": str(group["symbol"].iloc[0]),
        "asset_type": asset_type,
        "latest_timestamp": str(group["timestamp"].iloc[-1]),
        "latest_price": safe_number(latest_close),
        "daily_change_pct": safe_number(daily_change),
        "total_return_pct": safe_number(total_return),
        "annualized_volatility_pct": safe_number(
            volatility * 100 if volatility is not None else None
        ),
        "sharpe_ratio": safe_number(sharpe),
        "max_drawdown_pct": safe_number(max_drawdown * 100),
        "observations": int(len(closes)),
        "first_date": str(group["timestamp"].iloc[0]),
        "last_date": str(group["timestamp"].iloc[-1]),
    }


@app.get("/")
def root():
    return {
        "name": "FinPulse API",
        "status": "running",
        "documentation": "/docs",
    }


@app.get("/api/health")
def health():
    connection = get_connection()

    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM market_prices"
        ).fetchone()[0]

        return {
            "status": "healthy",
            "database": "connected",
            "mode": "read-only",
            "records": count,
        }
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database health check failed: {exc}",
        ) from exc
    finally:
        connection.close()


@app.get("/api/assets")
def assets():
    frame = fetch_prices()

    if frame.empty:
        return {"count": 0, "assets": []}

    results = []

    for _, group in frame.groupby("symbol", sort=True):
        metrics = calculate_metrics(group)
        if metrics:
            results.append(metrics)

    return {
        "count": len(results),
        "assets": results,
    }


@app.get("/api/prices")
def prices(
    symbol: str = Query(..., min_length=1),
    limit: int = Query(default=180, ge=1, le=2000),
):
    frame = fetch_prices(symbol)

    if frame.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No historical data found for {symbol}.",
        )

    frame = frame.sort_values("timestamp").tail(limit)

    records = frame[
        [
            "timestamp", "symbol", "asset_type",
            "open", "high", "low", "close", "volume",
        ]
    ].copy()

    records["timestamp"] = records["timestamp"].astype(str)

    return {
        "symbol": symbol,
        "count": len(records),
        "prices": records.replace(
            {np.nan: None}
        ).to_dict(orient="records"),
    }


@app.get("/api/summary")
def summary(symbol: Optional[str] = None):
    frame = fetch_prices(symbol)

    if frame.empty:
        if symbol:
            raise HTTPException(
                status_code=404,
                detail=f"No historical data found for {symbol}.",
            )
        return {"count": 0, "summaries": []}

    results = []

    for _, group in frame.groupby("symbol", sort=True):
        metrics = calculate_metrics(group)
        if metrics:
            results.append(metrics)

    return {
        "count": len(results),
        "summaries": results,
        "methodology": {
            "risk_free_rate": "Assumed zero for Sharpe ratio",
            "stock_index_periods_per_year": 252,
            "crypto_periods_per_year": 365,
            "source": "Local SQLite historical prices",
        },
    }
