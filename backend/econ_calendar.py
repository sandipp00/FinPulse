"""Economic calendar: scheduled US data releases and central-bank policy meetings.

  * Release dates come from FRED (fred/release/dates, including future dates).
  * BEA publishes exact release times (JSON); those are added to BEA's releases.
    BLS releases keep the date only: BLS's machine-readable schedule refuses
    clients without a contact address, and FinPulse does not guess a time.
  * FOMC and ECB policy meetings are a small hand-maintained list, copied from
    the central banks' own calendars (checked 2026-10-30); each carries its link.

There is no consensus forecast: free, legitimate sources do not publish one, so
the field is always empty. Released values are on the Macro page.
"""
import asyncio
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from backend import config, fred

log = logging.getLogger("finpulse.calendar")

CACHE_SECONDS = 6 * 3600
BEA_DATES_URL = "https://apps.bea.gov/API/signup/release_dates.json"

# FRED release id -> what it is. `bea_name` keys BEA's release_dates.json.
RELEASES = {
    10: {"title": "Consumer Price Index", "agency": "BLS", "series": ["CPIAUCSL"],
         "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm"},
    50: {"title": "Employment Situation (jobs report)", "agency": "BLS", "series": ["UNRATE", "PAYEMS"],
         "source_url": "https://www.bls.gov/schedule/news_release/empsit.htm"},
    53: {"title": "Gross Domestic Product", "agency": "BEA", "series": ["GDPC1"],
         "source_url": "https://www.bea.gov/news/schedule", "bea_name": "Gross Domestic Product"},
    54: {"title": "Personal Income and Outlays (PCE prices)", "agency": "BEA", "series": ["PCEPILFE"],
         "source_url": "https://www.bea.gov/news/schedule", "bea_name": "Personal Income and Outlays"},
}

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"

# (first day, decision day, with Summary of Economic Projections). 2027 is tentative.
FOMC_MEETINGS = [
    ("2026-01-27", "2026-01-28", False), ("2026-03-17", "2026-03-18", True),
    ("2026-04-28", "2026-04-29", False), ("2026-06-16", "2026-06-17", True),
    ("2026-07-28", "2026-07-29", False), ("2026-09-15", "2026-09-16", True),
    ("2026-10-27", "2026-10-28", False), ("2026-12-08", "2026-12-09", True),
    ("2027-01-26", "2027-01-27", False), ("2027-03-16", "2027-03-17", True),
    ("2027-04-27", "2027-04-28", False), ("2027-06-08", "2027-06-09", True),
    ("2027-07-27", "2027-07-28", False), ("2027-09-14", "2027-09-15", True),
    ("2027-10-26", "2027-10-27", False), ("2027-12-07", "2027-12-08", True),
]
FOMC_TENTATIVE_FROM = "2027-01-01"

# ECB Governing Council monetary policy decisions (day 2, with press conference).
ECB_DECISIONS = [
    "2026-10-29", "2026-12-17",
    "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-10",
    "2027-07-22", "2027-09-09", "2027-10-28", "2027-12-16",
]

CALENDAR_CHECKED = "2026-10-30"

_monotonic = time.monotonic
_wall = time.time
_cache: dict[str, tuple[float, object]] = {}
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=20)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    _cache.clear()


def _status(day: date, today: date) -> str:
    return "past" if day < today else "today" if day == today else "scheduled"


def meeting_events(today: date) -> list[dict]:
    events = []
    for first, decision, sep in FOMC_MEETINGS:
        day = date.fromisoformat(decision)
        tentative = decision >= FOMC_TENTATIVE_FROM or day > today
        events.append({
            "date": decision, "time_utc": None, "kind": "meeting", "agency": "Federal Reserve",
            "title": "FOMC meeting: rate decision" + (" with economic projections" if sep else ""),
            "detail": f"Meeting {first} to {decision}.",
            "series": ["FEDFUNDS"], "status": _status(day, today),
            "tentative": decision >= FOMC_TENTATIVE_FROM,
            "note": "Tentative until confirmed at the preceding meeting." if tentative and day > today else None,
            "source": "Federal Reserve FOMC calendar", "source_url": FOMC_URL, "consensus": None,
        })
    for decision in ECB_DECISIONS:
        day = date.fromisoformat(decision)
        events.append({
            "date": decision, "time_utc": None, "kind": "meeting", "agency": "ECB",
            "title": "ECB monetary policy decision", "detail": "Governing Council meeting, day 2, with press conference.",
            "series": [], "status": _status(day, today), "tentative": False, "note": None,
            "source": "ECB meeting calendar", "source_url": ECB_URL, "consensus": None,
        })
    return events


def parse_bea_times(body) -> dict[str, dict[str, str]]:
    """BEA release_dates.json -> {release name: {YYYY-MM-DD: ISO UTC time}}."""
    if not isinstance(body, dict):
        raise ValueError("BEA release dates are not a JSON object")
    times: dict[str, dict[str, str]] = {}
    for name, entry in body.items():
        stamps = entry.get("release_dates") if isinstance(entry, dict) else None
        if not isinstance(stamps, list):
            continue
        for stamp in stamps:
            try:
                moment = datetime.fromisoformat(str(stamp))
            except ValueError:
                continue
            if moment.tzinfo is None:
                continue
            moment = moment.astimezone(timezone.utc)
            times.setdefault(name, {})[moment.date().isoformat()] = moment.isoformat().replace("+00:00", "Z")
    return times


async def _cached(key: str, loader):
    hit = _cache.get(key)
    if hit and _monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = await loader()
    _cache[key] = (_monotonic(), value)
    return value


async def _bea_times() -> dict[str, dict[str, str]]:
    async def load():
        response = await get_client().get(BEA_DATES_URL, headers={"User-Agent": config.FEED_USER_AGENT})
        response.raise_for_status()
        return parse_bea_times(response.json())
    return await _cached("bea", load)


async def _release_dates(release_id: int, start: date) -> list[str]:
    async def load():
        body = await fred._get("release/dates", {
            "release_id": release_id,
            "realtime_start": start.isoformat(),
            "realtime_end": "9999-12-31",
            "include_release_dates_with_no_data": "true",
            "sort_order": "asc",
            "limit": 200,
        })
        rows = body.get("release_dates")
        if not isinstance(rows, list):
            raise fred.FredError(f"FRED sent no release dates for release {release_id}")
        dates = []
        for row in rows:
            try:
                dates.append(date.fromisoformat(str(row.get("date"))).isoformat())
            except (AttributeError, ValueError):
                continue
        return sorted(set(dates))
    return await _cached(f"fred:{release_id}:{start.isoformat()}", load)


async def build(days_back: int, days_ahead: int, now: Optional[datetime] = None) -> dict:
    now = now or datetime.fromtimestamp(_wall(), tz=timezone.utc)
    today = now.date()
    start, end = today - timedelta(days=days_back), today + timedelta(days=days_ahead)
    notes: list[str] = []
    events = [e for e in meeting_events(today) if start.isoformat() <= e["date"] <= end.isoformat()]

    if not fred.configured():
        notes.append("Data releases need FRED_API_KEY; only central-bank meetings are shown.")
    else:
        bea: dict[str, dict[str, str]] = {}
        try:
            bea = await _bea_times()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            notes.append(f"BEA release times unavailable ({type(exc).__name__}); BEA releases show dates only.")

        ids = list(RELEASES)
        results = await asyncio.gather(*(_release_dates(i, start) for i in ids), return_exceptions=True)
        for release_id, result in zip(ids, results):
            info = RELEASES[release_id]
            if isinstance(result, fred.FredError):
                notes.append(f"{info['title']}: {result}")
                continue
            if isinstance(result, Exception):
                raise result
            for day in result:
                if not start.isoformat() <= day <= end.isoformat():
                    continue
                events.append({
                    "date": day,
                    "time_utc": bea.get(info.get("bea_name", ""), {}).get(day),
                    "kind": "release", "agency": info["agency"], "title": info["title"], "detail": None,
                    "series": info["series"], "status": _status(date.fromisoformat(day), today),
                    "tentative": False, "note": None,
                    "source": "FRED release calendar" + (" + BEA schedule" if info.get("bea_name") else ""),
                    "source_url": info["source_url"], "consensus": None,
                })

    events.sort(key=lambda e: (e["date"], e["time_utc"] or "99", e["title"]))
    return {
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "from": start.isoformat(), "to": end.isoformat(),
        "count": len(events), "events": events, "notes": notes,
        "meetings_checked": CALENDAR_CHECKED,
        "consensus_note": "No consensus forecasts: free, legitimate sources do not publish them.",
    }
