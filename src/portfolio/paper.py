"""Paper-trading engine: a virtual, long-only crypto account stored in SQLite.

No real money and no exchange orders are involved. Market orders fill at the
price the caller supplies (the API passes the live exchange price) minus a
flat fee, with no slippage, leverage or shorting. Real fills are usually a
little worse, especially for larger orders or fast markets.

Cost basis is the average cost of the open position, and buy fees are
included in it, so realized P&L on a sale already reflects both fees.
"""
import math
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Optional

DEFAULT_STARTING_CASH = 100_000.0
DEFAULT_FEE_RATE = 0.001  # 0.1% per fill, roughly Binance spot
MIN_ORDER_USD = 10.0
QUANTITY_DECIMALS = 8
EPSILON = 1e-9

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    starting_cash REAL NOT NULL,
    cash REAL NOT NULL,
    created_at INTEGER NOT NULL,
    reset_at INTEGER
);
CREATE TABLE IF NOT EXISTS paper_positions (
    symbol TEXT PRIMARY KEY,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL,
    notional REAL NOT NULL,
    realized_pnl REAL,
    source TEXT NOT NULL DEFAULT 'manual',
    signal_rating TEXT
);
CREATE TABLE IF NOT EXISTS paper_equity (
    ts INTEGER PRIMARY KEY,
    equity REAL NOT NULL
);
"""


class OrderError(ValueError):
    """The order was rejected (bad size, not enough cash, nothing to sell...)."""


def _floor_quantity(value: float) -> float:
    factor = 10 ** QUANTITY_DECIMALS
    return math.floor(value * factor + EPSILON) / factor


def _now_ms() -> int:
    return int(time.time() * 1000)


class PaperBroker:
    def __init__(
        self,
        db_path: Path,
        fee_rate: float = DEFAULT_FEE_RATE,
        starting_cash: float = DEFAULT_STARTING_CASH,
    ):
        self.db_path = Path(db_path)
        self.fee_rate = fee_rate
        self.default_starting_cash = starting_cash

    # ---- connection / setup --------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: transactions are managed explicitly below.
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO paper_account (id, starting_cash, cash, created_at) "
            "VALUES (1, ?, ?, ?)",
            (self.default_starting_cash, self.default_starting_cash, _now_ms()),
        )
        return conn

    # ---- reads ---------------------------------------------------------

    def account(self) -> dict:
        with closing(self._connect()) as conn:
            return dict(conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone())

    def positions(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT symbol, quantity, avg_cost FROM paper_positions ORDER BY symbol"
            ).fetchall()
        return [dict(row) for row in rows]

    def orders(self, limit: int = 50) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM paper_orders ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def order_stats(self) -> dict:
        """Lifetime totals from the order log."""
        with closing(self._connect()) as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) AS orders,
                    COALESCE(SUM(fee), 0) AS fees_paid,
                    COALESCE(SUM(realized_pnl), 0) AS realized_pnl,
                    COALESCE(SUM(CASE WHEN side = 'sell' THEN 1 END), 0) AS closed,
                    COALESCE(SUM(CASE WHEN side = 'sell' AND realized_pnl > 0 THEN 1 END), 0) AS wins
                FROM paper_orders
            """).fetchone()
        return dict(row)

    def equity_history(self, limit: int = 500) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT ts, equity FROM (SELECT ts, equity FROM paper_equity "
                "ORDER BY ts DESC LIMIT ?) ORDER BY ts",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def last_equity_ts(self) -> Optional[int]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT MAX(ts) AS ts FROM paper_equity").fetchone()
        return row["ts"]

    def record_equity(self, equity: float, ts: Optional[int] = None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO paper_equity (ts, equity) VALUES (?, ?)",
                (ts or _now_ms(), round(equity, 2)),
            )

    # ---- valuation -----------------------------------------------------

    def portfolio(self, prices: dict[str, float]) -> dict:
        """Account state valued at `prices` (symbol -> price).

        A position with no price is valued at its cost and flagged
        `price_available: False` so callers can warn instead of guessing.
        """
        account = self.account()
        stats = self.order_stats()

        positions = []
        positions_value = 0.0
        unrealized = 0.0
        for row in self.positions():
            price = prices.get(row["symbol"])
            mark = price if price is not None else row["avg_cost"]
            value = row["quantity"] * mark
            pnl = row["quantity"] * (mark - row["avg_cost"])
            positions_value += value
            unrealized += pnl
            positions.append({
                **row,
                "price": mark,
                "price_available": price is not None,
                "market_value": value,
                "unrealized_pnl": pnl,
                "unrealized_pnl_pct": (mark / row["avg_cost"] - 1) * 100 if row["avg_cost"] else None,
            })

        equity = account["cash"] + positions_value
        for position in positions:
            position["weight_pct"] = (
                position["market_value"] / equity * 100 if equity else 0.0
            )

        return {
            "account": account,
            "positions": positions,
            "totals": {
                "equity": equity,
                "cash": account["cash"],
                "positions_value": positions_value,
                "total_pnl": equity - account["starting_cash"],
                "total_return_pct": (equity / account["starting_cash"] - 1) * 100,
                "realized_pnl": stats["realized_pnl"],
                "unrealized_pnl": unrealized,
                "fees_paid": stats["fees_paid"],
            },
            "stats": {
                "orders": stats["orders"],
                "closed_trades": stats["closed"],
                "win_rate_pct": (stats["wins"] / stats["closed"] * 100) if stats["closed"] else None,
            },
            "fee_pct": self.fee_rate * 100,
            "all_prices_available": all(p["price_available"] for p in positions),
        }

    # ---- writes --------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        price: float,
        *,
        quantity: Optional[float] = None,
        notional: Optional[float] = None,
        percent: Optional[float] = None,
        source: str = "manual",
        rating: Optional[str] = None,
    ) -> dict:
        """Fill a market order at `price`.

        Size it with exactly one of: `quantity` (coins), `notional` (USD,
        fee included for buys), or `percent` (of cash for a buy, of the open
        position for a sell; 100 sells the whole position exactly).
        """
        if side not in ("buy", "sell"):
            raise OrderError("Side must be 'buy' or 'sell'.")
        if sum(value is not None for value in (quantity, notional, percent)) != 1:
            raise OrderError("Give exactly one of quantity, notional or percent.")
        if not price or price <= 0:
            raise OrderError("No valid price to fill at.")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")  # take the write lock before reading
            try:
                order = (
                    self._buy(conn, symbol, price, quantity, notional, percent, source, rating)
                    if side == "buy"
                    else self._sell(conn, symbol, price, quantity, notional, percent, source, rating)
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
            return order
        finally:
            conn.close()

    def _buy(self, conn, symbol, price, quantity, notional, percent, source, rating) -> dict:
        cash = conn.execute("SELECT cash FROM paper_account WHERE id = 1").fetchone()["cash"]

        if quantity is not None:
            qty = _floor_quantity(quantity)
        else:
            budget = notional if notional is not None else cash * percent / 100
            # The budget covers the fee too, so a 100% buy never overdraws.
            qty = _floor_quantity(budget / (price * (1 + self.fee_rate)))

        cost = qty * price
        fee = cost * self.fee_rate
        if qty <= 0 or cost < MIN_ORDER_USD:
            raise OrderError(f"Minimum order is ${MIN_ORDER_USD:,.0f}.")
        if cost + fee > cash + EPSILON:
            raise OrderError(
                f"Insufficient cash: need ${cost + fee:,.2f}, have ${cash:,.2f}."
            )

        held = conn.execute(
            "SELECT quantity, avg_cost FROM paper_positions WHERE symbol = ?", (symbol,)
        ).fetchone()
        old_qty, old_avg = (held["quantity"], held["avg_cost"]) if held else (0.0, 0.0)
        new_qty = old_qty + qty
        new_avg = (old_qty * old_avg + cost + fee) / new_qty  # buy fee is part of cost basis

        conn.execute("UPDATE paper_account SET cash = cash - ? WHERE id = 1", (cost + fee,))
        conn.execute(
            "INSERT INTO paper_positions (symbol, quantity, avg_cost) VALUES (?, ?, ?) "
            "ON CONFLICT(symbol) DO UPDATE SET quantity = excluded.quantity, "
            "avg_cost = excluded.avg_cost",
            (symbol, new_qty, new_avg),
        )
        return self._log(conn, symbol, "buy", qty, price, fee, cost, None, source, rating)

    def _sell(self, conn, symbol, price, quantity, notional, percent, source, rating) -> dict:
        held = conn.execute(
            "SELECT quantity, avg_cost FROM paper_positions WHERE symbol = ?", (symbol,)
        ).fetchone()
        if held is None:
            raise OrderError(f"You don't hold any {symbol}.")

        held_qty, avg_cost = held["quantity"], held["avg_cost"]
        sells_everything = False

        if percent is not None:
            sells_everything = percent >= 100
            qty = held_qty if sells_everything else _floor_quantity(held_qty * percent / 100)
        elif quantity is not None:
            qty = _floor_quantity(quantity)
        else:
            qty = _floor_quantity(notional / price)

        if qty > held_qty * (1 + EPSILON):
            raise OrderError(f"You only hold {held_qty:.8g} {symbol.split('/')[0]}.")
        qty = min(qty, held_qty)
        sells_everything = sells_everything or abs(qty - held_qty) <= EPSILON * max(held_qty, 1)

        proceeds = qty * price
        fee = proceeds * self.fee_rate
        # Closing a position is always allowed, so tiny leftovers can be cleared.
        if qty <= 0 or (proceeds < MIN_ORDER_USD and not sells_everything):
            raise OrderError(f"Minimum order is ${MIN_ORDER_USD:,.0f}.")

        realized = proceeds - fee - qty * avg_cost
        conn.execute("UPDATE paper_account SET cash = cash + ? WHERE id = 1", (proceeds - fee,))
        if sells_everything:
            conn.execute("DELETE FROM paper_positions WHERE symbol = ?", (symbol,))
        else:
            conn.execute(
                "UPDATE paper_positions SET quantity = ? WHERE symbol = ?",
                (held_qty - qty, symbol),
            )
        return self._log(conn, symbol, "sell", qty, price, fee, proceeds, realized, source, rating)

    @staticmethod
    def _log(conn, symbol, side, qty, price, fee, notional, realized, source, rating) -> dict:
        ts = _now_ms()
        cursor = conn.execute(
            "INSERT INTO paper_orders "
            "(ts, symbol, side, quantity, price, fee, notional, realized_pnl, source, signal_rating) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, symbol, side, qty, price, fee, notional, realized, source, rating),
        )
        return {
            "id": cursor.lastrowid, "ts": ts, "symbol": symbol, "side": side,
            "quantity": qty, "price": price, "fee": fee, "notional": notional,
            "realized_pnl": realized, "source": source, "signal_rating": rating,
        }

    def reset(self, starting_cash: Optional[float] = None) -> dict:
        cash = starting_cash if starting_cash is not None else self.default_starting_cash
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for table in ("paper_orders", "paper_positions", "paper_equity"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute(
                "UPDATE paper_account SET starting_cash = ?, cash = ?, reset_at = ? WHERE id = 1",
                (cash, cash, _now_ms()),
            )
            conn.execute("INSERT INTO paper_equity (ts, equity) VALUES (?, ?)", (_now_ms(), cash))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self.account()
