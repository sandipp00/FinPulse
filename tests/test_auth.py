import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from backend import auth, config, db, main

EMAIL = "Alice@Example.com"
PASSWORD = "correct horse battery"


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "ALLOW_REGISTRATION", True)
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "TRUST_PROXY", False)
    with TestClient(main.app) as test_client:
        yield test_client


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---- password hashing ---------------------------------------------------------

def test_hashes_are_salted_and_verify_only_the_right_password():
    first, second = auth.hash_password("hunter2hunter2"), auth.hash_password("hunter2hunter2")

    assert first != second                               # per-user random salt
    assert first.startswith("scrypt$") and "hunter2" not in first
    assert auth.verify_password("hunter2hunter2", first)
    assert not auth.verify_password("hunter2hunter3", first)


@pytest.mark.parametrize("stored", ["", "garbage", "bcrypt$1$2$3$a$b", "scrypt$x$y$z$a$b"])
def test_malformed_hashes_never_verify_or_crash(stored):
    assert auth.verify_password("anything", stored) is False


# ---- registration ---------------------------------------------------------------

def test_register_signs_you_in_and_normalizes_the_email(client):
    response = register(client)

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "alice@example.com"
    assert client.get("/api/auth/me").json()["user"]["email"] == "alice@example.com"


def test_session_cookie_is_httponly_samesite_and_never_holds_the_user(client):
    cookie = register(client).headers["set-cookie"].lower()

    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "secure" not in cookie                       # off for local http
    assert "alice" not in cookie                        # opaque random token only


def test_secure_flag_is_added_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)

    assert "secure" in register(client).headers["set-cookie"].lower().split("; ")


def test_register_validation(client):
    assert register(client, email="not-an-email").status_code == 422
    assert register(client, email="a@b").status_code == 422
    assert register(client, password="short").status_code == 422
    assert register(client, password="x" * 129).status_code == 422
    assert register(client, email="e" * 250 + "@example.com").status_code == 422


def test_duplicate_email_is_rejected_case_insensitively(client):
    assert register(client).status_code == 201

    assert register(client, email="ALICE@example.COM").status_code == 409


def test_registration_can_be_closed(client, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_REGISTRATION", False)

    assert register(client).status_code == 403
    assert client.get("/api/auth/me").json()["registration_open"] is False


def test_password_is_stored_hashed_and_sessions_store_only_a_token_hash(client):
    register(client)
    token = client.cookies.get(auth.SESSION_COOKIE)

    conn = sqlite3.connect(config.DATABASE_PATH)
    stored_hash = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    stored_tokens = [row[0] for row in conn.execute("SELECT token_hash FROM sessions")]
    conn.close()

    assert PASSWORD not in stored_hash
    assert token not in stored_tokens                   # a DB leak cannot be replayed as a login
    assert auth._token_hash(token) in stored_tokens


# ---- login / logout ---------------------------------------------------------------

def test_login_with_the_right_password_works_from_a_new_client(client):
    register(client)

    with TestClient(main.app) as fresh:
        assert fresh.get("/api/auth/me").json()["user"] is None
        response = login(fresh, email="alice@EXAMPLE.com")
        assert response.status_code == 200
        assert fresh.get("/api/auth/me").json()["user"]["email"] == "alice@example.com"


def test_wrong_password_and_unknown_email_look_identical(client):
    register(client)

    wrong = login(client, password="not the password")
    unknown = login(client, email="nobody@example.com")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Incorrect email or password."}


def test_logout_destroys_the_session_server_side(client):
    register(client)
    stolen = client.cookies.get(auth.SESSION_COOKIE)

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").json()["user"] is None

    # Replaying the old cookie must not work: the session row is gone.
    with TestClient(main.app, cookies={auth.SESSION_COOKIE: stolen}) as thief:
        assert thief.get("/api/auth/me").json()["user"] is None


def test_expired_sessions_are_rejected(client):
    register(client)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute("UPDATE sessions SET expires_at = ?", (int(time.time()) - 1,))
    conn.commit()
    conn.close()

    assert client.get("/api/auth/me").json()["user"] is None


def test_a_forged_cookie_is_not_a_session(client):
    with TestClient(main.app, cookies={auth.SESSION_COOKIE: "a" * 43}) as forger:
        assert forger.get("/api/auth/me").json()["user"] is None
        assert forger.get("/api/paper/portfolio").status_code == 401


# ---- abuse protection ------------------------------------------------------------

def test_repeated_failed_logins_lock_that_email_out_even_with_the_right_password(client):
    register(client)

    codes = [login(client, password="wrong password").status_code for _ in range(5)]
    blocked = login(client)                             # correct password, but locked out

    assert codes == [401] * 5
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert login(client, email="someone.else@example.com").status_code == 401  # others unaffected


def test_a_successful_login_resets_the_failure_count(client):
    register(client)

    for _ in range(4):
        login(client, password="wrong password")
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, password="wrong password").status_code == 401  # budget is fresh


def test_registration_is_rate_limited_per_ip(client):
    codes = [register(client, email=f"user{i}@example.com").status_code for i in range(12)]

    assert codes[:10] == [201] * 10
    assert codes[10:] == [429, 429]


def test_oversized_password_cannot_be_used_to_burn_cpu(client):
    register(client)

    assert login(client, password="x" * 100_000).status_code == 401


def test_forwarded_ip_is_only_trusted_behind_a_proxy(client, monkeypatch):
    register(client)
    headers = {"x-forwarded-for": "203.0.113.9"}

    for _ in range(30):                                 # exhaust the per-IP budget as one IP
        auth.login_by_ip.record("203.0.113.9")
    # Not trusted: the spoofed header is ignored, so this client is not blocked.
    assert client.post("/api/auth/login", headers=headers,
                       json={"email": EMAIL, "password": PASSWORD}).status_code == 200

    monkeypatch.setattr(config, "TRUST_PROXY", True)
    blocked = client.post("/api/auth/login", headers=headers,
                          json={"email": EMAIL, "password": PASSWORD})
    assert blocked.status_code == 429


# ---- cross-site request protection ------------------------------------------------

def test_posts_from_another_origin_are_blocked(client):
    evil = {"origin": "https://evil.example"}

    assert client.post("/api/auth/logout", headers=evil).status_code == 403
    assert register(client).status_code == 201
    assert client.post("/api/paper/reset", json={}, headers=evil).status_code == 403


def test_configured_and_same_host_origins_are_allowed(client):
    allowed = {"origin": config.CORS_ORIGINS[0]}
    same_host = {"origin": "http://testserver"}            # TestClient's Host header

    assert client.post("/api/auth/logout", headers=allowed).status_code == 200
    assert client.post("/api/auth/logout", headers=same_host).status_code == 200


def test_get_requests_are_never_origin_blocked(client):
    assert client.get("/api/auth/me", headers={"origin": "https://evil.example"}).status_code == 200


# ---- startup ----------------------------------------------------------------------

def test_init_db_is_idempotent_and_creates_empty_market_data(tmp_path, monkeypatch):
    path = tmp_path / "fresh.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)

    db.init_db()
    db.init_db()

    conn = sqlite3.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert {"users", "sessions", "market_prices"} <= tables
    assert mode == "wal"
