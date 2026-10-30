"""Each signed-in user's own watchlist: the instruments, in their order, in the right panel.

A user who has never saved one gets the default list (has_custom is false). Saving
replaces the whole list in one transaction; every symbol must be an instrument the
terminal can show, at most MAX_ITEMS, no repeats. Saving an empty list goes back to
the default. Guests keep their list in the browser instead (frontend).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend import auth, db, instruments

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

MAX_ITEMS = 60


def signed_in(request: Request) -> dict:
    user = auth.optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in to save a watchlist to your account.")
    return user


class WatchlistIn(BaseModel):
    symbols: list[str] = Field(max_length=MAX_ITEMS)


def load(user_id: int) -> list[str]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT symbol FROM watchlist_items WHERE user_id = ? ORDER BY position", (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [row["symbol"] for row in rows]


def save(user_id: int, symbols: list[str]) -> None:
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM watchlist_items WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT INTO watchlist_items (user_id, symbol, position) VALUES (?, ?, ?)",
                [(user_id, symbol, i) for i, symbol in enumerate(symbols)],
            )
    finally:
        conn.close()


def validate(symbols: list[str], known: set[str]) -> Optional[str]:
    """An error message, or None if the list can be saved."""
    if len(set(symbols)) != len(symbols):
        return "Each instrument can be in the watchlist once."
    unknown = [s for s in symbols if s not in known]
    if unknown:
        return f"Unknown instrument(s): {', '.join(unknown[:5])}"
    return None


@router.get("")
def get_watchlist(user: dict = Depends(signed_in)):
    """The signed-in user's watchlist; has_custom is false until they save one."""
    symbols = load(user["id"])
    return {"symbols": symbols, "has_custom": bool(symbols), "max_items": MAX_ITEMS}


@router.put("")
def put_watchlist(body: WatchlistIn, user: dict = Depends(signed_in)):
    """Replace the signed-in user's watchlist. An empty list restores the default."""
    error = validate(body.symbols, set(instruments.catalogue()))
    if error:
        raise HTTPException(status_code=422, detail=error)
    save(user["id"], body.symbols)
    return {"symbols": body.symbols, "has_custom": bool(body.symbols), "max_items": MAX_ITEMS}
