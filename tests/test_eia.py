"""EIA oil prices: parsing, paging, failures, caching, key secrecy and the routes.

EIA is mocked (httpx.MockTransport) and every test sets its own fake key, so the
suite never sends a real key anywhere, even when one is configured in .env.
"""
import asyncio
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import config, eia, main

FAKE_KEY = "FAKEeiaKEY0123456789abcdefghijklmnopqrst"


def row(series, period, value="75.10", **extra):
    return {"period": period, "series": series, "series-description": "x", "value": value, "units": "$/BBL", **extra}


def body(rows, total=None, **extra):
    return {"response": {"total": str(len(rows) if total is None else total), "dateFormat": "YYYY-MM-DD",
                         "frequency": "daily", "data": rows, **extra}, "apiVersion": "2.1.10"}


GOOD = [
    row("RWTC", "2026-10-26", "103.37"), row("RBRTE", "2026-10-26", "106.10"),
    row("RWTC", "2026-10-27", "105.25"), row("RBRTE", "2026-10-27", ""),
    row("RBRTE", "2026-10-28", "107.40"),
]


class Clock:
    def __init__(self):
        self.mono = 50.0
        self.wall = 1_793_232_000.0  # 2026-10-29

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(eia, "_monotonic", lambda: clock.mono)
    monkeypatch.setattr(eia, "_wall", lambda: clock.wall)
    return clock


@pytest.fixture(autouse=True)
def server(monkeypatch, clock):
    monkeypatch.setattr(config, "EIA_API_KEY", FAKE_KEY)
    monkeypatch.setattr(config, "EIA_BASE_URL", "https://eia.example/v2")
    eia.clear_cache()

    class Server:
        requests = []
        handler = staticmethod(lambda request: httpx.Response(200, json=body(GOOD)))

    def handle(request):
        Server.requests.append(request)
        return Server.handler(request)

    monkeypatch.setattr(eia, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    yield Server
    eia.clear_cache()


def load():
    return asyncio.run(eia.oil_prices())


# ---- parsing ---------------------------------------------------------------

def test_rows_are_grouped_per_series_with_missing_values_kept():
    series, units, missing = eia.group_rows(list(reversed(GOOD)))

    assert series["RWTC"] == [{"date": "2026-10-26", "value": 103.37}, {"date": "2026-10-27", "value": 105.25}]
    assert series["RBRTE"][1] == {"date": "2026-10-27", "value": None}
    assert missing == {"RWTC": 0, "RBRTE": 1}
    assert units == {"RWTC": "$/BBL", "RBRTE": "$/BBL"}


@pytest.mark.parametrize("value", ["", None, "NA", "abc", "NaN", "-5", "0", True])
def test_unusable_values_count_as_missing(value):
    series, _, missing = eia.group_rows([row("RWTC", "2026-10-27", value)])
    assert series["RWTC"][0]["value"] is None and missing["RWTC"] == 1


def test_the_documented_units_column_name_is_also_accepted():
    _, units, _ = eia.group_rows([{"period": "2026-10-27", "series": "RWTC", "value": "1", "value-units": "$/BBL"}])
    assert units["RWTC"] == "$/BBL"


@pytest.mark.parametrize("rows, reason", [
    (["x"], "not an object"),
    ([row("RXYZ", "2026-10-27")], "unexpected series"),
    ([row("RWTC", "27/10/2026")], "invalid period"),
    ([row("RWTC", "2026-10")], "invalid period"),
    ([row("RWTC", "2026-10-27"), row("RWTC", "2026-10-27")], "repeat RWTC"),
    ([{"period": "2026-10-27", "series": "RWTC", "price": "1"}], "no value column"),
])
def test_malformed_rows_are_rejected(rows, reason):
    with pytest.raises(eia.EiaError, match=reason):
        eia.group_rows(rows)


@pytest.mark.parametrize("payload, reason", [
    ([], "not a JSON object"),
    ({}, "no response object"),
    ({"response": {"total": "1"}}, "no data list"),
    ({"response": {"data": []}}, "no row total"),
])
def test_malformed_responses_are_rejected(payload, reason):
    with pytest.raises(eia.EiaError, match=reason):
        eia.parse_page(payload)


# ---- requests and paging -------------------------------------------------------

def test_the_request_asks_for_both_daily_series_for_ten_years(server):
    load()

    (request,) = server.requests
    assert request.url.path == "/v2/petroleum/pri/spt/data/"
    params = request.url.params
    assert params["frequency"] == "daily"
    assert params["data[0]"] == "value"
    assert params.get_list("facets[series][]") == ["RWTC", "RBRTE"]
    assert params["start"] == "2016-10-31"
    assert params["sort[0][direction]"] == "asc"
    assert params["length"] == "5000"
    assert params["api_key"] == FAKE_KEY


def test_results_beyond_one_page_are_fetched_with_offsets(server):
    pages = {"0": body(GOOD[:3], total=5), "3": body(GOOD[3:], total=5)}
    server.handler = lambda r: httpx.Response(200, json=pages[r.url.params["offset"]])

    prices = load()

    assert [r.url.params["offset"] for r in server.requests] == ["0", "3"]
    assert len(prices.series["RBRTE"]) == 3


def test_endless_paging_is_cut_off(server):
    server.handler = lambda r: httpx.Response(200, json=body(GOOD[:1], total=10**6))
    with pytest.raises(eia.EiaError, match="more rows"):
        load()
    assert len(server.requests) == eia.MAX_PAGES


def test_eia_warnings_are_kept_as_notes(server):
    server.handler = lambda r: httpx.Response(200, json=body(GOOD, warning="parameter out of range", description="length capped"))
    assert load().notes == ["EIA warning: parameter out of range length capped"]


def test_no_key_means_no_request(server, monkeypatch):
    monkeypatch.setattr(config, "EIA_API_KEY", None)
    with pytest.raises(eia.EiaNotConfigured):
        load()
    assert server.requests == []


# ---- failures and the key ---------------------------------------------------------

def test_eia_error_messages_are_passed_on_without_the_key(server):
    server.handler = lambda r: httpx.Response(403, json={"error": f"API_KEY_INVALID {FAKE_KEY}", "code": 403})
    with pytest.raises(eia.EiaError) as raised:
        load()
    assert "API_KEY_INVALID" in str(raised.value)
    assert FAKE_KEY not in str(raised.value)


def test_an_error_in_a_200_body_is_still_an_error(server):
    server.handler = lambda r: httpx.Response(200, json={"error": "Invalid frequency", "code": 400})
    with pytest.raises(eia.EiaError, match="Invalid frequency"):
        load()


def test_network_errors_never_include_the_url_or_key(server):
    def boom(request):
        raise httpx.ConnectError(f"failed {request.url}", request=request)

    server.handler = boom
    with pytest.raises(eia.EiaError) as raised:
        load()
    assert str(raised.value) == "Could not reach EIA (ConnectError)"


def test_the_key_is_not_logged(server, caplog):
    server.handler = lambda r: httpx.Response(500, json={"error": "boom", "code": 500})
    caplog.set_level(logging.DEBUG)
    with pytest.raises(eia.EiaError):
        load()
    assert FAKE_KEY not in caplog.text


def test_timeouts_and_non_json(server):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    server.handler = slow
    with pytest.raises(eia.EiaError, match="did not answer in time"):
        load()
    server.handler = lambda r: httpx.Response(503, text="<html>down</html>")
    with pytest.raises(eia.EiaError, match="503 without JSON"):
        load()


def test_rate_limiting_backs_off(server, clock):
    server.handler = lambda r: httpx.Response(429, json={"error": "too many", "code": 429})
    with pytest.raises(eia.EiaError) as raised:
        load()
    assert raised.value.retry_after == eia.RATE_LIMIT_BACKOFF_SECONDS
    server.requests.clear()
    clock.advance(20)
    with pytest.raises(eia.EiaError, match="retry in 40s"):
        load()
    assert server.requests == []


# ---- caching ----------------------------------------------------------------------

def test_cached_for_an_hour_then_kept_when_eia_fails(server, clock):
    load()
    clock.advance(eia.CACHE_SECONDS - 1)
    load()
    assert len(server.requests) == 1

    clock.advance(2)
    server.handler = lambda r: httpx.Response(500, json={"error": "down", "code": 500})
    kept = load()
    assert kept.series["RWTC"][-1]["value"] == 105.25
    assert kept.notes[0].startswith("EIA unavailable")

    clock.advance(eia.STALE_MAX_SECONDS)
    with pytest.raises(eia.EiaError):
        load()


# ---- API ------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_list_without_a_key(client, server, monkeypatch):
    monkeypatch.setattr(config, "EIA_API_KEY", None)
    body_ = client.get("/api/commodities").json()

    assert body_["configured"] is False
    assert body_["citation"].startswith("Source: U.S. Energy Information Administration (")
    assert "Gold and silver are not included" in body_["not_covered"]
    assert {c["status"] for c in body_["commodities"]} == {"unavailable"}
    assert server.requests == []


def test_list_with_a_key(client):
    items = {c["id"]: c for c in client.get("/api/commodities").json()["commodities"]}

    wti = items["RWTC"]
    assert wti["label"] == "WTI crude oil (Cushing, OK)"
    assert wti["latest"] == {"date": "2026-10-27", "value": 105.25}
    assert wti["previous"] == {"date": "2026-10-26", "value": 103.37}
    assert wti["change"] == pytest.approx(1.88)
    assert wti["change_pct"] == pytest.approx((105.25 / 103.37 - 1) * 100, abs=1e-6)
    assert wti["units"] == "$/BBL"
    assert wti["meta"]["provider"] == "eia"
    assert wti["meta"]["source_timestamp"].startswith("2026-10-27")

    brent = items["RBRTE"]
    assert brent["latest"]["date"] == "2026-10-28"
    assert brent["previous"]["date"] == "2026-10-26"  # the empty 27th is skipped
    assert brent["missing"] == 1


def test_list_when_eia_fails(client, server):
    server.handler = lambda r: httpx.Response(500, json={"error": "down", "code": 500})
    items = client.get("/api/commodities").json()["commodities"]
    assert {c["status"] for c in items} == {"unavailable"}
    assert "500: down" in items[0]["error"]


def test_history(client):
    body_ = client.get("/api/commodities/history", params={"series": "RBRTE"}).json()
    assert [o["value"] for o in body_["observations"]] == [106.10, None, 107.40]


def test_history_errors(client, server, monkeypatch):
    assert client.get("/api/commodities/history", params={"series": "GOLD"}).status_code == 404

    server.handler = lambda r: httpx.Response(429, json={"error": "too many", "code": 429})
    limited = client.get("/api/commodities/history", params={"series": "RWTC"})
    assert limited.status_code == 503
    assert limited.headers["Retry-After"] == str(eia.RATE_LIMIT_BACKOFF_SECONDS)

    monkeypatch.setattr(config, "EIA_API_KEY", None)
    assert "EIA_API_KEY" in client.get("/api/commodities/history", params={"series": "RWTC"}).json()["detail"]


def test_responses_never_contain_the_key(client, server):
    server.handler = lambda r: httpx.Response(403, json={"error": f"bad key {FAKE_KEY}", "code": 403})
    assert FAKE_KEY not in client.get("/api/commodities").text
    assert FAKE_KEY not in client.get("/api/commodities/history", params={"series": "RWTC"}).text
