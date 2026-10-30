"""The normalized market-data record and the metadata every series carries.

Whatever the provider, a number leaves the API with where it came from, when it
was observed, when we fetched it, and how fresh it is. A value that could not be
obtained is reported as unavailable, never filled in.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# real_time    pushed by the provider's stream and received recently
# delayed      the provider documents a delay (no provider uses this yet)
# historical   a stored or fetched past observation (daily closes, candle history)
# cached       a provider response kept after the provider started failing
# stale        a real-time symbol whose last update is too old
# unavailable  no observation at all
DataStatus = Literal["real_time", "delayed", "historical", "cached", "stale", "unavailable"]

AssetClass = Literal["crypto", "stock", "index", "commodity"]


class SourceMeta(BaseModel):
    """Where a series came from and how fresh it is."""

    provider: str = Field(description="Provider identifier, e.g. 'binance' or 'database'")
    endpoint: Optional[str] = Field(None, description="Host that answered, if remote")
    status: DataStatus
    retrieved_at: Optional[datetime] = Field(None, description="When FinPulse fetched it (UTC)")
    source_timestamp: Optional[datetime] = Field(
        None, description="Provider time of the newest observation (UTC)"
    )
    cache_age_seconds: Optional[float] = Field(None, description="How long ago it was fetched")
    notes: list[str] = Field(default_factory=list)


class Candle(BaseModel):
    """One OHLCV bar. `time` is the bar's open time in unix seconds (UTC)."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketRecord(BaseModel):
    """The latest observation for one instrument."""

    instrument_id: str = Field(description="Stable id: '<asset_class>:<symbol>'")
    symbol: str
    asset_class: AssetClass
    price: Optional[float] = None
    currency: Optional[str] = Field(None, description="Currency the price is quoted in; None if unknown")
    unit: str = Field(description="What the price measures, e.g. 'per coin' or 'index points'")
    provider: str
    status: DataStatus
    source_timestamp: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    interval: Optional[str] = Field(None, description="Observation frequency, e.g. 'tick' or '1d'")
    change_pct: Optional[float] = None
    change_window: Optional[str] = Field(None, description="Window of change_pct, e.g. '24h' or '1d'")
    error: Optional[str] = None


class QuotesResponse(BaseModel):
    as_of: datetime
    count: int
    quotes: list[MarketRecord]
