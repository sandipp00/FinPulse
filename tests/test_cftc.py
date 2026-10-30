"""CFTC Commitments of Traders: net positions, percentiles, caching and failures. No network."""
import pytest
from fastapi.testclient import TestClient

from backend import cftc, config, main

GOLD = cftc.MARKETS[0]
BITCOIN = next(m for m in cftc.MARKETS if m[0] == "btc")


def disagg(day, long_, short, oi=1000):
    return {"report_date_as_yyyy_mm_dd": f"{day}T00:00:00.000", "cftc_contract_market_code": "088691",
            "m_money_positions_long_all": str(long_), "m_money_positions_short_all": str(short),
            "open_interest_all": str(oi), "contract_units": "(CONTRACTS OF 100 TROY OUNCES)"}


def financial(day, long_, short, am_long=50, am_short=10, oi=200):
    return {"report_date_as_yyyy_mm_dd": f"{day}T00:00:00.000", "cftc_contract_market_code": "133741",
            "lev_money_positions_long": str(long_), "lev_money_positions_short": str(short),
            "asset_mgr_positions_long": str(am_long), "asset_mgr_positions_short": str(am_short),
            "open_interest_all": str(oi), "contract_units": "(5 Bitcoins)"}


def test_net_is_long_minus_short_with_its_weekly_change_and_share_of_open_interest():
    rows = [disagg("2026-10-27", 600, 100), disagg("2026-10-13", 300, 200), disagg("2026-10-20", 500, 100)]
    gold = cftc.summarize(GOLD, rows)  # rows in any order
    assert gold["latest"] == {"date": "2026-10-27", "long": 600, "short": 100, "net": 500,
                              "net_pct_open_interest": 50.0, "change_1w": 100, "open_interest": 1000}
    assert gold["traders"] == "Managed money" and gold["asset"] == "gold"
    assert [h["value"] for h in gold["history"]] == [100, 400, 500]
    assert gold["percentile_3y"] == 100 and gold["range_3y"] == {"min": 100, "max": 500, "weeks": 3}


def test_financial_futures_use_leveraged_funds_and_add_asset_managers():
    btc = cftc.summarize(BITCOIN, [financial("2026-10-27", 20, 60)])
    assert btc["traders"] == "Leveraged funds"
    assert btc["latest"]["net"] == -40 and btc["latest"]["asset_managers_net"] == 40
    assert btc["latest"]["change_1w"] is None  # one week only


def test_bad_rows_are_skipped_and_no_rows_means_no_market():
    rows = [disagg("2026-10-27", 600, 100), {"report_date_as_yyyy_mm_dd": "2026-10-20T00:00:00.000",
                                             "m_money_positions_long_all": "n/a", "m_money_positions_short_all": "1"}]
    assert len(cftc.summarize(GOLD, rows)["history"]) == 1
    assert cftc.summarize(GOLD, []) is None


def test_percentile_is_the_share_at_or_below():
    assert cftc.percentile(5, [1, 2, 3, 4, 5]) == 100
    assert cftc.percentile(1, [1, 2, 3, 4, 5]) == 20
    assert cftc.percentile(0, []) is None


@pytest.fixture
def api(monkeypatch):
    cftc.clear_cache()
    monkeypatch.setattr(cftc, "_lock", None)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    clock = {"now": 1000.0}
    monkeypatch.setattr(cftc, "_monotonic", lambda: clock["now"])
    state = {"calls": [], "fail": None}

    async def fake_report(dataset, codes, since):
        state["calls"].append((dataset, tuple(codes)))
        if state["fail"]:
            raise cftc.CftcError(state["fail"])
        if dataset == cftc.DISAGGREGATED:
            return [disagg("2026-10-20", 500, 100), disagg("2026-10-27", 600, 100)]
        return [financial("2026-10-27", 20, 60)]

    monkeypatch.setattr(cftc, "_report", fake_report)
    with TestClient(main.app) as client:
        yield client, state, clock
    cftc.clear_cache()


def test_two_requests_cover_every_market_and_the_answer_is_cached(api):
    client, state, clock = api
    body = client.get("/api/cftc").json()
    assert {m["id"] for m in body["markets"]} == {"gold", "btc"}  # only markets the fakes returned
    assert body["as_of"] == "2026-10-27" and body["stale"] is None and "Commodity Futures" in body["notes"][0]
    assert len(state["calls"]) == 2
    assert set(state["calls"][0][1]) == {m[2] for m in cftc.MARKETS if m[3] == cftc.DISAGGREGATED}

    client.get("/api/cftc")
    assert len(state["calls"]) == 2  # cached


def test_the_last_answer_is_kept_while_the_cftc_fails_then_it_is_an_error(api, monkeypatch):
    client, state, clock = api
    client.get("/api/cftc")
    clock["now"] += cftc.CACHE_SECONDS + 1
    state["fail"] = "The CFTC is rate-limiting requests"
    body = client.get("/api/cftc").json()
    assert "rate-limiting" in body["stale"] and body["markets"]

    clock["now"] += cftc.STALE_MAX_SECONDS
    response = client.get("/api/cftc")
    assert response.status_code == 502 and "rate-limiting" in response.json()["detail"]

    monkeypatch.setattr(config, "CFTC_ENABLED", False)
    assert client.get("/api/cftc").status_code == 503
