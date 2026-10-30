import time

import pytest
from fastapi.testclient import TestClient

from backend import config, main, signal_service
from backend.live import feed
from src.portfolio.paper import OrderError, PaperBroker

FEE = 0.001


@pytest.fixture
def broker(tmp_path):
    return PaperBroker(tmp_path / "paper.db", user_id=1, fee_rate=FEE, starting_cash=100_000)


def cash(broker):
    return broker.account()["cash"]


# ---- broker: buying -----------------------------------------------------

def test_new_account_starts_with_the_configured_cash(broker):
    account = broker.account()

    assert account["cash"] == account["starting_cash"] == 100_000
    assert broker.positions() == []


def test_buy_by_notional_spends_exactly_that_much_including_fee(broker):
    order = broker.place_order("BTC/USDT", "buy", 50_000, notional=10_000)

    assert order["quantity"] == pytest.approx(10_000 / (50_000 * (1 + FEE)), abs=1e-8)
    assert order["fee"] == pytest.approx(order["notional"] * FEE)
    assert cash(broker) == pytest.approx(100_000 - 10_000, abs=0.01)


def test_buying_with_100_percent_never_overdraws(broker):
    broker.place_order("ETH/USDT", "buy", 2_345.67, percent=100)

    assert 0 <= cash(broker) < 1  # dust left by rounding the quantity down


def test_average_cost_blends_buys_and_includes_fees(broker):
    broker.place_order("BTC/USDT", "buy", 100, quantity=10)   # cost 1000, fee 1
    broker.place_order("BTC/USDT", "buy", 200, quantity=10)   # cost 2000, fee 2

    position = broker.positions()[0]
    assert position["quantity"] == 20
    assert position["avg_cost"] == pytest.approx((1000 + 1 + 2000 + 2) / 20)


# ---- broker: selling ----------------------------------------------------

def test_sell_realizes_pnl_after_both_fees(broker):
    broker.place_order("BTC/USDT", "buy", 100, quantity=10)   # basis 1001
    order = broker.place_order("BTC/USDT", "sell", 120, quantity=10)

    proceeds = 1200
    assert order["realized_pnl"] == pytest.approx(proceeds - proceeds * FEE - 1001)
    assert cash(broker) == pytest.approx(100_000 - 1001 + proceeds - proceeds * FEE)
    assert broker.positions() == []


def test_partial_sell_keeps_average_cost(broker):
    broker.place_order("BTC/USDT", "buy", 100, quantity=10)
    broker.place_order("BTC/USDT", "sell", 150, percent=40)

    position = broker.positions()[0]
    assert position["quantity"] == pytest.approx(6)
    assert position["avg_cost"] == pytest.approx(100.1)


def test_selling_100_percent_closes_the_position_exactly(broker):
    broker.place_order("SOL/USDT", "buy", 123.456789, notional=5_000)
    broker.place_order("SOL/USDT", "sell", 130, percent=100)

    assert broker.positions() == []


def test_losing_sale_counts_as_a_loss_in_stats(broker):
    broker.place_order("BTC/USDT", "buy", 100, quantity=10)
    broker.place_order("BTC/USDT", "sell", 90, percent=100)
    broker.place_order("ETH/USDT", "buy", 100, quantity=10)
    broker.place_order("ETH/USDT", "sell", 110, percent=100)

    stats = broker.portfolio({})["stats"]
    assert stats["closed_trades"] == 2
    assert stats["win_rate_pct"] == 50.0


# ---- broker: rejections never change anything -----------------------------

@pytest.mark.parametrize("kwargs, message", [
    ({"quantity": 1000}, "Insufficient cash"),
    ({"notional": 5}, "Minimum order"),
    ({}, "exactly one"),
    ({"quantity": 1, "notional": 100}, "exactly one"),
])
def test_rejected_buys_leave_the_account_untouched(broker, kwargs, message):
    with pytest.raises(OrderError, match=message):
        broker.place_order("BTC/USDT", "buy", 1_000, **kwargs)

    assert cash(broker) == 100_000
    assert broker.positions() == [] and broker.orders() == []


def test_cannot_sell_what_you_do_not_hold(broker):
    with pytest.raises(OrderError, match="don't hold"):
        broker.place_order("BTC/USDT", "sell", 100, percent=100)

    broker.place_order("BTC/USDT", "buy", 100, quantity=1)
    with pytest.raises(OrderError, match="only hold"):
        broker.place_order("BTC/USDT", "sell", 100, quantity=2)
    assert broker.positions()[0]["quantity"] == 1


def test_rejects_bad_side_and_price(broker):
    with pytest.raises(OrderError):
        broker.place_order("BTC/USDT", "short", 100, quantity=1)
    with pytest.raises(OrderError):
        broker.place_order("BTC/USDT", "buy", 0, quantity=1)
    with pytest.raises(OrderError):
        broker.place_order("BTC/USDT", "buy", -5, quantity=1)


def test_a_leftover_below_the_minimum_can_still_be_closed(broker):
    broker.place_order("SOL/USDT", "buy", 100, quantity=12)           # $1,200
    broker.place_order("SOL/USDT", "sell", 100, quantity=11.95)       # leaves 0.05 SOL = $5

    with pytest.raises(OrderError, match="Minimum order"):
        broker.place_order("SOL/USDT", "sell", 100, quantity=0.04)    # partial sell under $10

    broker.place_order("SOL/USDT", "sell", 100, percent=100)          # closing is always allowed
    assert broker.positions() == []


def test_selling_all_but_one_unit_of_dust_closes_the_position(broker):
    broker.place_order("XRP/USDT", "buy", 1.0, quantity=12)
    broker.place_order("XRP/USDT", "sell", 50, quantity=11.99999999)

    assert broker.positions() == []


# ---- broker: valuation, history, reset ------------------------------------

def test_portfolio_values_positions_at_market_prices(broker):
    broker.place_order("BTC/USDT", "buy", 100, quantity=10)

    result = broker.portfolio({"BTC/USDT": 110})

    position = result["positions"][0]
    assert position["market_value"] == pytest.approx(1100)
    assert position["unrealized_pnl"] == pytest.approx(10 * (110 - 100.1))
    totals = result["totals"]
    assert totals["equity"] == pytest.approx(cash(broker) + 1100)
    assert totals["total_pnl"] == pytest.approx(totals["equity"] - 100_000)
    assert totals["fees_paid"] == pytest.approx(1.0)
    assert result["all_prices_available"] is True


def test_position_without_a_price_is_valued_at_cost_and_flagged(broker):
    broker.place_order("BTC/USDT", "buy", 100, quantity=10)

    result = broker.portfolio({})

    assert result["all_prices_available"] is False
    assert result["positions"][0]["price_available"] is False
    assert result["positions"][0]["unrealized_pnl"] == 0


def test_equity_history_is_chronological_and_limited(broker):
    for index, value in enumerate([100_000, 100_500, 99_900]):
        broker.record_equity(value, ts=1_000 + index)

    assert [p["equity"] for p in broker.equity_history()] == [100_000, 100_500, 99_900]
    assert [p["ts"] for p in broker.equity_history(limit=2)] == [1_001, 1_002]


def test_reset_wipes_everything_and_can_change_starting_cash(broker):
    broker.place_order("BTC/USDT", "buy", 100, quantity=10)
    broker.record_equity(100_000)

    broker.reset(250_000)

    account = broker.account()
    assert account["cash"] == account["starting_cash"] == 250_000
    assert broker.positions() == [] and broker.orders() == []
    assert len(broker.equity_history()) == 1


# ---- API --------------------------------------------------------------------

def tick(symbol, price, age=0.0):
    return {"symbol": symbol, "price": price, "time": 0, "received_at": time.time() - age}


@pytest.fixture
def paper_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "finpulse.db")
    monkeypatch.setattr(main, "DATABASE_PATH", tmp_path / "finpulse.db")
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(config, "PAPER_STARTING_CASH", 100_000.0)
    monkeypatch.setattr(config, "PAPER_FEE_PCT", 0.1)
    monkeypatch.setattr(feed, "latest", {
        "BTC/USDT": tick("BTC/USDT", 50_000),
        "ETH/USDT": tick("ETH/USDT", 2_500),
    })
    with TestClient(main.app) as client:
        # Paper trading needs an account; registering also signs the client in.
        response = client.post(
            "/api/auth/register", json={"email": "trader@example.com", "password": "correct horse"}
        )
        assert response.status_code == 201
        yield client


def test_api_portfolio_starts_flat(paper_client):
    body = paper_client.get("/api/paper/portfolio").json()

    assert body["totals"]["equity"] == 100_000
    assert body["positions"] == []
    assert "Not investment advice" in body["disclaimer"]


def test_api_buy_fills_at_the_servers_live_price_not_the_clients(paper_client):
    response = paper_client.post("/api/paper/orders", json={
        "symbol": "BTC/USDT", "side": "buy", "notional_usd": 10_000, "price": 1,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["order"]["price"] == 50_000
    assert body["portfolio"]["positions"][0]["symbol"] == "BTC/USDT"
    assert body["portfolio"]["totals"]["cash"] == pytest.approx(90_000, abs=0.01)
    assert paper_client.get("/api/paper/orders").json()["orders"][0]["side"] == "buy"
    assert len(paper_client.get("/api/paper/equity").json()["points"]) >= 1


def test_api_values_open_positions_with_the_latest_price(paper_client, monkeypatch):
    paper_client.post("/api/paper/orders", json={"symbol": "BTC/USDT", "side": "buy", "percent": 50})
    feed.latest["BTC/USDT"] = tick("BTC/USDT", 55_000)

    totals = paper_client.get("/api/paper/portfolio").json()["totals"]

    assert totals["unrealized_pnl"] > 4_500  # ~10% on about $50k, less the fee
    assert totals["total_return_pct"] > 4


def test_api_refuses_to_trade_without_a_fresh_price(paper_client):
    buy = {"side": "buy", "percent": 10}

    feed.latest["BTC/USDT"] = tick("BTC/USDT", 50_000, age=120)   # stale
    stale = paper_client.post("/api/paper/orders", json={"symbol": "BTC/USDT", **buy})

    del feed.latest["ETH/USDT"]                                    # never received
    missing = paper_client.post("/api/paper/orders", json={"symbol": "ETH/USDT", **buy})

    assert stale.status_code == 503 and "old" in stale.json()["detail"]
    assert missing.status_code == 503 and "No live price" in missing.json()["detail"]
    assert paper_client.get("/api/paper/portfolio").json()["positions"] == []


def test_api_validation(paper_client):
    post = lambda body: paper_client.post("/api/paper/orders", json=body)  # noqa: E731

    assert post({"symbol": "ZZZ/USDT", "side": "buy", "percent": 10}).status_code == 404
    assert post({"symbol": "BTC/USDT", "side": "buy"}).status_code == 422
    assert post({"symbol": "BTC/USDT", "side": "buy", "percent": 10, "quantity": 1}).status_code == 422
    assert post({"symbol": "BTC/USDT", "side": "hold", "percent": 10}).status_code == 422
    assert post({"symbol": "BTC/USDT", "side": "buy", "percent": 150}).status_code == 422
    assert post({"symbol": "BTC/USDT", "side": "buy", "quantity": 1_000}).status_code == 400  # no cash
    assert post({"symbol": "BTC/USDT", "side": "sell", "percent": 100}).status_code == 400   # no position


def test_api_reset_restores_the_account(paper_client):
    paper_client.post("/api/paper/orders", json={"symbol": "BTC/USDT", "side": "buy", "percent": 30})

    body = paper_client.post("/api/paper/reset", json={"starting_cash": 5_000}).json()

    assert body["positions"] == []
    assert body["totals"]["equity"] == 5_000
    assert paper_client.post("/api/paper/reset", json={"starting_cash": 5}).status_code == 422


# ---- API: follow the signal --------------------------------------------------

def fake_signal(monkeypatch, rating):
    async def signal_for(symbol, interval):
        return {"symbol": symbol, "interval": interval, "rating": rating}

    monkeypatch.setattr(signal_service, "signal_for", signal_for)


def follow(client, **extra):
    return client.post("/api/paper/follow", json={"symbol": "BTC/USDT", "interval": "1d", **extra}).json()


def test_follow_buys_on_a_buy_rating_then_does_not_double_up(paper_client, monkeypatch):
    fake_signal(monkeypatch, "Strong Buy")

    first = follow(paper_client, percent=20)
    second = follow(paper_client, percent=20)

    assert first["action"] == "buy" and first["order"]["source"] == "signal"
    assert first["order"]["signal_rating"] == "Strong Buy"
    assert first["portfolio"]["totals"]["cash"] == pytest.approx(80_000, abs=0.01)
    assert second["action"] == "none" and "already holding" in second["reason"]


def test_follow_sells_everything_on_a_sell_rating(paper_client, monkeypatch):
    paper_client.post("/api/paper/orders", json={"symbol": "BTC/USDT", "side": "buy", "percent": 40})
    fake_signal(monkeypatch, "Sell")

    result = follow(paper_client)

    assert result["action"] == "sell"
    assert result["portfolio"]["positions"] == []


def test_follow_does_nothing_on_hold_or_when_there_is_nothing_to_sell(paper_client, monkeypatch):
    fake_signal(monkeypatch, "Hold")
    assert follow(paper_client)["action"] == "none"

    fake_signal(monkeypatch, "Strong Sell")
    flat = follow(paper_client)
    assert flat["action"] == "none" and "no position" in flat["reason"]
    assert paper_client.get("/api/paper/orders").json()["orders"] == []


# ---- per-user isolation -------------------------------------------------------

def test_two_brokers_for_different_users_never_see_each_other(tmp_path):
    path = tmp_path / "shared.db"
    alice = PaperBroker(path, user_id=1, fee_rate=FEE, starting_cash=100_000)
    bob = PaperBroker(path, user_id=2, fee_rate=FEE, starting_cash=50_000)

    alice.place_order("BTC/USDT", "buy", 100, quantity=10)
    alice.record_equity(99_000)

    assert [p["symbol"] for p in alice.positions()] == ["BTC/USDT"]
    assert bob.positions() == [] and bob.orders() == [] and bob.equity_history() == []
    assert bob.account()["cash"] == 50_000
    assert alice.account()["cash"] < 100_000

    bob.reset()
    assert [p["symbol"] for p in alice.positions()] == ["BTC/USDT"]  # untouched by Bob's reset
    with pytest.raises(OrderError):
        bob.place_order("BTC/USDT", "sell", 100, percent=100)  # can't sell Alice's coins


def test_single_account_tables_are_set_aside_not_deleted(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE paper_account (id INTEGER PRIMARY KEY, starting_cash REAL, cash REAL,
                                        created_at INTEGER, reset_at INTEGER);
            INSERT INTO paper_account VALUES (1, 100000, 88000, 0, NULL);
            CREATE TABLE paper_positions (symbol TEXT PRIMARY KEY, quantity REAL, avg_cost REAL);
            CREATE TABLE paper_orders (id INTEGER PRIMARY KEY, ts INTEGER, symbol TEXT, side TEXT,
                quantity REAL, price REAL, fee REAL, notional REAL, realized_pnl REAL, source TEXT,
                signal_rating TEXT);
            CREATE TABLE paper_equity (ts INTEGER PRIMARY KEY, equity REAL);
        """)

    broker = PaperBroker(path, user_id=7, fee_rate=FEE, starting_cash=100_000)

    assert broker.account()["cash"] == 100_000          # fresh per-user account
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT cash FROM legacy_paper_account").fetchone()[0] == 88_000
    # Opening it again must not migrate twice or fail.
    assert PaperBroker(path, user_id=7, fee_rate=FEE).account()["cash"] == 100_000


# ---- API: authentication and isolation ---------------------------------------

def test_paper_endpoints_require_sign_in(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "finpulse.db")
    monkeypatch.setattr(main, "DATABASE_PATH", tmp_path / "finpulse.db")
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    monkeypatch.setattr(feed, "latest", {"BTC/USDT": tick("BTC/USDT", 50_000)})

    with TestClient(main.app) as anonymous:
        assert anonymous.get("/api/paper/portfolio").status_code == 401
        assert anonymous.get("/api/paper/orders").status_code == 401
        assert anonymous.get("/api/paper/equity").status_code == 401
        order = {"symbol": "BTC/USDT", "side": "buy", "percent": 10}
        assert anonymous.post("/api/paper/orders", json=order).status_code == 401
        assert anonymous.post("/api/paper/follow", json={"symbol": "BTC/USDT"}).status_code == 401
        assert anonymous.post("/api/paper/reset", json={}).status_code == 401
        # Market data stays public.
        assert anonymous.get("/api/live/status").status_code == 200


def test_users_have_separate_paper_accounts_over_http(paper_client):
    paper_client.post("/api/paper/orders", json={"symbol": "BTC/USDT", "side": "buy", "percent": 30})

    with TestClient(main.app) as other:
        other.post("/api/auth/register", json={"email": "other@example.com", "password": "another pass"})
        theirs = other.get("/api/paper/portfolio").json()
        assert theirs["positions"] == [] and theirs["totals"]["equity"] == 100_000
        other.post("/api/paper/reset", json={"starting_cash": 5_000})

    mine = paper_client.get("/api/paper/portfolio").json()
    assert [p["symbol"] for p in mine["positions"]] == ["BTC/USDT"]
    assert len(paper_client.get("/api/paper/orders").json()["orders"]) == 1
