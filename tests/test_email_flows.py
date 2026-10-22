import logging
import re
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from backend import admin, auth, config, mailer, main
from tests.fake_smtp import FakeSMTPServer

PASSWORD = "correct horse battery"
PUBLIC = "https://finpulse.test"


@pytest.fixture
def mail(tmp_path, monkeypatch):
    """The API with email enabled; `outbox` collects every email it tries to send."""
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_BACKEND", "console")
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    monkeypatch.setattr(config, "PUBLIC_URL", PUBLIC)

    outbox = []
    monkeypatch.setattr(
        mailer, "send_email",
        lambda to, subject, body: outbox.append({"to": to, "subject": subject, "body": body}),
    )
    with TestClient(main.app) as client:
        yield client, outbox


def token_from(email, kind):
    match = re.search(rf"#{kind}=([A-Za-z0-9_-]+)", email["body"])
    assert match, f"no {kind} link in: {email['body']}"
    return match.group(1)


def register(client, email="alice@example.com", password=PASSWORD):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response


def login(client, email="alice@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---- verification --------------------------------------------------------------

def test_register_emails_a_verification_link_built_from_the_configured_url(mail):
    client, outbox = mail

    user = register(client).json()["user"]

    assert user["email_verified"] is False
    assert len(outbox) == 1 and outbox[0]["to"] == "alice@example.com"
    assert outbox[0]["body"].count(f"{PUBLIC}/#verify=") == 1   # fragment, never a query string
    assert "?" not in re.search(r"https?://\S+", outbox[0]["body"]).group(0)


def test_paper_trading_is_locked_until_the_address_is_confirmed(mail):
    client, outbox = mail
    register(client)

    locked = client.get("/api/paper/portfolio")
    assert locked.status_code == 403 and "confirm your email" in locked.json()["detail"]
    assert client.post("/api/paper/reset", json={}).status_code == 403
    assert client.get("/api/live/status").status_code == 200       # market data stays public

    client.post("/api/auth/verify-email", json={"token": token_from(outbox[0], "verify")})

    assert client.get("/api/paper/portfolio").status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["user"]["email_verified"] is True
    assert me["verification_required"] is True and me["email_enabled"] is True


def test_verification_links_are_single_use_and_garbage_is_rejected(mail):
    client, outbox = mail
    register(client)
    token = token_from(outbox[0], "verify")

    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    again = client.post("/api/auth/verify-email", json={"token": token})
    assert again.status_code == 400 and again.json()["detail"] == auth.INVALID_LINK
    for junk in ("", "nope", "x" * 5000, token[:-1] + "A"):
        assert client.post("/api/auth/verify-email", json={"token": junk}).status_code == 400


def test_expired_verification_links_are_rejected(mail):
    client, outbox = mail
    register(client)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute("UPDATE email_tokens SET expires_at = ?", (int(time.time()) - 1,))
    conn.commit()
    conn.close()

    assert client.post("/api/auth/verify-email", json={"token": token_from(outbox[0], "verify")}).status_code == 400
    assert client.get("/api/paper/portfolio").status_code == 403


def test_tokens_are_stored_hashed_and_a_reset_token_cannot_verify(mail):
    client, outbox = mail
    register(client)
    verify_token = token_from(outbox[0], "verify")
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    reset_token = token_from(outbox[1], "reset")

    conn = sqlite3.connect(config.DATABASE_PATH)
    stored = [row[0] for row in conn.execute("SELECT token_hash FROM email_tokens")]
    conn.close()
    assert verify_token not in stored and reset_token not in stored
    assert client.post("/api/auth/verify-email", json={"token": reset_token}).status_code == 400
    assert client.post("/api/auth/reset-password",
                       json={"token": verify_token, "password": "a new password"}).status_code == 400


def test_resend_needs_a_session_respects_a_cooldown_and_replaces_the_old_link(mail):
    client, outbox = mail
    with TestClient(main.app) as anonymous:
        assert anonymous.post("/api/auth/resend-verification").status_code == 401

    register(client)
    first = token_from(outbox[0], "verify")
    too_soon = client.post("/api/auth/resend-verification")
    assert too_soon.status_code == 429 and int(too_soon.headers["retry-after"]) > 0
    assert len(outbox) == 1

    conn = sqlite3.connect(config.DATABASE_PATH)             # pretend the first link is 2 minutes old
    conn.execute("UPDATE email_tokens SET created_at = created_at - 120")
    conn.commit()
    conn.close()

    assert client.post("/api/auth/resend-verification").status_code == 200
    assert len(outbox) == 2
    second = token_from(outbox[1], "verify")
    assert second != first
    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400   # replaced
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200
    assert client.post("/api/auth/resend-verification").json()["already_verified"] is True


def test_nothing_is_required_or_sent_when_email_is_off(mail, monkeypatch):
    client, outbox = mail
    monkeypatch.setattr(config, "EMAIL_BACKEND", "off")
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", False)

    register(client, email="private@example.com")

    assert outbox == []
    assert client.get("/api/paper/portfolio").status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["verification_required"] is False and me["email_enabled"] is False
    client.post("/api/auth/forgot-password", json={"email": "private@example.com"})
    assert outbox == []


def test_operator_can_verify_an_account_without_email(mail):
    client, outbox = mail
    register(client)
    assert client.get("/api/paper/portfolio").status_code == 403

    assert admin.verify_user("ALICE@example.com") is True

    assert client.get("/api/paper/portfolio").status_code == 200
    assert admin.verify_user("nobody@example.com") is False


# ---- forgot / reset password ---------------------------------------------------------

def test_forgot_password_answers_identically_and_only_emails_real_accounts(mail):
    client, outbox = mail
    register(client)
    outbox.clear()

    known = client.post("/api/auth/forgot-password", json={"email": "Alice@Example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    garbage = client.post("/api/auth/forgot-password", json={"email": "not even an email"})

    assert known.status_code == unknown.status_code == garbage.status_code == 200
    assert known.json() == unknown.json() == garbage.json() == auth.FORGOT_RESPONSE
    assert [m["to"] for m in outbox] == ["alice@example.com"]
    assert outbox[0]["body"].count(f"{PUBLIC}/#reset=") == 1


def test_a_forged_host_header_cannot_redirect_the_reset_link(mail):
    client, outbox = mail
    register(client)
    outbox.clear()

    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"},
                headers={"host": "evil.example", "x-forwarded-host": "evil.example"})

    assert "evil.example" not in outbox[0]["body"]
    assert PUBLIC in outbox[0]["body"]


def test_reset_flow_sets_a_new_password_signs_out_everywhere_and_verifies(mail):
    client, outbox = mail
    register(client)                                         # unverified, signed in
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = token_from(outbox[-1], "reset")

    with TestClient(main.app) as other_browser:
        done = other_browser.post("/api/auth/reset-password",
                                  json={"token": token, "password": "brand new passphrase"})
        assert done.status_code == 200

    assert client.get("/api/auth/me").json()["user"] is None                 # old session revoked
    assert login(client, password=PASSWORD).status_code == 401               # old password dead
    signed_in = login(client, password="brand new passphrase")
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["email_verified"] is True                # proved inbox control
    assert client.get("/api/paper/portfolio").status_code == 200


def test_reset_links_are_single_use_expire_and_bad_passwords_do_not_burn_them(mail):
    client, outbox = mail
    register(client)
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = token_from(outbox[-1], "reset")

    too_short = client.post("/api/auth/reset-password", json={"token": token, "password": "short"})
    assert too_short.status_code == 422                       # typo: the link must still work
    assert client.post("/api/auth/reset-password",
                       json={"token": token, "password": "a long enough password"}).status_code == 200
    assert client.post("/api/auth/reset-password",
                       json={"token": token, "password": "another long password"}).status_code == 400

    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    expired = token_from(outbox[-1], "reset")
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute("UPDATE email_tokens SET expires_at = 1")
    conn.commit()
    conn.close()
    assert client.post("/api/auth/reset-password",
                       json={"token": expired, "password": "yet another password"}).status_code == 400


def test_a_new_reset_request_invalidates_the_previous_link(mail):
    client, outbox = mail
    register(client)
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    old, new = token_from(outbox[-2], "reset"), token_from(outbox[-1], "reset")

    assert client.post("/api/auth/reset-password", json={"token": old, "password": "whatever long one"}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": new, "password": "whatever long one"}).status_code == 200


def test_reset_clears_login_lockouts_for_that_account(mail, monkeypatch):
    client, outbox = mail
    register(client)
    client.post("/api/auth/verify-email", json={"token": token_from(outbox[0], "verify")})
    for _ in range(5):
        login(client, password="wrong password")
    assert login(client).status_code == 429                                  # this IP is locked for this email

    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    client.post("/api/auth/reset-password",
                json={"token": token_from(outbox[-1], "reset"), "password": "fresh start password"})

    assert login(client, password="fresh start password").status_code == 200


def test_reset_requests_are_rate_limited_without_revealing_anything(mail):
    client, outbox = mail
    register(client)
    outbox.clear()

    codes = [client.post("/api/auth/forgot-password", json={"email": "alice@example.com"}).status_code
             for _ in range(9)]

    assert codes == [200] * 9                                 # same answer even when suppressed
    assert len(outbox) == 5                                   # per-email budget: the rest are dropped silently
    for _ in range(3):
        last = client.post("/api/auth/forgot-password", json={"email": "other@example.com"})
    assert last.status_code == 429                            # per-IP ceiling (10/hour)


def test_wrong_links_are_throttled_per_ip(mail):
    client, _ = mail

    codes = [client.post("/api/auth/verify-email", json={"token": f"guess{i}"}).status_code
             for i in range(32)]

    assert codes[:30] == [400] * 30 and codes[30:] == [429, 429]


def test_duplicate_signup_points_the_owner_to_forgot_password(mail):
    client, _ = mail
    register(client)

    again = client.post("/api/auth/register", json={"email": "alice@example.com", "password": PASSWORD})

    assert again.status_code == 409 and "Forgot password" in again.json()["detail"]


def test_deleting_a_user_removes_their_links_and_remembered_networks(mail):
    client, outbox = mail
    register(client)
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})

    admin.delete_user("alice@example.com")

    conn = sqlite3.connect(config.DATABASE_PATH)
    assert conn.execute("SELECT COUNT(*) FROM email_tokens").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM login_ips").fetchone()[0] == 0
    conn.close()


# ---- the mailer itself ---------------------------------------------------------------

@pytest.fixture
def smtp(monkeypatch):
    with FakeSMTPServer() as server:
        monkeypatch.setattr(config, "EMAIL_BACKEND", "smtp")
        monkeypatch.setattr(config, "SMTP_HOST", "127.0.0.1")
        monkeypatch.setattr(config, "SMTP_PORT", server.port)
        monkeypatch.setattr(config, "SMTP_STARTTLS", False)
        monkeypatch.setattr(config, "SMTP_SSL", False)
        monkeypatch.setattr(config, "SMTP_USER", None)
        monkeypatch.setattr(config, "EMAIL_FROM", "FinPulse <hello@finpulse.test>")
        yield server


def test_smtp_backend_delivers_a_well_formed_message(smtp):
    subject, body = mailer.verification_email(f"{PUBLIC}/#verify=abc123")

    mailer.send_email("alice@example.com", subject, body)

    assert len(smtp.inbox) == 1
    message = smtp.inbox[0]["message"]
    assert message["To"] == "alice@example.com"
    assert message["From"] == "FinPulse <hello@finpulse.test>"
    assert message["Subject"] == "Confirm your email for FinPulse"
    assert f"{PUBLIC}/#verify=abc123" in message.get_content()
    assert "ignore this email" in message.get_content()


def test_a_hostile_address_cannot_inject_headers(smtp):
    with pytest.raises(mailer.MailError):
        mailer.send_email("victim@example.com\r\nBcc: attacker@example.com", "Hi", "body")

    assert smtp.inbox == []


def test_send_failures_raise_but_background_sending_only_logs(monkeypatch, caplog):
    monkeypatch.setattr(config, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(config, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "SMTP_PORT", 1)               # nothing is listening
    monkeypatch.setattr(config, "SMTP_STARTTLS", False)

    with pytest.raises(mailer.MailError):
        mailer.send_email("a@example.com", "s", "b")
    with caplog.at_level(logging.ERROR, logger="finpulse.mail"):
        mailer.send_quietly("a@example.com", "s", "b")        # must not raise
    assert "Could not send email" in caplog.text


def test_console_backend_logs_the_message_and_off_sends_nothing(monkeypatch, caplog, smtp):
    monkeypatch.setattr(config, "EMAIL_BACKEND", "console")
    with caplog.at_level(logging.WARNING, logger="finpulse.mail"):
        mailer.send_email("a@example.com", "Subject line", "the body with a link")
    assert "the body with a link" in caplog.text and smtp.inbox == []

    monkeypatch.setattr(config, "EMAIL_BACKEND", "off")
    mailer.send_email("a@example.com", "s", "b")
    assert smtp.inbox == [] and not mailer.enabled()


def test_registration_really_sends_over_smtp_in_the_background(tmp_path, monkeypatch, smtp):
    path = tmp_path / "finpulse.db"
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    monkeypatch.setattr(main, "DATABASE_PATH", path)
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    monkeypatch.setattr(config, "PUBLIC_URL", PUBLIC)

    with TestClient(main.app) as client:
        register(client, email="smtp-user@example.com")

    assert len(smtp.inbox) == 1
    assert smtp.inbox[0]["message"]["To"] == "smtp-user@example.com"
    assert "#verify=" in smtp.inbox[0]["message"].get_content()
