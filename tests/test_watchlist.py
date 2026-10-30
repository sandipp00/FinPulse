"""Each user's own watchlist: default until saved, validated, private, and gone with the account."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import config, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_SYMBOLS", ["BTC/USDT", "ETH/USDT"])
    monkeypatch.setattr(config, "YAHOO_LIVE_SYMBOLS", ["NVDA", "AAPL", "^N225", "EUR/USD"])
    with TestClient(main.app) as test_client:
        yield test_client


def signup(client, email):
    response = client.post("/api/auth/register", json={"email": email, "password": "a long password"})
    assert response.status_code == 201


def test_guests_are_asked_to_sign_in(client):
    assert client.get("/api/watchlist").status_code == 401
    response = client.put("/api/watchlist", json={"symbols": ["NVDA"]})
    assert response.status_code == 401 and "sign in" in response.json()["detail"]


def test_a_new_user_has_the_default_until_they_save_their_own(client):
    signup(client, "a@example.com")
    assert client.get("/api/watchlist").json() == {"symbols": [], "has_custom": False, "max_items": 60}

    saved = client.put("/api/watchlist", json={"symbols": ["NVDA", "BTC/USDT", "^N225"]}).json()
    assert saved["symbols"] == ["NVDA", "BTC/USDT", "^N225"] and saved["has_custom"] is True
    assert client.get("/api/watchlist").json()["symbols"] == ["NVDA", "BTC/USDT", "^N225"]  # order kept

    client.put("/api/watchlist", json={"symbols": ["EUR/USD", "NVDA"]})
    assert client.get("/api/watchlist").json()["symbols"] == ["EUR/USD", "NVDA"]  # replaced, not merged

    client.put("/api/watchlist", json={"symbols": []})
    assert client.get("/api/watchlist").json()["has_custom"] is False  # back to the default


@pytest.mark.parametrize("symbols, message", [
    (["NVDA", "NVDA"], "once"),
    (["NVDA", "TSM"], "Unknown instrument(s): TSM"),
])
def test_bad_lists_are_refused_and_nothing_is_saved(client, symbols, message):
    signup(client, "a@example.com")
    client.put("/api/watchlist", json={"symbols": ["AAPL"]})
    response = client.put("/api/watchlist", json={"symbols": symbols})
    assert response.status_code == 422 and message in response.json()["detail"]
    assert client.get("/api/watchlist").json()["symbols"] == ["AAPL"]


def test_too_many_symbols_are_refused(client):
    signup(client, "a@example.com")
    assert client.put("/api/watchlist", json={"symbols": ["NVDA"] * 61}).status_code == 422


def test_each_user_sees_only_their_own_and_it_goes_with_the_account(client, tmp_path):
    signup(client, "a@example.com")
    client.put("/api/watchlist", json={"symbols": ["NVDA"]})
    client.post("/api/auth/logout")
    signup(client, "b@example.com")
    assert client.get("/api/watchlist").json()["symbols"] == []

    conn = sqlite3.connect(tmp_path / "finpulse.db")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM users WHERE email = 'a@example.com'")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM watchlist_items").fetchone()[0] == 0
    conn.close()


def test_a_write_from_another_site_is_refused(client):
    signup(client, "a@example.com")
    response = client.put("/api/watchlist", json={"symbols": ["NVDA"]}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
