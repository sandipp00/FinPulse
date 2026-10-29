"""FRED macro data: parsing, failures, caching, key secrecy and the API routes.

FRED is mocked (httpx.MockTransport) and every test sets its own fake key, so the
suite never sends a real key anywhere, even when one is configured in .env.
"""
import asyncio
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import config, fred, main

FAKE_KEY = "abcdefghijklmnopqrstuvwxyz012345"


def info_body(series_id="UNRATE", **extra):
    return {"seriess": [{
        "id": series_id, "title": "Unemployment Rate", "units": "Percent", "units_short": "%",
        "frequency": "Monthly", "frequency_short": "M", "seasonal_adjustment_short": "SA",
        "last_updated": "2026-10-03 07:48:02-05", "notes": "Public data.", **extra,
    }]}


def obs_body(rows):
    return {"observations": [{"realtime_start": "x", "realtime_end": "x", "date": d, "value": v} for d, v in rows]}


GOOD_OBS = [("2026-07-01", "4.1"), ("2026-08-01", "."), ("2026-09-01", "4.3")]


class Clock:
    def __init__(self):
        self.mono = 5000.0
        self.wall = 1_793_000_000.0  # 2026-10-26

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(fred, "_monotonic", lambda: clock.mono)
    monkeypatch.setattr(fred, "_wall", lambda: clock.wall)
    return clock


@pytest.fixture(autouse=True)
def server(monkeypatch, clock):
    """A fake FRED. Set `server.handler(request) -> httpx.Response`."""
    monkeypatch.setattr(config, "FRED_API_KEY", FAKE_KEY)
    monkeypatch.setattr(config, "FRED_BASE_URL", "https://fred.example/fred")
    fred._cache.clear()
    monkeypatch.setattr(fred, "_blocked_until", 0.0)

    class Server:
        requests = []
        handler = None

    def default(request):
        series_id = request.url.params["series_id"]
        if request.url.path.endswith("/observations"):
            return httpx.Response(200, json=obs_body(GOOD_OBS))
        return httpx.Response(200, json=info_body(series_id))

    def handle(request):
        Server.requests.append(request)
        return (Server.handler or default)(request)

    monkeypatch.setattr(fred, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    yield Server
    fred._cache.clear()


def fetch(series_id="UNRATE"):
    return asyncio.run(fred.fetch_series(series_id))


# ---- parsing -------------------------------------------------------------

def test_observations_keep_missing_values_missing():
    observations, missing = fred.parse_observations(obs_body(GOOD_OBS), "UNRATE")

    assert observations == [
        {"date": "2026-07-01", "value": 4.1},
        {"date": "2026-08-01", "value": None},
        {"date": "2026-09-01", "value": 4.3},
    ]
    assert missing == 1


@pytest.mark.parametrize("value", [".", "", None, "abc", "NaN", "inf"])
def test_any_non_numeric_value_counts_as_missing(value):
    observations, missing = fred.parse_observations(obs_body([("2026-01-01", value)]), "X")
    assert observations[0]["value"] is None and missing == 1


@pytest.mark.parametrize("body, reason", [
    ({}, "no observations list"),
    ({"observations": "nope"}, "no observations list"),
    ({"observations": ["x"]}, "not an object"),
    (obs_body([("2026-13-01", "1")]), "invalid date"),
    (obs_body([("2026-02-01", "1"), ("2026-01-01", "2")]), "increasing"),
    (obs_body([("2026-01-01", "1"), ("2026-01-01", "2")]), "increasing"),
])
def test_malformed_observations_are_rejected(body, reason):
    with pytest.raises(fred.FredError, match=reason):
        fred.parse_observations(body, "X")


@pytest.mark.parametrize("body, reason", [
    ({}, "no metadata"),
    ({"seriess": []}, "no metadata"),
    (info_body("OTHER"), "not UNRATE"),
    (info_body(title=""), "no title"),
])
def test_malformed_metadata_is_rejected(body, reason):
    with pytest.raises(fred.FredError, match=reason):
        fred.parse_info(body, "UNRATE")


def test_last_updated_keeps_its_offset():
    parsed = fred.parse_last_updated("2026-10-03 07:48:02-05")
    assert parsed.isoformat() == "2026-10-03T07:48:02-05:00"
    assert fred.parse_last_updated("garbage") is None
    assert fred.parse_last_updated(None) is None


def test_latest_two_skips_missing_values():
    latest, previous = fred.latest_two([
        {"date": "a", "value": 1.0}, {"date": "b", "value": 2.0}, {"date": "c", "value": None},
    ])
    assert latest["date"] == "b" and previous["date"] == "a"
    assert fred.latest_two([]) == (None, None)


# ---- requests --------------------------------------------------------------

def test_requests_ask_for_json_and_ten_years(server):
    fetch()

    info, obs = server.requests
    assert info.url.path == "/fred/series"
    assert obs.url.path == "/fred/series/observations"
    assert obs.url.params["file_type"] == "json"
    assert obs.url.params["sort_order"] == "asc"
    assert obs.url.params["observation_start"] == "2016-10-28"
    assert obs.url.params["api_key"] == FAKE_KEY


def test_only_curated_series_can_be_fetched(server):
    with pytest.raises(KeyError):
        fetch("ANYTHING")
    assert server.requests == []


def test_no_key_means_no_request(server, monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", None)
    with pytest.raises(fred.FredNotConfigured):
        fetch()
    assert server.requests == []


def test_copyrighted_series_are_flagged(server):
    server.handler = lambda r: httpx.Response(200, json=(
        obs_body(GOOD_OBS) if r.url.path.endswith("/observations")
        else info_body(notes="Copyright, 2026, Some Index Provider. Reprinted with permission.")
    ))
    assert "copyrighted" in fetch().notes[0]


# ---- failures and the key ----------------------------------------------------

def test_fred_error_messages_are_passed_on_without_the_key(server):
    server.handler = lambda r: httpx.Response(400, json={
        "error_code": 400, "error_message": f"Bad Request.  The value for variable api_key is not registered. ({FAKE_KEY})",
    })
    with pytest.raises(fred.FredError) as raised:
        fetch()
    assert "not registered" in str(raised.value)
    assert FAKE_KEY not in str(raised.value)


def test_network_errors_never_include_the_url_or_key(server):
    def boom(request):
        raise httpx.ConnectError(f"failed to connect to {request.url}", request=request)

    server.handler = boom
    with pytest.raises(fred.FredError) as raised:
        fetch()
    assert str(raised.value) == "Could not reach FRED (ConnectError)"
    assert FAKE_KEY not in str(raised.value)


def test_the_key_is_not_logged(server, caplog):
    server.handler = lambda r: httpx.Response(500, text="oops")
    caplog.set_level(logging.DEBUG)
    with pytest.raises(fred.FredError):
        fetch()
    # httpx would log the request URL (with the key) at INFO; it is held at WARNING.
    assert FAKE_KEY not in caplog.text


def test_a_timeout_is_reported_plainly(server):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    server.handler = slow
    with pytest.raises(fred.FredError, match="did not answer in time"):
        fetch()


def test_rate_limiting_backs_off_without_more_requests(server, clock):
    server.handler = lambda r: httpx.Response(429, json={"error_code": 429, "error_message": "Too Many Requests"})
    with pytest.raises(fred.FredError) as raised:
        fetch()
    assert raised.value.retry_after == fred.RATE_LIMIT_BACKOFF_SECONDS

    server.requests.clear()
    clock.advance(10)
    with pytest.raises(fred.FredError, match="retry in 50s"):
        fetch()
    assert server.requests == []  # blocked locally, FRED is not asked again


def test_a_non_json_body_is_an_error(server):
    server.handler = lambda r: httpx.Response(200, text="<html>maintenance</html>")
    with pytest.raises(fred.FredError, match="not a JSON object"):
        fetch()


# ---- caching -----------------------------------------------------------------

def test_responses_are_cached_for_an_hour(server, clock):
    fetch()
    clock.advance(fred.CACHE_SECONDS - 1)
    fetch()
    assert len(server.requests) == 2  # one metadata + one observations call


def test_a_failing_fred_serves_the_last_response_with_a_note(server, clock):
    first = fetch()
    clock.advance(fred.CACHE_SECONDS + 1)
    server.handler = lambda r: httpx.Response(500, json={"error_code": 500, "error_message": "Internal"})

    kept = fetch()

    assert kept.observations == first.observations
    assert kept.notes[-1].startswith("FRED unavailable")


def test_a_kept_response_expires(server, clock):
    fetch()
    clock.advance(fred.STALE_MAX_SECONDS + 1)
    server.handler = lambda r: httpx.Response(500)
    with pytest.raises(fred.FredError):
        fetch()


# ---- API -------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_list_without_a_key_is_unavailable_and_sends_nothing(client, server, monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", None)

    body = client.get("/api/macro/series").json()

    assert body["configured"] is False
    assert body["notice"].startswith("This product uses the FRED® API")
    assert body["count"] == len(fred.SERIES)
    assert {s["status"] for s in body["series"]} == {"unavailable"}
    assert all(s["latest"] is None for s in body["series"])
    assert server.requests == []


def test_list_with_a_key_reports_latest_values_and_sources(client, server):
    body = client.get("/api/macro/series").json()

    assert body["configured"] is True
    unrate = next(s for s in body["series"] if s["id"] == "UNRATE")
    assert unrate["status"] == "historical"
    assert unrate["label"] == "Unemployment rate"
    assert unrate["latest"] == {"date": "2026-09-01", "value": 4.3}
    assert unrate["previous"] == {"date": "2026-07-01", "value": 4.1}  # the missing August is skipped
    assert unrate["change"] == pytest.approx(0.2)
    assert unrate["missing"] == 1
    assert unrate["units_short"] == "%"
    assert unrate["last_updated"].startswith("2026-10-03T07:48:02")
    assert unrate["meta"]["provider"] == "fred"
    assert unrate["meta"]["endpoint"] == "fred.example"
    assert unrate["meta"]["source_timestamp"].startswith("2026-09-01")


def test_one_failing_series_does_not_hide_the_others(client, server):
    def handler(request):
        if request.url.params["series_id"] == "GDPC1":
            return httpx.Response(500)
        if request.url.path.endswith("/observations"):
            return httpx.Response(200, json=obs_body(GOOD_OBS))
        return httpx.Response(200, json=info_body(request.url.params["series_id"]))

    server.handler = handler
    series = {s["id"]: s for s in client.get("/api/macro/series").json()["series"]}

    assert series["GDPC1"]["status"] == "unavailable"
    assert "500" in series["GDPC1"]["error"]
    assert series["UNRATE"]["status"] == "historical"


def test_detail_returns_observations_with_gaps(client, server):
    body = client.get("/api/macro/series/UNRATE").json()

    assert [o["value"] for o in body["observations"]] == [4.1, None, 4.3]
    assert body["notes"] == "Public data."


def test_detail_errors(client, server, monkeypatch):
    assert client.get("/api/macro/series/NOPE").status_code == 404

    server.handler = lambda r: httpx.Response(429)
    limited = client.get("/api/macro/series/UNRATE")
    assert limited.status_code == 503
    assert limited.headers["Retry-After"] == str(fred.RATE_LIMIT_BACKOFF_SECONDS)

    monkeypatch.setattr(config, "FRED_API_KEY", None)
    missing = client.get("/api/macro/series/UNRATE")
    assert missing.status_code == 503
    assert "FRED_API_KEY" in missing.json()["detail"]


def test_error_responses_never_contain_the_key(client, server):
    server.handler = lambda r: httpx.Response(400, json={"error_code": 400, "error_message": f"bad key {FAKE_KEY}"})

    detail = client.get("/api/macro/series/UNRATE")
    listing = client.get("/api/macro/series")

    assert FAKE_KEY not in detail.text
    assert FAKE_KEY not in listing.text
