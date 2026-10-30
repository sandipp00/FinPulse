"""Exchange hours: the current session, the estimated next one, and the endpoint."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from backend import config, feeds, indices, main, market_hours
from backend.market_hours import MON_FRI, SUN_THU, next_session


def at(local: str, zone: str) -> int:
    return int(datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(zone)).timestamp())


def utc(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M")


TOKYO = (at("2026-10-30T09:00", "Asia/Tokyo"), at("2026-10-30T15:30", "Asia/Tokyo"))


def test_a_session_that_has_not_ended_is_yahoos_own():
    upcoming = next_session(TOKYO, "Asia/Tokyo", MON_FRI, at("2026-10-30T08:00", "Asia/Tokyo"))
    assert upcoming == {"start": TOKYO[0], "end": TOKYO[1], "estimated": False}
    assert next_session(TOKYO, "Asia/Tokyo", MON_FRI, at("2026-10-30T12:00", "Asia/Tokyo"))["estimated"] is False


def test_after_friday_the_next_session_is_monday_at_the_same_local_hours():
    after = next_session(TOKYO, "Asia/Tokyo", MON_FRI, at("2026-10-30T16:00", "Asia/Tokyo"))
    assert (utc(after["start"]), utc(after["end"]), after["estimated"]) == ("2026-11-02 00:00", "2026-11-02 06:30", True)


def test_the_estimate_follows_a_daylight_saving_change():
    new_york = (at("2026-10-30T09:30", "America/New_York"), at("2026-10-30T16:00", "America/New_York"))
    after = next_session(new_york, "America/New_York", MON_FRI, at("2026-10-30T17:00", "America/New_York"))
    assert utc(after["start"]) == "2026-11-02 14:30"  # 09:30 EST; it was 13:30 UTC under EDT


def test_saudi_trading_days_run_sunday_to_thursday():
    riyadh = (at("2026-10-29T10:00", "Asia/Riyadh"), at("2026-10-29T15:00", "Asia/Riyadh"))
    after = next_session(riyadh, "Asia/Riyadh", SUN_THU, at("2026-10-29T16:00", "Asia/Riyadh"))
    assert utc(after["start"]) == "2026-11-01 07:00"  # Sunday


def test_every_exchange_has_a_followed_benchmark():
    assert {row[3] for row in market_hours.EXCHANGES} <= indices.INDEX_SYMBOLS


def test_endpoint_reports_each_exchange_with_or_without_a_known_session(monkeypatch):
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(feeds.yahoo_quotes, "_sessions", {"^N225": TOKYO})
    monkeypatch.setattr(market_hours, "_wall", lambda: at("2026-10-30T12:00", "Asia/Tokyo"))
    with TestClient(main.app) as client:
        body = client.get("/api/market-hours").json()

    assert body["count"] == len(market_hours.EXCHANGES)
    tokyo = next(e for e in body["exchanges"] if e["id"] == "tse")
    assert tokyo["session"] == {"start": TOKYO[0], "end": TOKYO[1], "estimated": False}
    assert tokyo["benchmark"] == "^N225" and tokyo["timezone"] == "Asia/Tokyo" and tokyo["lunch_break"] is True
    london = next(e for e in body["exchanges"] if e["id"] == "lse")
    assert london["session"] is None  # not looked up yet: unknown, not guessed
    assert any("holidays" in note for note in body["notes"])
