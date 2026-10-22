"""Email-and-password accounts with server-side sessions.

Design:
  * Passwords are hashed with scrypt (standard library, memory-hard) and a
    per-user random salt, and compared in constant time.
  * A login creates a random session token. Only its SHA-256 is stored, so a
    leaked database cannot be replayed as live sessions. The token travels in
    an httpOnly, SameSite=Lax cookie that scripts cannot read.
  * When email is configured, new accounts must confirm their address before
    they can paper trade, and anyone can reset a forgotten password through an
    emailed one-time link. Those links carry a random token (stored only as a
    hash), expire, work once, and are built from the configured PUBLIC_URL, not
    from the request, so a forged Host header cannot redirect them.
  * Login failures are counted per (email, IP) pair, so a stranger guessing
    your address cannot lock you out. A higher per-email ceiling still slows
    guessing spread over many IPs, and during it only networks the owner has
    signed in from before are let through.
  * Login, registration and the email endpoints are rate limited, and failures
    return one generic message so responses do not reveal which emails exist.
  * State-changing requests from another origin are rejected (CSRF defence in
    depth on top of SameSite).
"""
import base64
import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.requests import HTTPConnection

from backend import config, db, mailer

log = logging.getLogger("finpulse.auth")

router = APIRouter(prefix="/api/auth", tags=["accounts"])

SESSION_COOKIE = "finpulse_session"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
# Capping the length stops someone from making the server hash megabytes.
MAX_PASSWORD = 128
MAX_TOKEN_LENGTH = 200

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2**14, 8, 1, 32

RESEND_COOLDOWN_SECONDS = 60
KNOWN_IP_DAYS = 30
MAX_KNOWN_IPS = 20

INVALID_LINK = "This link is invalid or has expired."
FORGOT_RESPONSE = {
    "ok": True,
    "message": "If an account exists for that email, a reset link is on its way.",
}


# ---- passwords ---------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p),
            dklen=len(base64.b64decode(expected)),
        )
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


# Checked when the email is unknown, so "no such user" costs the same time as
# "wrong password".
_DUMMY_HASH = hash_password("not-a-real-password")


# ---- rate limiting -----------------------------------------------------------

class RateLimiter:
    """Sliding-window counter, kept in memory (fine for one server process)."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again; 0 if it is not blocked."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) < self.limit:
                return 0
            return max(1, int(self.window - (now - hits[0])))

    def record(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(key, now).append(now)
            if len(self._hits) > 10_000:  # bound memory under a key-spraying attack
                for stale in [k for k in self._hits if not self._prune(k, now)]:
                    del self._hits[stale]

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear_where(self, matches: Callable[[str], bool]) -> None:
        with self._lock:
            for key in [k for k in self._hits if matches(k)]:
                del self._hits[key]


FIFTEEN_MINUTES = 15 * 60
ONE_HOUR = 60 * 60

# Login failures are counted three ways. The (email, IP) pair is what stops a
# stranger from locking the owner out: their failures only fill *their* slot.
login_by_pair = RateLimiter(limit=5, window_seconds=FIFTEEN_MINUTES)
login_by_ip = RateLimiter(limit=30, window_seconds=FIFTEEN_MINUTES)
# Ceiling for guessing spread across many IPs (see the comment in login()).
login_by_email = RateLimiter(limit=60, window_seconds=FIFTEEN_MINUTES)

register_by_ip = RateLimiter(limit=10, window_seconds=ONE_HOUR)
forgot_by_ip = RateLimiter(limit=10, window_seconds=ONE_HOUR)
forgot_by_email = RateLimiter(limit=5, window_seconds=ONE_HOUR)
bad_link_by_ip = RateLimiter(limit=30, window_seconds=FIFTEEN_MINUTES)
resend_by_user = RateLimiter(limit=5, window_seconds=ONE_HOUR)

ALL_LIMITERS = (
    login_by_pair, login_by_ip, login_by_email, register_by_ip,
    forgot_by_ip, forgot_by_email, bad_link_by_ip, resend_by_user,
)


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many(wait: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Too many attempts. Try again in {wait // 60 + 1} minute(s).",
        headers={"Retry-After": str(wait)},
    )


def _enforce(limiter: RateLimiter, key: str) -> None:
    wait = limiter.retry_after(key)
    if wait:
        raise _too_many(wait)


# ---- known networks ------------------------------------------------------------

def _ip_hash(conn: sqlite3.Connection, ip: str) -> str:
    """Keyed hash of an address: IPv4 is small enough to brute force if unkeyed."""
    secret = conn.execute("SELECT value FROM app_secret WHERE id = 1").fetchone()["value"]
    return hmac.new(secret, ip.encode(), hashlib.sha256).hexdigest()


def _remember_ip(conn: sqlite3.Connection, user_id: int, ip: str) -> None:
    conn.execute(
        "INSERT INTO login_ips (user_id, ip_hash, last_seen) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, ip_hash) DO UPDATE SET last_seen = excluded.last_seen",
        (user_id, _ip_hash(conn, ip), int(time.time())),
    )
    conn.execute(
        "DELETE FROM login_ips WHERE user_id = ? AND ip_hash NOT IN "
        "(SELECT ip_hash FROM login_ips WHERE user_id = ? ORDER BY last_seen DESC LIMIT ?)",
        (user_id, user_id, MAX_KNOWN_IPS),
    )


def _is_known_ip(conn: sqlite3.Connection, user_id: int, ip: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM login_ips WHERE user_id = ? AND ip_hash = ? AND last_seen > ?",
        (user_id, _ip_hash(conn, ip), int(time.time()) - KNOWN_IP_DAYS * 86_400),
    ).fetchone()
    return row is not None


# ---- sessions ----------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_token_hash(token), user_id, now, now + config.SESSION_DAYS * 86_400),
    )
    return token


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=config.SESSION_DAYS * 86_400,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _public_user(row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "email_verified": row["email_verified_at"] is not None,
    }


def _user_for_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT users.id, users.email, users.email_verified_at FROM sessions "
            "JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
            (_token_hash(token), int(time.time())),
        ).fetchone()
    finally:
        conn.close()
    return _public_user(row) if row else None


def optional_user(request: Request) -> Optional[dict]:
    return _user_for_token(request.cookies.get(SESSION_COOKIE))


def current_user(request: Request) -> dict:
    """Dependency: the signed-in user, or a 401."""
    user = optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in to use paper trading.")
    return user


def verified_user(user: dict = Depends(current_user)) -> dict:
    """Dependency: a signed-in user whose email is confirmed (when that is required)."""
    if config.REQUIRE_EMAIL_VERIFICATION and not user["email_verified"]:
        raise HTTPException(
            status_code=403,
            detail="Please confirm your email address to use paper trading. "
                   "Check your inbox for the link.",
        )
    return user


def warn_about_email_config() -> None:
    """Log (at startup) settings that would leave users stuck."""
    if config.REQUIRE_EMAIL_VERIFICATION and not mailer.enabled():
        log.warning(
            "Email verification is required but no email backend is configured, so "
            "nobody can verify. Set SMTP_HOST (or EMAIL_BACKEND=console for development), "
            "or set REQUIRE_EMAIL_VERIFICATION=false."
        )
    if config.EMAIL_BACKEND == "smtp" and config.PUBLIC_URL.startswith("http://localhost"):
        log.warning(
            "PUBLIC_URL is %s, so links in real emails will point there. "
            "Set PUBLIC_URL to your site's address.", config.PUBLIC_URL,
        )


# ---- cross-site request protection ----------------------------------------------

def origin_allowed(connection: HTTPConnection) -> bool:
    """Is this request from this site (or a configured frontend)?

    Browsers always send Origin on cross-site POSTs and WebSocket handshakes.
    It must match this host or one of the configured frontend origins; requests
    without it (curl, tests) are not cross-site browser requests and pass.
    """
    origin = connection.headers.get("origin")
    if not origin or origin in config.CORS_ORIGINS:
        return True
    return urlparse(origin).netloc == connection.headers.get("host")


def check_origin(connection: HTTPConnection) -> None:
    """App-wide dependency: block state-changing requests from other sites.

    Takes HTTPConnection (not Request) because FastAPI runs app-wide
    dependencies for WebSocket routes too, and a Request cannot be built there.
    WebSockets are checked inside their handler, where the socket can be
    closed cleanly.
    """
    if connection.scope["type"] != "http":
        return
    if connection.scope["method"] in ("GET", "HEAD", "OPTIONS"):
        return
    if not origin_allowed(connection):
        raise HTTPException(status_code=403, detail="Cross-site request blocked.")


# ---- one-time email links ------------------------------------------------------

def _issue_token(conn: sqlite3.Connection, user_id: int, purpose: str, ttl_seconds: int) -> str:
    """Create a fresh link token, replacing any earlier one of the same kind."""
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    conn.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (user_id, purpose))
    conn.execute(
        "INSERT INTO email_tokens (token_hash, user_id, purpose, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (_token_hash(token), user_id, purpose, now, now + ttl_seconds),
    )
    return token


def _lookup_token(conn: sqlite3.Connection, token: str, purpose: str) -> Optional[int]:
    """The user a valid, unexpired token of this kind belongs to (else None)."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    row = conn.execute(
        "SELECT user_id FROM email_tokens WHERE token_hash = ? AND purpose = ? AND expires_at > ?",
        (_token_hash(token), purpose, int(time.time())),
    ).fetchone()
    return row["user_id"] if row else None


def _link(kind: str, token: str) -> str:
    # In the URL fragment (#...), so the token is never sent to any server, written to
    # access logs, or leaked through the Referer header. The page reads it in JavaScript.
    return f"{config.PUBLIC_URL}/#{kind}={token}"


def _queue_verification_email(background: BackgroundTasks, email: str, token: str) -> None:
    subject, body = mailer.verification_email(_link("verify", token))
    background.add_task(mailer.send_quietly, email, subject, body)


def _send_reset_if_account_exists(email: str) -> None:
    """Background job: runs after the response, so timing never reveals the answer."""
    conn = db.connect()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            return
        token = _issue_token(conn, row["id"], "reset", config.RESET_TOKEN_MINUTES * 60)
        conn.commit()
    finally:
        conn.close()
    subject, body = mailer.reset_email(_link("reset", token))
    mailer.send_quietly(email, subject, body)


# ---- endpoints ---------------------------------------------------------------

class Credentials(BaseModel):
    email: str
    password: str


class TokenBody(BaseModel):
    token: str


class EmailBody(BaseModel):
    email: str


class ResetBody(BaseModel):
    token: str
    password: str


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def _check_password_length(password: str) -> None:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be {MIN_PASSWORD}-{MAX_PASSWORD} characters.",
        )


@router.post("/register", status_code=201)
def register(
    credentials: Credentials, request: Request, response: Response, background: BackgroundTasks
):
    if not config.ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Registration is closed on this server.")

    ip = client_ip(request)
    _enforce(register_by_ip, ip)
    register_by_ip.record(ip)

    email = _normalize_email(credentials.email)
    _check_password_length(credentials.password)

    conn = db.connect()
    try:
        try:
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, hash_password(credentials.password), int(time.time())),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists. Sign in, or use "
                       "\"Forgot password\" if it is yours.",
            ) from None
        user_id = cursor.lastrowid
        verification_token = None
        if config.REQUIRE_EMAIL_VERIFICATION and mailer.enabled():
            verification_token = _issue_token(
                conn, user_id, "verify", config.VERIFY_TOKEN_HOURS * 3600
            )
        _remember_ip(conn, user_id, ip)
        token = _create_session(conn, user_id)
        conn.commit()
    finally:
        conn.close()

    if verification_token:
        _queue_verification_email(background, email, verification_token)

    _set_cookie(response, token)
    return {"user": {"id": user_id, "email": email, "email_verified": False}}


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response):
    ip = client_ip(request)
    email = credentials.email.strip().lower()
    pair = f"{email}|{ip}"

    _enforce(login_by_ip, ip)
    _enforce(login_by_pair, pair)

    # Bound the work an attacker can force with a huge password.
    password = credentials.password[:MAX_PASSWORD + 1]

    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT id, email, email_verified_at, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        # Ceiling for password guessing spread across many IPs. Once one email has seen
        # too many failures from anywhere, only networks that account has signed in from
        # before may keep trying. An attacker cannot be on one of those, so the owner is
        # never locked out on their usual network, however many addresses the attacker uses.
        global_wait = login_by_email.retry_after(email)
        if global_wait and not (row and _is_known_ip(conn, row["id"], ip)):
            raise _too_many(global_wait)

        valid = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)

        if not row or not valid or len(credentials.password) > MAX_PASSWORD:
            login_by_ip.record(ip)
            login_by_pair.record(pair)
            login_by_email.record(email)
            raise HTTPException(status_code=401, detail="Incorrect email or password.")

        login_by_pair.clear(pair)
        _remember_ip(conn, row["id"], ip)
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        token = _create_session(conn, row["id"])
        conn.commit()
    finally:
        conn.close()

    _set_cookie(response, token)
    return {"user": _public_user(row)}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        conn = db.connect()
        try:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
            conn.commit()
        finally:
            conn.close()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: Optional[dict] = Depends(optional_user)):
    """The signed-in user, or `{"user": null}` (not an error: logged-out is normal)."""
    return {
        "user": user,
        "registration_open": config.ALLOW_REGISTRATION,
        "verification_required": config.REQUIRE_EMAIL_VERIFICATION,
        "email_enabled": mailer.enabled(),
    }


@router.post("/verify-email")
def verify_email(body: TokenBody, request: Request):
    """Confirm an address with the token from the emailed link."""
    ip = client_ip(request)
    _enforce(bad_link_by_ip, ip)

    conn = db.connect()
    try:
        user_id = _lookup_token(conn, body.token, "verify")
        if user_id is None:
            bad_link_by_ip.record(ip)
            raise HTTPException(status_code=400, detail=INVALID_LINK)
        conn.execute(
            "UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?",
            (int(time.time()), user_id),
        )
        conn.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = 'verify'", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/resend-verification")
def resend_verification(background: BackgroundTasks, user: dict = Depends(current_user)):
    """Email a fresh verification link to the signed-in, unverified user."""
    if user["email_verified"]:
        return {"ok": True, "already_verified": True}
    if not mailer.enabled():
        raise HTTPException(status_code=400, detail="Email is not set up on this server.")

    conn = db.connect()
    try:
        last = conn.execute(
            "SELECT created_at FROM email_tokens WHERE user_id = ? AND purpose = 'verify'",
            (user["id"],),
        ).fetchone()
        if last:
            wait = RESEND_COOLDOWN_SECONDS - (int(time.time()) - last["created_at"])
            if wait > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"A link was just sent. You can ask for another in {wait} seconds.",
                    headers={"Retry-After": str(wait)},
                )
        _enforce(resend_by_user, str(user["id"]))
        resend_by_user.record(str(user["id"]))
        token = _issue_token(conn, user["id"], "verify", config.VERIFY_TOKEN_HOURS * 3600)
        conn.commit()
    finally:
        conn.close()

    _queue_verification_email(background, user["email"], token)
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(body: EmailBody, request: Request, background: BackgroundTasks):
    """Email a reset link if the address has an account.

    The answer is always the same, whether or not the account exists, and the
    lookup and sending happen after the response, so neither the wording nor
    the timing reveals which emails are registered.
    """
    ip = client_ip(request)
    email = body.email.strip().lower()

    _enforce(forgot_by_ip, ip)
    forgot_by_ip.record(ip)
    over_email_budget = forgot_by_email.retry_after(email) > 0   # silently drops, never tells
    forgot_by_email.record(email)

    if mailer.enabled() and not over_email_budget:
        background.add_task(_send_reset_if_account_exists, email)
    return FORGOT_RESPONSE


@router.post("/reset-password")
def reset_password(body: ResetBody, request: Request):
    """Choose a new password with the token from the emailed link."""
    ip = client_ip(request)
    _enforce(bad_link_by_ip, ip)
    _check_password_length(body.password)   # before touching the token, so a typo does not burn it

    conn = db.connect()
    try:
        user_id = _lookup_token(conn, body.token, "reset")
        if user_id is None:
            bad_link_by_ip.record(ip)
            raise HTTPException(status_code=400, detail=INVALID_LINK)

        email = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()["email"]
        conn.execute(
            "UPDATE users SET password_hash = ?, "
            "email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?",
            (hash_password(body.password), int(time.time()), user_id),   # the link proves the inbox
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))   # sign out everywhere
        conn.execute("DELETE FROM email_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()

    # A fresh start for this account's login counters.
    login_by_email.clear(email)
    login_by_pair.clear_where(lambda key: key.startswith(f"{email}|"))
    return {"ok": True}
