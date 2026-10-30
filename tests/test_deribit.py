"""Deribit crypto derivatives: parsing, the four summaries, caching and failures. No network."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import config, deribit, main

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
NOW_MS = NOW.timestamp() * 1000
DAY = deribit.DAY_MS


def test_instrument_names_give_the_0800_utc_expiry_strike_and_kind():
    future = deribit.parse_name("BTC-27NOV26")
    assert future["expiry_ms"] == datetime(2026, 11, 27, 8, tzinfo=timezone.utc).timestamp() * 1000
    assert future["strike"] is None and future["kind"] is None
    option = deribit.parse_name("ETH-1NOV26-2250-P")
    assert option["strike"] == 2250.0 and option["kind"] == "put"
    for bad in ("BTC-PERPETUAL", "BTC-31FOO26", "BTC-31FEB26", "", None):
        assert deribit.parse_name(bad) is None


def test_dvol_reports_the_latest_value_its_year_and_where_it_sits():
    rows = [[NOW_MS - (4 - i) * DAY, 0, 0, 0, close] for i, close in enumerate([50, 30, 60, 40])]
    rows.append([NOW_MS, 0, 0, 0, None])  # a bad row is skipped
    dvol = deribit.dvol_summary(rows)
    assert dvol["value"] == 40 and dvol["change_1d"] == -20
    assert (dvol["low_1y"], dvol["high_1y"]) == (30, 60)
    assert dvol["percentile_1y"] == 50  # at or above 2 of the 4 closes
    assert [p["value"] for p in dvol["history"]] == [50, 30, 60, 40]
    with pytest.raises(deribit.DeribitError):
        deribit.dvol_summary([])


def test_funding_is_annualized_now_and_averaged_per_day():
    ticker = {"mark_price": 101.0, "index_price": 100.0, "funding_8h": 0.0001, "open_interest": 5e8}
    day1, day2 = NOW_MS - DAY, NOW_MS
    history = [{"timestamp": day1, "interest_1h": 0.00001}, {"timestamp": day1 + 3_600_000, "interest_1h": 0.00003},
               {"timestamp": day2, "interest_1h": -0.00001}, {"timestamp": day2, "interest_1h": None}]
    funding = deribit.funding_summary(ticker, history)
    assert funding["premium_pct"] == 1.0
    assert funding["funding_8h_pct"] == 0.01
    assert funding["funding_annualized_pct"] == pytest.approx(10.95)  # 0.01% x 3 x 365
    assert funding["open_interest_usd"] == 5e8
    assert funding["history"] == [{"time": "2026-10-29", "value": pytest.approx(17.52)},  # mean 2e-5 x 24 x 365
                                  {"time": "2026-10-30", "value": pytest.approx(-8.76)}]
    with pytest.raises(deribit.DeribitError):
        deribit.funding_summary({"mark_price": 1.0}, [])


def test_the_futures_curve_skips_the_perpetual_and_annualizes_only_far_enough_out():
    rows = [
        {"instrument_name": "BTC-PERPETUAL", "mark_price": 100.5},
        {"instrument_name": "BTC-29JAN27", "mark_price": 102.0, "open_interest": 7.0},
        {"instrument_name": "BTC-31OCT26", "mark_price": 100.1},   # under a day out: not annualized
        {"instrument_name": "BTC-29OCT26", "mark_price": 100.0},   # already expired
        {"instrument_name": "BTC-27NOV26-80000-C", "mark_price": 0.01},  # an option
    ]
    curve = deribit.futures_curve(rows, index_price=100.0, now_ms=NOW_MS)
    assert [r["instrument"] for r in curve] == ["BTC-31OCT26", "BTC-29JAN27"]
    near, far = curve
    assert near["annualized_pct"] is None and near["basis_pct"] == pytest.approx(0.1)
    assert far["basis_pct"] == pytest.approx(2.0)
    assert far["annualized_pct"] == pytest.approx(2.0 * 365 / far["days"], abs=0.01)


def test_options_give_put_call_open_interest_and_the_at_the_money_iv_per_expiry():
    def option(name, oi, iv, underlying=100.0):
        return {"instrument_name": name, "open_interest": oi, "mark_iv": iv, "underlying_price": underlying}

    rows = [
        option("BTC-27NOV26-90-C", 10, 60), option("BTC-27NOV26-100-C", 20, 50), option("BTC-27NOV26-100-P", 10, 54),
        option("BTC-29JAN27-120-P", 15, 70, underlying=102.0), option("BTC-29JAN27-100-C", 5, 48, underlying=102.0),
        option("BTC-29OCT26-100-C", 1, 99),  # expired: counts nowhere in the term structure
        {"instrument_name": "BTC-27NOV26", "open_interest": 999},  # a future
    ]
    options = deribit.options_summary(rows, NOW_MS)
    assert options["call_open_interest"] == 36 and options["put_open_interest"] == 25
    assert options["put_call_ratio"] == pytest.approx(25 / 36, abs=0.001)
    term = options["term_structure"]
    assert [(t["expiry"], t["atm_strike"], t["atm_iv"]) for t in term] == [
        ("2026-11-27", 100.0, 52.0),  # mean of the call (50) and the put (54) at 100
        ("2027-01-29", 100.0, 48.0),  # 100 is nearer 102 than 120
    ]


def responses(dvol_close=40.0):
    return {
        "get_volatility_index_data": {"data": [[NOW_MS - DAY, 0, 0, 0, 42.0], [NOW_MS, 0, 0, 0, dvol_close]]},
        "ticker": {"mark_price": 100.2, "index_price": 100.0, "funding_8h": 0.00002, "open_interest": 1e8,
                   "timestamp": NOW_MS},
        "get_funding_rate_history": [{"timestamp": NOW_MS, "interest_1h": 0.000002}],
        "get_book_summary_by_currency:future": [{"instrument_name": "BTC-29JAN27", "mark_price": 101.0}],
        "get_book_summary_by_currency:option": [
            {"instrument_name": "BTC-29JAN27-100-C", "open_interest": 2, "mark_iv": 45, "underlying_price": 101.0},
            {"instrument_name": "BTC-29JAN27-100-P", "open_interest": 1, "mark_iv": 47, "underlying_price": 101.0},
        ],
    }


@pytest.fixture
def api(monkeypatch):
    deribit.clear_cache()
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(deribit, "_wall", lambda: NOW.timestamp())
    clock = {"now": 1000.0}
    monkeypatch.setattr(deribit, "_monotonic", lambda: clock["now"])
    state = {"calls": [], "data": responses(), "fail": None}

    async def fake_call(method, **params):
        state["calls"].append((method, params))
        if state["fail"]:
            raise deribit.DeribitError(state["fail"])
        key = f"{method}:{params['kind']}" if "kind" in params else method
        return state["data"][key]

    monkeypatch.setattr(deribit, "_call", fake_call)
    with TestClient(main.app) as client:
        yield client, state, clock
    deribit.clear_cache()


def test_the_route_returns_all_four_views_with_source_metadata(api):
    client, state, _ = api
    body = client.get("/api/crypto/derivatives?currency=BTC").json()

    assert body["currency"] == "BTC"
    assert body["dvol"]["value"] == 40.0 and body["dvol"]["change_1d"] == -2.0
    assert body["perpetual"]["instrument"] == "BTC-PERPETUAL" and body["perpetual"]["premium_pct"] == 0.2
    assert [f["instrument"] for f in body["futures"]] == ["BTC-29JAN27"]
    assert body["options"]["put_call_ratio"] == 0.5 and body["options"]["term_structure"][0]["atm_iv"] == 46.0
    assert body["meta"]["provider"] == "deribit" and body["meta"]["status"] == "real_time"
    assert len(state["calls"]) == 5
    assert {params.get("instrument_name") for _, params in state["calls"]} >= {"BTC-PERPETUAL"}


def test_one_fetch_per_minute_then_the_last_good_answer_while_deribit_is_down(api):
    client, state, clock = api
    client.get("/api/crypto/derivatives?currency=BTC")
    client.get("/api/crypto/derivatives?currency=BTC")
    assert len(state["calls"]) == 5  # the second came from the cache

    clock["now"] += deribit.CACHE_SECONDS + 1
    state["fail"] = "Deribit is rate-limiting requests"
    body = client.get("/api/crypto/derivatives?currency=BTC").json()
    assert body["meta"]["status"] == "cached" and "rate-limiting" in body["meta"]["notes"][0]

    clock["now"] += deribit.STALE_MAX_SECONDS
    response = client.get("/api/crypto/derivatives?currency=BTC")
    assert response.status_code == 502 and "rate-limiting" in response.json()["detail"]


def test_each_coin_is_cached_separately_and_other_coins_are_refused(api):
    client, state, _ = api
    client.get("/api/crypto/derivatives?currency=BTC")
    eth = client.get("/api/crypto/derivatives?currency=ETH").json()
    assert eth["perpetual"]["instrument"] == "ETH-PERPETUAL" and len(state["calls"]) == 10
    assert client.get("/api/crypto/derivatives?currency=SOL").status_code == 422


def test_it_can_be_turned_off(api, monkeypatch):
    client, state, _ = api
    monkeypatch.setattr(config, "DERIBIT_ENABLED", False)
    response = client.get("/api/crypto/derivatives")
    assert response.status_code == 503 and state["calls"] == []


@pytest.mark.parametrize("status, message", [(429, "rate-limiting"), (500, "answered 500")])
def test_http_errors_become_plain_messages(monkeypatch, status, message):
    import asyncio

    import httpx

    def handler(request):
        return httpx.Response(status, json={"error": "x"})

    monkeypatch.setattr(deribit, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(deribit.DeribitError, match=message):
        asyncio.run(deribit._call("ticker", instrument_name="BTC-PERPETUAL"))
    monkeypatch.setattr(deribit, "_client", None)
