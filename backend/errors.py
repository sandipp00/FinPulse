"""HTTP errors shared by the routes that call the exchange."""
from fastapi import HTTPException

from backend import candles as candle_source


def exchange_error(exc: candle_source.CandleSourceError) -> HTTPException:
    """502 when the exchange failed; 503 with Retry-After when it is rate limiting us."""
    if exc.retry_after is not None:
        return HTTPException(
            status_code=503,
            detail=f"The exchange is rate limiting requests: {exc}",
            headers={"Retry-After": str(max(1, round(exc.retry_after)))},
        )
    return HTTPException(
        status_code=502,
        detail=f"Could not load candles from the exchange: {exc}",
    )
