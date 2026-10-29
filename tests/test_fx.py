"""FX: ECB reference rates via Frankfurter, derived cross rates, failures and caching.

The source is mocked (httpx.MockTransport); the shapes match real Frankfurter v2
responses (a list of {date, base, quote, rate}; errors as {status, message}).
"""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import config, fx, main


def rows(day, usd=1.1, gbp=0.85, jpy=165.0, inr=95.0):
    return [
        {"date": day, "base": "EUR", "quote": "USD", "rate": usd},
        {"date": day, "base": "EUR", "quote": "GBP", "rate": gbp},
        {"date": day, "base": "EUR", "quote": "JPY", "rate": jpy},
        {"date": day, "base": "EUR", "quote": "INR", "rate": inr},
    ]


GOOD = rows("2026-10-28", usd=1.1133, inr=105.9) + rows("2026-10-29", usd=1.113, inr=106.0)


class Clock:
    def __init__(self):
        self.mono = 100.0
        self.wall = 1_793_232_000.0  # 2026-10-29

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(fx, "_monotonic", lambda: clock.mono)
    monkeypatch.setattr(fx, "_wall", lambda: clock.wall)
    return clock


@pytest.fixture(autouse=True)
def source(monkeypatch, clock):
    monkeypatch.setattr(config, "FX_BASE_URL", "https://fx.example/v2")
    fx.clear_cache()

    class Source:
        requests = []
        handler = staticmethod(lambda request: httpx.Response(200, json=GOOD))

    def handle(request):
        Source.requests.append(request)
        return Source.handler(request)

    monkeypatch.setattr(fx, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    yield Source
    fx.clear_cache()


def load():
    return asyncio.run(fx.euro_rates())


# ---- parsing -----------------------------------------------------------------

def test_rates_are_grouped_by_date_oldest_first():
    by_date = fx.parse_rates(list(reversed(GOOD)))

    assert list(by_date) == ["2026-10-28", "2026-10-29"]
    assert by_date["2026-10-29"] == {"USD": 1.113, "GBP": 0.85, "JPY": 165.0, "INR": 106.0}


@pytest.mark.parametrize("body, reason", [
    ({"status": 200}, "not send a list"),
    (["x"], "not an object"),
    ([{"date": "2026-10-29", "base": "USD", "quote": "INR", "rate": 95}], "not quoted against EUR"),
    ([{"date": "2026-10-29", "base": "EUR", "quote": "CHF", "rate": 0.9}], "unexpected currency"),
    ([{"date": "29/10/2026", "base": "EUR", "quote": "USD", "rate": 1.1}], "invalid date"),
    ([{"date": "2026-10-29", "base": "EUR", "quote": "USD", "rate": "1.1"}], "invalid rate"),
    ([{"date": "2026-10-29", "base": "EUR", "quote": "USD", "rate": 0}], "invalid rate"),
    ([{"date": "2026-10-29", "base": "EUR", "quote": "USD", "rate": -1}], "invalid rate"),
    ([{"date": "2026-10-29", "base": "EUR", "quote": "USD", "rate": True}], "invalid rate"),
    ([{"date": "2026-10-29", "base": "EUR", "quote": "USD", "rate": float("nan")}], "invalid rate"),
    (rows("2026-10-29")[:1] * 2, "repeat USD"),
])
def test_malformed_responses_are_rejected(body, reason):
    with pytest.raises(fx.FxError, match=reason):
        fx.parse_rates(body)


# ---- cross rates -----------------------------------------------------------------

def test_direct_pairs_are_the_published_rate_and_crosses_are_derived():
    rates = fx.EuroRates(fx.parse_rates(GOOD), 0, 0)

    assert fx.pair_series(rates, "EUR/USD")[-1] == {"date": "2026-10-29", "rate": 1.113}
    usd_inr = fx.pair_series(rates, "USD/INR")[-1]
    assert usd_inr["rate"] == pytest.approx(106.0 / 1.113)
    assert fx.pair_series(rates, "GBP/USD")[-1]["rate"] == pytest.approx(1.113 / 0.85)
    assert fx.pair_series(rates, "USD/JPY")[-1]["rate"] == pytest.approx(165.0 / 1.113)

    assert not fx.is_derived("EUR/INR")
    assert fx.is_derived("USD/INR")


def test_a_day_missing_one_side_of_a_cross_is_skipped_not_filled():
    partial = rows("2026-10-28") + [{"date": "2026-10-29", "base": "EUR", "quote": "INR", "rate": 106.0}]
    rates = fx.EuroRates(fx.parse_rates(partial), 0, 0)

    assert [p["date"] for p in fx.pair_series(rates, "USD/INR")] == ["2026-10-28"]
    assert [p["date"] for p in fx.pair_series(rates, "EUR/INR")] == ["2026-10-28", "2026-10-29"]


# ---- requests and failures ---------------------------------------------------------

def test_one_request_asks_the_ecb_feed_for_ten_years(source):
    load()

    (request,) = source.requests
    assert request.url.path == "/v2/rates"
    assert request.url.params["providers"] == "ecb"
    assert request.url.params["base"] == "EUR"
    assert request.url.params["quotes"] == "USD,GBP,JPY,INR"
    assert request.url.params["from"] == "2016-10-31"


def test_source_errors_pass_on_its_message(source):
    source.handler = lambda r: httpx.Response(422, json={"status": 422, "message": "invalid currency: ABC"})
    with pytest.raises(fx.FxError, match="422: invalid currency: ABC"):
        load()


@pytest.mark.parametrize("error, reason", [
    (httpx.ReadTimeout, "did not answer in time"),
    (httpx.ConnectError, "Could not reach the FX source \\(ConnectError\\)"),
])
def test_network_failures(source, error, reason):
    def fail(request):
        raise error("boom", request=request)

    source.handler = fail
    with pytest.raises(fx.FxError, match=reason):
        load()


def test_a_non_json_body_is_an_error(source):
    source.handler = lambda r: httpx.Response(502, text="<html>bad gateway</html>")
    with pytest.raises(fx.FxError, match="502 without JSON"):
        load()


def test_rate_limits_honour_retry_after_and_stop_asking(source, clock):
    source.handler = lambda r: httpx.Response(429, headers={"Retry-After": "40"}, json={"status": 429, "message": "slow down"})
    with pytest.raises(fx.FxError) as raised:
        load()
    assert raised.value.retry_after == 40

    source.requests.clear()
    clock.advance(10)
    with pytest.raises(fx.FxError, match="retry in 30s"):
        load()
    assert source.requests == []


# ---- caching -------------------------------------------------------------------------

def test_rates_are_cached_for_an_hour(source, clock):
    load()
    clock.advance(fx.CACHE_SECONDS - 1)
    load()
    assert len(source.requests) == 1


def test_a_failing_source_serves_the_last_rates_labelled(source, clock):
    load()
    clock.advance(fx.CACHE_SECONDS + 1)
    source.handler = lambda r: httpx.Response(500, json={"status": 500, "message": "down"})

    kept = load()

    assert "2026-10-29" in kept.by_date
    assert kept.notes[0].startswith("FX source unavailable")


def test_kept_rates_expire(source, clock):
    load()
    clock.advance(fx.STALE_MAX_SECONDS + 1)
    source.handler = lambda r: httpx.Response(500, json={"status": 500, "message": "down"})
    with pytest.raises(fx.FxError):
        load()


# ---- API ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_pairs_endpoint(client):
    body = client.get("/api/fx/pairs").json()

    assert body["notice"].startswith("Euro foreign exchange reference rates from the European Central Bank")
    assert body["count"] == len(fx.PAIRS)
    pairs = {p["pair"]: p for p in body["pairs"]}

    eur_usd = pairs["EUR/USD"]
    assert eur_usd["derived"] is False
    assert eur_usd["latest"] == {"date": "2026-10-29", "rate": 1.113}
    assert eur_usd["previous"] == {"date": "2026-10-28", "rate": 1.1133}
    assert eur_usd["change_pct"] == pytest.approx((1.113 / 1.1133 - 1) * 100, abs=1e-6)  # rounded to 6 dp
    assert eur_usd["status"] == "historical"
    assert eur_usd["meta"]["provider"] == "ecb"
    assert eur_usd["meta"]["endpoint"] == "fx.example"
    assert eur_usd["meta"]["source_timestamp"].startswith("2026-10-29")

    usd_inr = pairs["USD/INR"]
    assert usd_inr["derived"] is True
    assert "Not published by the ECB" in usd_inr["method"]
    assert usd_inr["latest"]["rate"] == pytest.approx(106.0 / 1.113)


def test_pairs_endpoint_reports_every_pair_unavailable_when_the_source_fails(client, source):
    source.handler = lambda r: httpx.Response(500, json={"status": 500, "message": "down"})

    body = client.get("/api/fx/pairs").json()

    assert {p["status"] for p in body["pairs"]} == {"unavailable"}
    assert all(p["latest"] is None for p in body["pairs"])
    assert "500: down" in body["pairs"][0]["error"]


def test_history_endpoint(client):
    body = client.get("/api/fx/history", params={"pair": "USD/INR"}).json()

    assert [o["date"] for o in body["observations"]] == ["2026-10-28", "2026-10-29"]
    assert body["derived"] is True


def test_history_errors(client, source):
    assert client.get("/api/fx/history", params={"pair": "AUD/USD"}).status_code == 404
    assert client.get("/api/fx/history", params={"pair": "x"}).status_code == 422

    source.handler = lambda r: httpx.Response(429, headers={"Retry-After": "15"})
    limited = client.get("/api/fx/history", params={"pair": "EUR/USD"})
    assert limited.status_code == 503
    assert limited.headers["Retry-After"] == "15"
