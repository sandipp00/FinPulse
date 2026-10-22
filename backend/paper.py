"""Paper-trading API: a virtual account that trades at live exchange prices.

Prices always come from the server's own live feed; the client can never name
a price. Everything here is simulated, so no real orders are placed.
"""
import asyncio
import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from backend import candles as candle_source, config, signal_service
from backend.auth import verified_user
from backend.live import feed
from src.portfolio.paper import OrderError, PaperBroker

# Every paper-trading route belongs to a signed-in user whose email is confirmed
# (when this server requires that); none are public.
router = APIRouter(
    prefix="/api/paper",
    tags=["paper trading"],
    dependencies=[Depends(verified_user)],
)

EQUITY_SNAPSHOT_SECONDS = 60
BUY_RATINGS = {"Strong Buy", "Buy"}
SELL_RATINGS = {"Strong Sell", "Sell"}
DISCLAIMER = (
    "Paper trading uses virtual money and live prices with no slippage. "
    "Real trades would fill differently. Not investment advice."
)


def get_broker(user: dict = Depends(verified_user)) -> PaperBroker:
    """The signed-in user's own account (one broker per request)."""
    return PaperBroker(
        config.DATABASE_PATH,
        user["id"],
        fee_rate=config.PAPER_FEE_PCT / 100,
        starting_cash=config.PAPER_STARTING_CASH,
    )


def _require_symbol(symbol: str) -> None:
    if symbol not in config.LIVE_SYMBOLS:
        raise HTTPException(
            status_code=404,
            detail=f"{symbol} is not tradable. Available: {', '.join(config.LIVE_SYMBOLS)}",
        )


def live_price(symbol: str) -> float:
    """The current exchange price, or a 503 if there is no fresh one."""
    tick = feed.latest.get(symbol)
    if tick is None:
        raise HTTPException(
            status_code=503,
            detail=f"No live price for {symbol} yet. Is the live feed connected?",
        )
    age = time.time() - tick.get("received_at", 0)
    if age > config.PAPER_MAX_PRICE_AGE_SECONDS:
        raise HTTPException(
            status_code=503,
            detail=f"The live price for {symbol} is {age:.0f}s old; refusing to trade on it.",
        )
    return tick["price"]


def fresh_prices() -> dict[str, float]:
    now = time.time()
    return {
        symbol: tick["price"]
        for symbol, tick in feed.latest.items()
        if now - tick.get("received_at", 0) <= config.PAPER_MAX_PRICE_AGE_SECONDS
    }


class OrderRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Optional[float] = Field(default=None, gt=0, description="Size in coins")
    notional_usd: Optional[float] = Field(default=None, gt=0, description="Size in USD")
    percent: Optional[float] = Field(
        default=None, gt=0, le=100,
        description="% of cash (buy) or of the position (sell)",
    )

    @model_validator(mode="after")
    def exactly_one_size(self):
        given = [v for v in (self.quantity, self.notional_usd, self.percent) if v is not None]
        if len(given) != 1:
            raise ValueError("Give exactly one of quantity, notional_usd or percent.")
        return self


class FollowRequest(BaseModel):
    symbol: str
    interval: Literal["1m", "15m", "1h", "1d"] = "1d"
    percent: float = Field(default=25, ge=1, le=100, description="% of cash to buy with")


class ResetRequest(BaseModel):
    starting_cash: Optional[float] = Field(default=None, ge=1_000, le=10_000_000)


def _snapshot_equity_if_due(broker: PaperBroker, portfolio: dict) -> None:
    """Store an equity point at most once a minute, and only with full prices."""
    if not portfolio["all_prices_available"]:
        return
    last = broker.last_equity_ts()
    if last is None or time.time() * 1000 - last >= EQUITY_SNAPSHOT_SECONDS * 1000:
        broker.record_equity(portfolio["totals"]["equity"])


def _portfolio_response(broker: PaperBroker) -> dict:
    portfolio = broker.portfolio(fresh_prices())
    _snapshot_equity_if_due(broker, portfolio)
    return {**portfolio, "disclaimer": DISCLAIMER}


def _execute(broker: PaperBroker, request: OrderRequest, **extra) -> dict:
    _require_symbol(request.symbol)
    price = live_price(request.symbol)
    try:
        order = broker.place_order(
            request.symbol, request.side, price,
            quantity=request.quantity,
            notional=request.notional_usd,
            percent=request.percent,
            **extra,
        )
    except OrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Record the new equity right away so the curve shows the order's effect.
    portfolio = broker.portfolio(fresh_prices())
    if portfolio["all_prices_available"]:
        broker.record_equity(portfolio["totals"]["equity"])
    return order


@router.get("/portfolio")
def portfolio(broker: PaperBroker = Depends(get_broker)):
    return _portfolio_response(broker)


@router.get("/orders")
def orders(limit: int = 50, broker: PaperBroker = Depends(get_broker)):
    return {"orders": broker.orders(max(1, min(limit, 200)))}


@router.get("/equity")
def equity(limit: int = 500, broker: PaperBroker = Depends(get_broker)):
    return {"points": broker.equity_history(max(2, min(limit, 2000)))}


@router.post("/orders")
def place_order(request: OrderRequest, broker: PaperBroker = Depends(get_broker)):
    order = _execute(broker, request)
    return {"order": order, "portfolio": _portfolio_response(broker)}


@router.post("/follow")
async def follow_signal(request: FollowRequest, broker: PaperBroker = Depends(get_broker)):
    """Trade the way the backtest does: buy a Buy when flat, sell all on a Sell.

    The rating is computed on the server from closed candles, so the client
    cannot fake a signal.
    """
    _require_symbol(request.symbol)

    try:
        signal = await signal_service.signal_for(request.symbol, request.interval)
    except candle_source.CandleSourceError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not load candles from the exchange: {exc}"
        ) from exc

    rating = signal["rating"]
    holding = any(p["symbol"] == request.symbol for p in await asyncio.to_thread(broker.positions))

    if rating in BUY_RATINGS and not holding:
        order_request = OrderRequest(symbol=request.symbol, side="buy", percent=request.percent)
    elif rating in SELL_RATINGS and holding:
        order_request = OrderRequest(symbol=request.symbol, side="sell", percent=100)
    else:
        reason = (
            f"Rating is {rating}: already holding, nothing to buy." if rating in BUY_RATINGS
            else f"Rating is {rating}: no position to sell." if rating in SELL_RATINGS
            else f"Rating is {rating}: the rules say to stay put."
        )
        return {
            "action": "none",
            "rating": rating,
            "reason": reason,
            "order": None,
            "portfolio": await asyncio.to_thread(_portfolio_response, broker),
        }

    order = await asyncio.to_thread(
        _execute, broker, order_request, source="signal", rating=rating
    )
    return {
        "action": order["side"],
        "rating": rating,
        "reason": f"Rating is {rating}: {order['side']} executed.",
        "order": order,
        "portfolio": await asyncio.to_thread(_portfolio_response, broker),
    }


@router.post("/reset")
def reset(request: ResetRequest, broker: PaperBroker = Depends(get_broker)):
    broker.reset(request.starting_cash)
    return _portfolio_response(broker)
