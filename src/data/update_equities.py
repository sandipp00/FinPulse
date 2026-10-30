"""Append new daily bars for stored instruments: stocks, indices and metals from Yahoo
Finance (yfinance), and BTC/ETH from Binance's public daily klines.

Safe by construction:
  * dry run by default: reports what would be added and writes nothing;
  * append-only: only bars dated after a symbol's newest stored bar are inserted,
    with INSERT OR IGNORE, so existing rows are never changed;
  * adjustment check: Yahoo's adjusted prices are recalculated after dividends and
    splits, so the last stored bars are re-downloaded and compared first. If they
    no longer match, the symbol is skipped and reported instead of mixing two
    adjustment bases in one series;
  * only completed days: bars dated today (UTC) or later are dropped, since a bar
    for the current session can still change;
  * --replace-newest SYMBOL is the one exception to append-only: it replaces that
    symbol's newest stored bar with Yahoo's final values, and only when that bar is
    the sole mismatch and at least MIN_MATCHING_DAYS older days match exactly (the
    signature of a bar saved before its session closed);
  * with --apply, the database is first copied with SQLite's backup API to
    data/backups/ and the copy is checked before anything is written.

Yahoo Finance data is for personal use; FinPulse is run as a personal terminal.
Crypto daily bars come from the same Binance endpoint (and the same exchange) as
the stored history, so the adjustment check compares like with like.

    python src/data/update_equities.py            # dry run
    python src/data/update_equities.py --apply    # back up, then append
    python src/data/update_equities.py --apply --replace-newest AAPL
"""
import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # lets `python src/data/update_equities.py` import src.*

from src.data.build_database import validate_frame  # noqa: E402

DB_PATH = ROOT / "data" / "finpulse.db"
BACKUP_DIR = ROOT / "data" / "backups"

# symbol -> asset_type, as stored in market_prices.
SYMBOLS = {
    "AAPL": "stock",
    "^NSEI": "index",
    "^GSPC": "index",
    # COMEX front-month futures (continuous contract), not spot prices.
    "GC=F": "commodity",
    "SI=F": "commodity",
    # Binance spot daily klines (see fetch_binance_daily).
    "BTC/USDT": "crypto",
    "ETH/USDT": "crypto",
}

BINANCE_REST_URLS = ("https://api.binance.com", "https://data-api.binance.vision")
BINANCE_PAGE = 1000

# Yahoo keeps updating a futures contract's newest daily bar after settlement (into
# the evening session), so for these asset types the newest bar is held back until
# a later one exists.
HOLD_BACK_NEWEST = {"commodity"}

# A symbol with no stored history is downloaded from here (matches the others).
NEW_SYMBOL_START = "2023-01-01"
# How many calendar days before the newest stored bar to re-download for the check.
OVERLAP_DAYS = 10
# Largest relative difference between a stored and a re-downloaded close that
# still counts as the same adjustment basis (allows for float rounding only).
MATCH_TOLERANCE = 0.0005
# Older days that must match before a newest bar may be replaced.
MIN_MATCHING_DAYS = 3


@dataclass
class SymbolPlan:
    symbol: str
    asset_type: str
    stored_last: Optional[str] = None
    overlap_checked: int = 0
    overlap_max_diff_pct: Optional[float] = None
    mismatches: list[str] = field(default_factory=list)
    new_rows: Optional[pd.DataFrame] = None
    # (old stored row, new row) when --replace-newest applies to this symbol.
    replacement: Optional[tuple[dict, dict]] = None
    dropped_incomplete: int = 0
    status: str = ""
    error: Optional[str] = None

    @property
    def adds(self) -> int:
        return 0 if self.new_rows is None else len(self.new_rows)

    @property
    def changes(self) -> int:
        return self.adds + (1 if self.replacement else 0)


def fetch_binance_daily(symbol: str, start: str) -> pd.DataFrame:
    """Daily bars from `start` (UTC), in the shape fetch_stock_data returns."""
    import httpx

    start_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    last_error = None
    for base in BINANCE_REST_URLS:
        rows, since = [], start_ms
        try:
            while True:
                response = httpx.get(f"{base}/api/v3/klines", timeout=20, params={
                    "symbol": symbol.replace("/", ""), "interval": "1d", "startTime": since, "limit": BINANCE_PAGE,
                })
                response.raise_for_status()
                page = response.json()
                rows.extend(page)
                if len(page) < BINANCE_PAGE:
                    break
                since = page[-1][0] + 1
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            continue
        if not rows:
            raise ValueError(f"No daily klines returned for {symbol}")
        return pd.DataFrame({
            "timestamp": pd.to_datetime([r[0] for r in rows], unit="ms", utc=True),
            "symbol": symbol,
            "open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
            "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows],
            "volume": [float(r[5]) for r in rows],
        })
    raise ValueError(f"Binance unavailable for {symbol}: {last_error}")


def source_name(symbol: str) -> str:
    return "Binance" if "/" in symbol else "Yahoo"


def default_fetch(symbol: str, start: str) -> pd.DataFrame:
    if "/" in symbol:
        return fetch_binance_daily(symbol, start)
    from src.data.stock_data import fetch_stock_data  # imports yfinance only when used
    return fetch_stock_data(symbol, start=start)


def stored_rows(conn: sqlite3.Connection, symbol: str, asset_type: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT timestamp, open, high, low, close, volume FROM market_prices "
        "WHERE symbol = ? AND asset_type = ? ORDER BY timestamp",
        conn, params=(symbol, asset_type),
    )


def plan_symbol(conn, symbol: str, asset_type: str, fetch: Callable, today: date,
                replace_newest: bool = False) -> SymbolPlan:
    plan = SymbolPlan(symbol, asset_type)
    stored = stored_rows(conn, symbol, asset_type)
    if not stored.empty:
        plan.stored_last = stored["timestamp"].iloc[-1][:10]

    start = NEW_SYMBOL_START if plan.stored_last is None else (
        date.fromisoformat(plan.stored_last) - timedelta(days=OVERLAP_DAYS)
    ).isoformat()
    try:
        fetched = fetch(symbol, start)
        fetched = validate_frame(fetched, asset_type, symbol)
    except Exception as exc:  # network, empty response, validation: report, never write
        plan.status, plan.error = "error", f"{type(exc).__name__}: {exc}"
        return plan

    fetched["day"] = fetched["timestamp"].str[:10]
    complete = fetched[fetched["day"] < today.isoformat()]
    if asset_type in HOLD_BACK_NEWEST:
        complete = complete.iloc[:-1]
    plan.dropped_incomplete = len(fetched) - len(complete)

    if plan.stored_last is not None:
        stored["day"] = stored["timestamp"].str[:10]
        overlap = stored.merge(complete[["day", "close"]], on="day", suffixes=("_stored", "_new"))
        plan.overlap_checked = len(overlap)
        if overlap.empty:
            plan.status, plan.error = "skipped", "No overlapping days to check the adjustment basis against"
            return plan
        diffs = (overlap["close_new"] / overlap["close_stored"] - 1).abs()
        plan.overlap_max_diff_pct = float(diffs.max() * 100)
        bad = overlap[diffs > MATCH_TOLERANCE]
        plan.mismatches = [
            f"{row.day}: stored {row.close_stored:.4f}, {source_name(symbol)} now {row.close_new:.4f}"
            for row in bad.itertuples()
        ]
        if plan.mismatches:
            only_newest = set(bad["day"]) == {plan.stored_last}
            if replace_newest and only_newest and len(overlap) - len(bad) >= MIN_MATCHING_DAYS:
                old = stored[stored["day"] == plan.stored_last].iloc[0].to_dict()
                new = complete[complete["day"] == plan.stored_last].iloc[0].to_dict()
                plan.replacement = (old, new)
            else:
                plan.status = "skipped"
                plan.error = (f"{source_name(symbol)}'s prices for stored days have changed "
                              "(dividend, split or a corrected bar)")
                if replace_newest and not only_newest:
                    plan.error += "; not only the newest bar differs, so it is not replaced"
                elif replace_newest:
                    plan.error += f"; fewer than {MIN_MATCHING_DAYS} older days match, so it is not replaced"
                elif only_newest:
                    plan.error += (". Only the newest stored bar differs, which usually means it was saved before "
                                   f"its session closed; --replace-newest {symbol} would replace it")
                return plan

    new = complete if plan.stored_last is None else complete[complete["day"] > plan.stored_last]
    plan.new_rows = new.drop(columns=["day"]).reset_index(drop=True)
    plan.status = "ready" if plan.changes else "up to date"
    return plan


def backup(db_path: Path, backup_dir: Path, now: datetime) -> Path:
    """Copy the database (including pending WAL pages) and check the copy."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"finpulse-{now:%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            a = src.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            b = dst.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if a != b:
                raise RuntimeError(f"Backup check failed for {table}: {a} rows vs {b}")
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup failed its integrity check")
    finally:
        src.close()
        dst.close()
    return target


def apply(conn: sqlite3.Connection, plans: list[SymbolPlan]) -> int:
    """Apply every ready plan in one transaction: approved replacements, then inserts.

    Returns the number of rows inserted. A replacement must match exactly one row
    (the old values are part of the WHERE clause), or the whole transaction fails.
    """
    inserted = 0
    with conn:
        for plan in plans:
            if plan.status != "ready":
                continue
            if plan.replacement:
                old, new = plan.replacement
                cursor = conn.execute(
                    "UPDATE market_prices SET open = ?, high = ?, low = ?, close = ?, volume = ? "
                    "WHERE timestamp = ? AND symbol = ? AND asset_type = ? AND close = ? AND volume = ?",
                    (new["open"], new["high"], new["low"], new["close"], new["volume"],
                     old["timestamp"], plan.symbol, plan.asset_type, old["close"], old["volume"]),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"{plan.symbol}: expected to replace 1 row, matched {cursor.rowcount}")
            if not plan.adds:
                continue
            rows = plan.new_rows[["timestamp", "symbol", "asset_type", "open", "high", "low", "close", "volume"]]
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO market_prices (timestamp, symbol, asset_type, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                list(rows.itertuples(index=False, name=None)),
            )
            inserted += conn.total_changes - before
    return inserted


def report(plans: list[SymbolPlan]) -> str:
    lines = []
    for p in plans:
        lines.append(f"{p.symbol} ({p.asset_type}): {p.status}")
        lines.append(f"  stored through: {p.stored_last or 'nothing stored (new symbol)'}")
        if p.overlap_checked:
            lines.append(f"  adjustment check: {p.overlap_checked} overlapping days, largest close difference "
                         f"{p.overlap_max_diff_pct:.4f}%")
        for m in p.mismatches:
            lines.append(f"    mismatch {m}")
        if p.replacement:
            old, new = p.replacement
            lines.append(f"  replace {old['day']}: close {old['close']:.4f} -> {new['close']:.4f}, "
                         f"volume {old['volume']:,.0f} -> {new['volume']:,.0f}")
        if p.dropped_incomplete:
            what = ("dated today or later, or the newest futures bar" if p.asset_type in HOLD_BACK_NEWEST
                    else "dated today or later")
            lines.append(f"  ignored {p.dropped_incomplete} bar(s) {what} (session may be unfinished)")
        if p.adds:
            days = p.new_rows["timestamp"].str[:10]
            lines.append(f"  would add {p.adds} bar(s): {days.iloc[0]} to {days.iloc[-1]}")
            flat = p.new_rows[["open", "high", "low"]].eq(p.new_rows["close"], axis=0).all(axis=1)
            if flat.any():
                lines.append(f"  note: {int(flat.sum())} of them have one price for open, high, low and close "
                             "(very thin trading, e.g. an expiring futures contract); stored as reported")
        if p.error:
            lines.append(f"  {p.error}")
    return "\n".join(lines)


def main(argv=None, fetch: Callable = default_fetch, now: Optional[datetime] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="back up the database, then append the new bars")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--backup-dir", type=Path, default=BACKUP_DIR)
    parser.add_argument("--replace-newest", action="append", default=[], metavar="SYMBOL",
                        help="replace this symbol's newest stored bar if it is the only one that differs")
    args = parser.parse_args(argv)
    now = now or datetime.now(timezone.utc)
    unknown = sorted(set(args.replace_newest) - set(SYMBOLS))
    if unknown:
        print(f"--replace-newest: unknown symbol(s) {', '.join(unknown)}. Known: {', '.join(SYMBOLS)}")
        return 2

    if not args.db.exists():
        print(f"Database not found: {args.db}")
        return 1

    conn = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    try:
        plans = [plan_symbol(conn, s, t, fetch, now.date(), s in args.replace_newest)
                 for s, t in SYMBOLS.items()]
    finally:
        conn.close()

    print(report(plans))
    ready = [p for p in plans if p.status == "ready"]
    if not args.apply:
        replaced = sum(1 for p in ready if p.replacement)
        print(f"\nDry run: nothing was written. {sum(p.adds for p in ready)} bar(s) would be added"
              + (f" and {replaced} replaced" if replaced else "") + ". Run with --apply to back up and write.")
        return 0
    if not ready:
        print("\nNothing to add; the database was not touched.")
        return 0

    copy = backup(args.db, args.backup_dir, now)
    print(f"\nBackup written and checked: {copy}")
    conn = sqlite3.connect(args.db, timeout=10)
    try:
        inserted = apply(conn, ready)
    finally:
        conn.close()
    replaced = [p.symbol for p in ready if p.replacement]
    if replaced:
        print(f"Inserted {inserted} new bar(s) and replaced the newest stored bar of {', '.join(replaced)}. "
              "No other existing rows were modified.")
    else:
        print(f"Inserted {inserted} new bar(s). Existing rows were not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
