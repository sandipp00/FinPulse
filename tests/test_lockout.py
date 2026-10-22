import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from backend import auth, config, main

OWNER = "owner@example.com"
PASSWORD = "correct horse battery"
OWNER_IP = "198.51.100.10"
ATTACKER_IP = "203.0.113.66"


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_BACKEND", "off")
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)
    monkeypatch.setattr(config, "TRUST_PROXY", True)        # so each request can claim an IP
    monkeypatch.setattr(auth, "SCRYPT_N", 2**4)              # cheap hashes keep many-attempt tests fast
    with TestClient(main.app) as test_client:
        yield test_client


def post(client, path, ip, **body):
    return client.post(f"/api/auth/{path}", json=body, headers={"x-forwarded-for": ip})


def login(client, ip, email=OWNER, password=PASSWORD):
    return post(client, "login", ip, email=email, password=password)


def signup_owner(client, ip=OWNER_IP):
    assert post(client, "register", ip, email=OWNER, password=PASSWORD).status_code == 201


def fail_many(client, count, ip, email=OWNER):
    return [login(client, ip, email, "wrong password").status_code for _ in range(count)]


# ---- the original complaint: a stranger must not be able to lock the owner out ---------

def test_a_strangers_failed_guesses_never_lock_the_owner_out(client):
    signup_owner(client)

    codes = fail_many(client, 8, ATTACKER_IP)

    assert codes == [401] * 5 + [429] * 3                    # the attacker's own slot fills up
    owner = login(client, OWNER_IP)                          # ...and the owner is not affected at all
    assert owner.status_code == 200
    assert login(client, "192.0.2.77").status_code == 200    # not even from a brand-new network


def test_the_attacker_is_still_stopped_from_guessing_at_their_slot(client):
    signup_owner(client)
    fail_many(client, 5, ATTACKER_IP)

    blocked = login(client, ATTACKER_IP)                     # even the right password is refused

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_one_ip_cannot_spray_guesses_across_many_emails(client):
    codes = [login(client, ATTACKER_IP, email=f"victim{i}@example.com", password="x" * 10).status_code
             for i in range(32)]

    assert codes[:30] == [401] * 30 and codes[30:] == [429, 429]


def test_a_successful_login_clears_only_that_networks_failures(client):
    signup_owner(client)
    fail_many(client, 4, OWNER_IP)

    assert login(client, OWNER_IP).status_code == 200
    assert fail_many(client, 4, OWNER_IP) == [401] * 4       # a fresh budget


# ---- guessing spread across many IPs: the ceiling that exempts the owner's networks ----

def spread_attack(client, ips=12):
    """12 IPs x 5 failures = 60 failures against one email: the global ceiling."""
    for i in range(ips):
        assert fail_many(client, 5, f"203.0.113.{100 + i}") == [401] * 5


def test_a_distributed_attack_trips_the_ceiling_for_networks_the_owner_has_never_used(client):
    signup_owner(client)
    spread_attack(client)

    stranger = login(client, "192.0.2.200")                  # unknown network, correct password
    assert stranger.status_code == 429


def test_the_owner_still_gets_in_from_a_network_they_have_used_before(client):
    signup_owner(client)
    spread_attack(client)

    assert login(client, OWNER_IP).status_code == 200        # the IP they registered from
    wrong = login(client, OWNER_IP, password="typo typo")
    assert wrong.status_code == 401                          # known IPs still get real answers (and count)


def test_a_network_becomes_known_after_a_successful_login(client):
    signup_owner(client)
    assert login(client, "192.0.2.50").status_code == 200    # the owner signs in from a second place
    spread_attack(client)

    assert login(client, "192.0.2.50").status_code == 200


def test_networks_not_seen_for_a_month_are_no_longer_trusted(client):
    signup_owner(client)
    spread_attack(client)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute("UPDATE login_ips SET last_seen = ?", (int(time.time()) - 31 * 86_400,))
    conn.commit()
    conn.close()

    assert login(client, OWNER_IP).status_code == 429


def test_unknown_emails_hit_the_same_wall_so_nothing_is_revealed(client):
    for i in range(12):
        fail_many(client, 5, f"203.0.113.{100 + i}", email="ghost@example.com")

    assert login(client, OWNER_IP, email="ghost@example.com").status_code == 429


# ---- remembered networks are stored safely --------------------------------------------

def test_addresses_are_stored_only_as_keyed_hashes(client):
    signup_owner(client)
    login(client, "192.0.2.50")

    conn = sqlite3.connect(config.DATABASE_PATH)
    rows = conn.execute("SELECT ip_hash FROM login_ips").fetchall()
    dump = "".join(str(r) for r in conn.iterdump())
    conn.close()

    assert len(rows) == 2 and all(len(r[0]) == 64 for r in rows)
    assert OWNER_IP not in dump and "192.0.2.50" not in dump
    # Unkeyed hashes of IPv4 addresses are trivially reversible; these must not be.
    import hashlib
    assert hashlib.sha256(OWNER_IP.encode()).hexdigest() not in [r[0] for r in rows]


def test_only_the_most_recent_networks_are_kept(client):
    signup_owner(client)
    for i in range(auth.MAX_KNOWN_IPS + 5):
        assert login(client, f"192.0.2.{i}").status_code == 200

    conn = sqlite3.connect(config.DATABASE_PATH)
    count = conn.execute("SELECT COUNT(*) FROM login_ips").fetchone()[0]
    conn.close()
    assert count == auth.MAX_KNOWN_IPS


def test_each_installation_has_its_own_hashing_key(tmp_path, monkeypatch):
    hashes = []
    for name in ("one", "two"):
        path = tmp_path / f"{name}.db"
        monkeypatch.setattr(config, "DATABASE_PATH", path)
        monkeypatch.setattr(main, "DATABASE_PATH", path)
        monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
        monkeypatch.setattr(config, "TRUST_PROXY", True)
        monkeypatch.setattr(auth, "SCRYPT_N", 2**4)
        for limiter in auth.ALL_LIMITERS:
            limiter._hits.clear()
        with TestClient(main.app) as c:
            post(c, "register", OWNER_IP, email=OWNER, password=PASSWORD)
        conn = sqlite3.connect(path)
        hashes.append(conn.execute("SELECT ip_hash FROM login_ips").fetchone()[0])
        conn.close()

    assert hashes[0] != hashes[1]


def test_proxy_headers_are_ignored_unless_a_proxy_is_trusted(client, monkeypatch):
    signup_owner(client)
    monkeypatch.setattr(config, "TRUST_PROXY", False)

    # Every request now looks like the same direct client, whatever the header says,
    # so a spoofed address cannot be used to dodge the per-IP limits.
    codes = [login(client, f"203.0.113.{i}", password="wrong password").status_code for i in range(7)]

    assert codes == [401] * 5 + [429] * 2
