"""Account administration for whoever runs the server.

Account tasks for the person running the server:

    python -m backend.admin list-users
    python -m backend.admin verify-user someone@example.com
    python -m backend.admin set-password someone@example.com
    python -m backend.admin delete-user someone@example.com

People can also reset their own password by email once SMTP is configured; this is
the fallback for when email is not set up.

With Docker:  docker compose exec api python -m backend.admin list-users
"""
import argparse
import getpass
import sys
import time

from backend import auth, db

PAPER_TABLES = ("paper_orders", "paper_positions", "paper_equity", "paper_account")


def list_users() -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, email, created_at, email_verified_at FROM users ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def verify_user(email: str) -> bool:
    """Mark an address as confirmed without an email round trip. False if no such user."""
    conn = db.connect()
    try:
        cursor = conn.execute(
            "UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE email = ?",
            (int(time.time()), email.strip().lower()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def set_password(email: str, password: str) -> bool:
    """Set a new password and sign the user out everywhere. False if no such user."""
    if not auth.MIN_PASSWORD <= len(password) <= auth.MAX_PASSWORD:
        raise ValueError(f"Password must be {auth.MIN_PASSWORD}-{auth.MAX_PASSWORD} characters.")

    conn = db.connect()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (auth.hash_password(password), row["id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    auth.login_by_email.clear(email.strip().lower())  # in case they were locked out (same process only)
    return True


def delete_user(email: str) -> bool:
    """Remove the account, its sessions and all of its paper-trading data."""
    conn = db.connect()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if row is None:
            return False
        for table in PAPER_TABLES:
            try:
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (row["id"],))
            except Exception:  # table not created yet: this user never traded
                pass
        conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))  # sessions cascade
        conn.commit()
    finally:
        conn.close()
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.admin", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-users")
    for name in ("verify-user", "set-password", "delete-user"):
        commands.add_parser(name).add_argument("email")
    args = parser.parse_args(argv)

    db.init_db()

    if args.command == "list-users":
        for user in list_users():
            mark = "verified" if user["email_verified_at"] else "unverified"
            print(f"{user['id']:>4}  {user['email']}  ({mark})")
        return 0

    if args.command == "set-password":
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Repeat: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
        try:
            found = set_password(args.email, password)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    elif args.command == "verify-user":
        found = verify_user(args.email)
    else:
        found = delete_user(args.email)

    if not found:
        print(f"No account for {args.email}.", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
