import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import admin, config, main
from src.portfolio.paper import PaperBroker


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def signup(client, email, password="original password"):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()["user"]["id"]


def test_list_users(client):
    signup(client, "a@example.com")
    signup(client, "b@example.com")

    assert [u["email"] for u in admin.list_users()] == ["a@example.com", "b@example.com"]


def test_set_password_changes_it_and_signs_the_user_out_everywhere(client):
    signup(client, "a@example.com")
    assert client.get("/api/auth/me").json()["user"] is not None

    assert admin.set_password("A@Example.com", "a brand new password") is True

    assert client.get("/api/auth/me").json()["user"] is None            # old session revoked
    login = lambda pw: client.post(  # noqa: E731
        "/api/auth/login", json={"email": "a@example.com", "password": pw}
    ).status_code
    assert login("original password") == 401
    assert login("a brand new password") == 200


def test_set_password_validates_and_reports_unknown_users(client):
    signup(client, "a@example.com")

    with pytest.raises(ValueError):
        admin.set_password("a@example.com", "short")
    assert admin.set_password("nobody@example.com", "long enough password") is False


def test_delete_user_removes_the_account_and_all_of_its_paper_data(client, tmp_path):
    keep = signup(client, "keep@example.com")
    gone = signup(client, "gone@example.com")
    for user_id in (keep, gone):
        broker = PaperBroker(config.DATABASE_PATH, user_id, starting_cash=100_000)
        broker.place_order("BTC/USDT", "buy", 100, quantity=10)
        broker.record_equity(99_000)

    assert admin.delete_user("gone@example.com") is True

    conn = sqlite3.connect(config.DATABASE_PATH)
    count = lambda table, uid: conn.execute(  # noqa: E731
        f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (uid,)
    ).fetchone()[0]
    for table in ("paper_account", "paper_positions", "paper_orders", "paper_equity", "sessions"):
        assert count(table, gone) == 0, table
        assert count(table, keep) >= 1, table      # the other user is untouched
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    conn.close()

    assert admin.delete_user("gone@example.com") is False


def test_cli_list_and_missing_user_exit_codes(client, capsys):
    signup(client, "a@example.com")

    assert admin.main(["list-users"]) == 0
    assert "a@example.com" in capsys.readouterr().out
    assert admin.main(["delete-user", "nobody@example.com"]) == 1
    assert "No account" in capsys.readouterr().err
