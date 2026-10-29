"""News and economic-calendar routes (backend/news.py, backend/econ_calendar.py)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend import econ_calendar, news

router = APIRouter(tags=["news"])


@router.get("/api/news")
async def news_items(
    topic: Optional[str] = Query(default=None, max_length=20),
    instrument: Optional[str] = Query(default=None, max_length=20),
    source: Optional[str] = Query(default=None, max_length=20),
    limit: int = Query(default=60, ge=1, le=200),
):
    """Headlines with links to the originals, newest first, filterable by topic, instrument and source."""
    if topic and topic not in news.TOPICS:
        raise HTTPException(status_code=400, detail=f"Unknown topic. Use one of: {', '.join(news.TOPICS)}")
    if instrument and instrument not in news.INSTRUMENT_PATTERNS:
        raise HTTPException(status_code=400, detail=f"Unknown instrument. Use one of: {', '.join(news.INSTRUMENT_PATTERNS)}")
    if source and source not in {s.id for s in news.SOURCES}:
        raise HTTPException(status_code=400, detail=f"Unknown source. Use one of: {', '.join(s.id for s in news.SOURCES)}")

    items, sources = await news.collect()
    if topic:
        items = [i for i in items if topic in i["topics"]]
    if instrument:
        items = [i for i in items if instrument in i["instruments"]]
    if source:
        items = [i for i in items if i["source"] == source]

    return {
        "count": min(len(items), limit),
        "total": len(items),
        "items": items[:limit],
        "sources": sources,
        "topics": list(news.TOPICS),
        "instruments": list(news.INSTRUMENT_PATTERNS),
        "policy": "Headlines and short snippets only, each linking to the original publication.",
    }


@router.get("/api/calendar")
async def calendar(
    days_back: int = Query(default=14, ge=0, le=120),
    days_ahead: int = Query(default=60, ge=0, le=400),
):
    """Scheduled US data releases and FOMC/ECB policy meetings in the window, by date."""
    return await econ_calendar.build(days_back, days_ahead)
