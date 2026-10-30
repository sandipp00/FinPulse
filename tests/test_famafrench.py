"""Fama-French factors: parsing the library's CSV, the regression, and the route. No network."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import config, famafrench, main
from src.analytics import factor_model

THREE = """This file was created by using the 202609 CRSP database.
The Tbill return is the simple daily rate.

,Mkt-RF,SMB,HML,RF
20260928,    0.50,   -0.10,    0.20,    0.01
20260929,   -0.26,    0.32,  -99.99,    0.01
20260930,    1.00,    0.00,   -0.88,    0.01

 Annual Factors: January-December
,Mkt-RF,SMB,HML,RF
  2025,   10.00,    1.00,    2.00,    4.00

Copyright 2026 Eugene F. Fama and Kenneth R. French
"""


def test_the_daily_table_is_read_and_stops_before_the_annual_one():
    frame = famafrench.parse_daily_csv(THREE)
    assert list(frame.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert [d.date().isoformat() for d in frame.index] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert frame.loc["2026-09-30", "HML"] == -0.88
    assert np.isnan(frame.loc["2026-09-29", "HML"])  # -99.99 means missing


def test_a_file_without_a_table_is_an_error():
    with pytest.raises(famafrench.FactorError):
        famafrench.parse_daily_csv("just a note\nand nothing else")


def synthetic(days=600, seed=3):
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2023-01-02", periods=days)
    f = pd.DataFrame(rng.normal(0, 1, (days, 4)), index=index, columns=list(factor_model.FACTORS))
    f["RF"] = 0.01
    noise = rng.normal(0, 0.3, days)
    returns = 0.02 + f["RF"] + 1.3 * f["Mkt-RF"] + 0.5 * f["SMB"] - 0.7 * f["HML"] + 0.2 * f["Mom"] + noise
    return returns, f


def test_the_regression_recovers_known_exposures():
    returns, f = synthetic()
    fit = factor_model.regress(returns, f)
    betas = {k: v["value"] for k, v in fit["betas"].items()}
    assert betas == pytest.approx({"Mkt-RF": 1.3, "SMB": 0.5, "HML": -0.7, "Mom": 0.2}, abs=0.05)
    assert fit["alpha_annual_pct"] == pytest.approx(((1.0002) ** 252 - 1) * 100, abs=2.5)
    assert fit["r_squared"] > 0.9 and fit["observations"] == 600
    assert abs(fit["betas"]["Mkt-RF"]["t_stat"]) > 20


def test_too_little_overlap_gives_no_fit():
    returns, f = synthetic(days=50)
    assert factor_model.regress(returns, f) is None


@pytest.fixture
def api(monkeypatch):
    famafrench.clear_cache()
    monkeypatch.setattr(famafrench, "_lock", None)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    returns, f = synthetic(days=900)
    state = {"downloads": 0, "fail": None}

    async def fake_download(name):
        state["downloads"] += 1
        if state["fail"]:
            raise famafrench.FactorError(state["fail"])
        return f[["Mkt-RF", "SMB", "HML", "RF"]] if "Research" in name else f[["Mom"]]

    async def fake_returns(symbol):
        return returns

    monkeypatch.setattr(famafrench, "_download", fake_download)
    monkeypatch.setattr(famafrench, "asset_returns", fake_returns)
    with TestClient(main.app) as client:
        yield client, state
    famafrench.clear_cache()


def test_the_route_fits_the_last_three_years_and_caches_the_factors(api):
    client, state = api
    body = client.get("/api/factors?symbol=NVDA").json()
    assert body["observations"] == famafrench.WINDOW_DAYS
    assert body["betas"]["Mkt-RF"]["value"] == pytest.approx(1.3, abs=0.05)
    assert body["factors_through"] == body["end_date"] and body["stale"] is None
    assert "Kenneth R. French" in body["notes"][0]
    client.get("/api/factors?symbol=^GSPC")
    assert state["downloads"] == 2  # both files once, then cached


def test_unknown_symbols_failures_and_the_off_switch(api, monkeypatch):
    client, state = api
    assert client.get("/api/factors?symbol=BTC/USDT").status_code == 404
    state["fail"] = "The Kenneth French Data Library answered 503"
    response = client.get("/api/factors?symbol=NVDA")
    assert response.status_code == 502 and "503" in response.json()["detail"]
    monkeypatch.setattr(config, "FAMA_FRENCH_ENABLED", False)
    assert client.get("/api/factors?symbol=NVDA").status_code == 503
