
import asyncio
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend import (
    auth, candles as candle_source, config, db, fred, fx, fx_api, instruments, macro,
    market_service, paper, risk_service, signal_service,
)
from backend.errors import exchange_error
from backend.live import feed
from backend.schemas.market import QuotesResponse
from src.analytics.financial_metrics import asset_snapshot

DATABASE_PATH = config.DATABASE_PATH


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    auth.warn_about_email_config()
    if config.LIVE_FEED_ENABLED:
        feed.start()
    yield
    if config.LIVE_FEED_ENABLED:
        await feed.stop()
    await candle_source.close_client()
    await fred.close_client()
    await fx.close_client()


app = FastAPI(
    title="FinPulse API",
    description="Financial market data and analytics API",
    version="1.2.0",
    lifespan=lifespan,
    # Blocks state-changing requests that come from another website.
    dependencies=[Depends(auth.check_origin)],
)

# Allow the configured frontend origins (CORS_ORIGINS) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,  # the session cookie; origins are an explicit list, never "*"
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(paper.router)
app.include_router(instruments.router)
app.include_router(macro.router)
app.include_router(fx_api.router)


def get_connection():
    """Open the market-data database for reading only.

    `query_only` makes SQLite reject any write on this connection. It is used
    instead of a read-only file URI because that mode cannot read a database
    in WAL mode when the -shm file does not exist yet.
    """
    if not DATABASE_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="Database not found: data/finpulse.db",
        )

    try:
        connection = sqlite3.connect(DATABASE_PATH, timeout=10)
        connection.execute("PRAGMA query_only = ON")
        return connection
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


@app.get("/api/market/quotes", response_model=QuotesResponse)
def market_quotes():
    """The latest observation per instrument, normalized, with source and freshness.

    Live symbols come from the exchange feed; the rest are the latest stored
    daily close. If the stored history cannot be read, live quotes are still
    returned and stored instruments are simply absent.
    """
    try:
        stored = assets()["assets"]
    except HTTPException:
        stored = []

    quotes = market_service.build_quotes(
        config.LIVE_SYMBOLS, dict(feed.latest), feed.connected, stored
    )
    return {
        "as_of": pd.Timestamp.now(tz="UTC").to_pydatetime(),
        "count": len(quotes),
        "quotes": quotes,
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


@app.get("/api/candles")
async def candles(
    symbol: str = Query(..., min_length=1),
    interval: str = Query(default="1h"),
    limit: int = Query(
        default=500,
        ge=candle_source.MIN_LIMIT,
        le=candle_source.MAX_LIMIT,
    ),
):
    """OHLCV candles for a live crypto symbol, oldest first."""
    _require_live_symbol(symbol)
    _require_interval(interval)

    try:
        series = await candle_source.fetch_candle_series(symbol, interval, limit, allow_stale=True)
    except candle_source.CandleSourceError as exc:
        raise exchange_error(exc) from exc

    return {
        "symbol": symbol,
        "interval": interval,
        "count": len(series.candles),
        "candles": series.candles,
        "meta": series.meta.model_dump(mode="json"),
    }


def _require_live_symbol(symbol: str) -> None:
    if symbol not in config.LIVE_SYMBOLS:
        raise HTTPException(
            status_code=404,
            detail=f"{symbol} is not a live symbol. "
                   f"Available: {', '.join(config.LIVE_SYMBOLS)}",
        )


def _require_interval(interval: str) -> None:
    if interval not in candle_source.INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported interval. Use one of: "
                   f"{', '.join(candle_source.INTERVALS)}",
        )


@app.get("/api/signals")
async def signals(
    interval: str = Query(default="1h"),
    symbol: Optional[str] = None,
):
    """Buy/sell ratings from the rule-based engine, with the reasons for each.

    Ratings use closed candles only, so they change at most once per candle.
    """
    _require_interval(interval)
    symbols = config.LIVE_SYMBOLS
    if symbol:
        _require_live_symbol(symbol)
        symbols = [symbol]

    try:
        results = await signal_service.signals_for(symbols, interval)
    except candle_source.CandleSourceError as exc:
        raise exchange_error(exc) from exc

    return {
        "interval": interval,
        "count": len(results),
        "signals": results,
        "disclaimer": signal_service.DISCLAIMER,
    }


@app.get("/api/backtest")
async def backtest(
    symbol: str = Query(..., min_length=1),
    interval: str = Query(default="1d"),
    fee_pct: float = Query(default=0.1, ge=0, le=2, description="Fee per fill, in percent"),
):
    """Historical performance of the signal rules on this symbol and timeframe."""
    _require_live_symbol(symbol)
    _require_interval(interval)

    try:
        result = await signal_service.backtest_for(symbol, interval, fee_pct / 100)
    except candle_source.CandleSourceError as exc:
        raise exchange_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {**result, "disclaimer": signal_service.DISCLAIMER}


@app.get("/api/risk")
async def risk():
    """Volatility, drawdown, value at risk and correlations for every tracked asset."""
    return await risk_service.build_report()


@app.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    """Stream live ticks: a snapshot first, then each update as it arrives."""
    # Prices are public, but a page on another site has no business streaming
    # them through its visitors' browsers (and this keeps one rule for all routes).
    if not auth.origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

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
