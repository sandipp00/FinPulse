
import asyncio
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.live import feed
from src.analytics.financial_metrics import asset_snapshot

DATABASE_PATH = config.DATABASE_PATH


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if config.LIVE_FEED_ENABLED:
        feed.start()
    yield
    if config.LIVE_FEED_ENABLED:
        await feed.stop()


app = FastAPI(
    title="FinPulse API",
    description="Financial market data and analytics API",
    version="1.1.0",
    lifespan=lifespan,
)

# Allow the configured frontend origins (CORS_ORIGINS) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
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


ROUNDED_FIELDS = (
    "latest_price", "daily_change_pct", "total_return_pct",
    "annualized_volatility_pct", "sharpe_ratio", "max_drawdown_pct",
)


def calculate_metrics(group: pd.DataFrame) -> dict:
    """Shared snapshot metrics, made JSON-safe."""
    metrics = asset_snapshot(group)
    for field in ROUNDED_FIELDS:
        if field in metrics:
            metrics[field] = safe_number(metrics[field])
    return metrics


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


@app.get("/api/live/status")
def live_status():
    return {"enabled": config.LIVE_FEED_ENABLED, **feed.status()}


@app.get("/api/live/ticks")
def live_ticks():
    """Latest in-memory tick per live symbol (REST fallback for the socket)."""
    return {
        "connected": feed.connected,
        "ticks": [feed.latest[s] for s in feed.symbols if s in feed.latest],
    }


@app.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    """Stream live ticks: a snapshot first, then each update as it arrives."""
    await websocket.accept()

    if not config.LIVE_FEED_ENABLED:
        await websocket.close(code=1013, reason="Live feed disabled")
        return

    queue = feed.subscribe()
    try:
        await websocket.send_json({
            "type": "snapshot",
            "connected": feed.connected,
            "ticks": [feed.latest[s] for s in feed.symbols if s in feed.latest],
        })

        while True:
            await websocket.send_json(await queue.get())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        feed.unsubscribe(queue)
