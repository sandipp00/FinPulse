"""Earnings from Nasdaq: the three kinds of next-report sentence, past quarters, caching, failures. No network."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import config, earnings, main

EXPECTED = ("NVIDIA Corporation Common Stock is expected* to report earnings on  11/17/2026 after market close.  The "
            "report will be for the fiscal Quarter ending Oct 2026.  According to Zacks Investment Research, based on  13 "
            "analysts'  forecasts, the consensus EPS forecast for the quarter is $2.49.  The reported EPS for the same "
            "quarter last year was $1.24.")
ESTIMATED = ("Broadcom Inc. Common Stock is estimated to report earnings on 12/10/2026. The upcoming earnings date is derived "
             "from an algorithm based on a company's historical reporting dates. Our vendor, Zacks Investment Research, "
             "might revise this date in the future, once the company announces the actual earnings date.")
NONE = "Our vendor, Zacks Investment Research, hasn't provided us with the upcoming earnings report date."
SURPRISE = {"data": {"earningsSurpriseTable": {"rows": [
    {"fiscalQtrEnd": "Jul 2026", "dateReported": "8/26/2026", "eps": 2.22, "consensusForecast": "2.09", "percentageSurprise": "6.22"},
    {"fiscalQtrEnd": "Apr 2026", "dateReported": "5/20/2026", "eps": 1.87, "consensusForecast": "1.7", "percentageSurprise": "10"},
]}}}
NO_RECORD = {"data": None, "status": {"rCode": 200, "bCodeMessage": [{"code": 1002, "errorMessage": "No record found."}]}}


def test_an_expected_date_comes_with_timing_and_the_consensus():
    assert earnings.parse_next(EXPECTED) == {
        "date": "2026-11-17", "certainty": "expected", "timing": "after_close", "fiscal_quarter": "Oct 2026",
        "eps_forecast": 2.49, "analysts": 13, "eps_last_year": 1.24,
    }


def test_an_estimated_date_says_so_and_has_no_invented_figures():
    parsed = earnings.parse_next(ESTIMATED)
    assert parsed["date"] == "2026-12-10" and parsed["certainty"] == "estimated"
    assert parsed["timing"] is None and parsed["eps_forecast"] is None and parsed["analysts"] is None


def test_no_date_is_none():
    assert earnings.parse_next(NONE) is None
    assert earnings.parse_next("") is None
    assert earnings.parse_next("is expected* to report earnings on 13/45/2026") is None  # not a real date


def test_past_quarters_are_parsed_and_a_missing_table_is_empty():
    assert earnings.parse_history(SURPRISE) == [
        {"fiscal_quarter": "Jul 2026", "date": "2026-08-26", "eps": 2.22, "eps_forecast": 2.09, "surprise_pct": 6.22},
        {"fiscal_quarter": "Apr 2026", "date": "2026-05-20", "eps": 1.87, "eps_forecast": 1.7, "surprise_pct": 10.0},
    ]
    assert earnings.parse_history(NO_RECORD) == [] and earnings.parse_history(None) == []


def test_upcoming_is_soonest_first_before_the_open_first_and_skips_past_dates():
    def s(symbol, day, timing):
        return {"symbol": symbol, "name": symbol, "next": {"date": day, "timing": timing}}

    stocks = [s("AMD", "2026-11-03", "after_close"), s("WMT", "2026-11-03", "before_open"),
              s("OLD", "2026-10-01", None), {"symbol": "JPM", "name": "JPM", "next": None}]
    assert [r["symbol"] for r in earnings.upcoming(stocks, date(2026, 10, 31))] == ["WMT", "AMD"]


def test_brk_b_is_brk_dot_b_on_nasdaq():
    assert earnings.nasdaq_symbol("BRK-B") == "BRK.B" and earnings.nasdaq_symbol("NVDA") == "NVDA"


@pytest.fixture
def api(monkeypatch):
    earnings.clear_cache()
    monkeypatch.setattr(earnings, "_lock", None)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(earnings, "STOCK_SYMBOLS", ["NVDA", "AVGO", "JPM"])
    clock = {"now": 1000.0}
    monkeypatch.setattr(earnings, "_monotonic", lambda: clock["now"])
    state = {"calls": [], "down": set()}
    texts = {"NVDA": EXPECTED, "AVGO": ESTIMATED, "JPM": NONE}

    async def fake_get(path):
        state["calls"].append(path)
        code = path.split("/")[2]
        if code in state["down"]:
            raise earnings.EarningsError("Nasdaq answered 403")
        return {"data": {"reportText": texts[code]}} if "earnings-date" in path else SURPRISE

    monkeypatch.setattr(earnings, "_get", fake_get)
    with TestClient(main.app) as client:
        yield client, state, clock
    earnings.clear_cache()


def test_the_route_lists_upcoming_reports_and_every_stock(api, monkeypatch):
    client, state, _ = api
    body = client.get("/api/earnings").json()
    assert body["count"] == 3 and body["failed"] == []
    assert [r["symbol"] for r in body["upcoming"] if r["date"] >= "2026-11-01"] == ["NVDA", "AVGO"]
    jpm = next(s for s in body["stocks"] if s["symbol"] == "JPM")
    assert jpm["next"] is None and jpm["history"][0]["eps"] == 2.22
    assert len(state["calls"]) == 6  # two requests per stock
    assert any("Estimated" in note for note in body["notes"])


def test_each_stock_is_cached_and_its_last_answer_kept_while_nasdaq_fails(api):
    client, state, clock = api
    client.get("/api/earnings")
    client.get("/api/earnings?symbol=NVDA")
    assert len(state["calls"]) == 6  # served from the cache

    clock["now"] += earnings.CACHE_SECONDS + 1
    state["down"] = {"NVDA"}
    nvda = client.get("/api/earnings?symbol=NVDA").json()
    assert nvda["next"]["eps_forecast"] == 2.49 and "403" in nvda["stale"]

    clock["now"] += earnings.STALE_MAX_SECONDS
    body = client.get("/api/earnings").json()
    assert body["failed"] == ["NVDA"] and body["count"] == 2
    assert any("Could not load: NVDA" in note for note in body["notes"])
    assert client.get("/api/earnings?symbol=NVDA").status_code == 502


def test_unknown_symbols_and_the_off_switch(api, monkeypatch):
    client, state, _ = api
    assert client.get("/api/earnings?symbol=TSM").status_code == 404
    monkeypatch.setattr(config, "EARNINGS_ENABLED", False)
    assert client.get("/api/earnings").status_code == 503 and state["calls"] == []
