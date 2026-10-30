"""The equity updater: dry run by default, append-only, adjustment check, backups.

Runs against a temporary database with the Yahoo download replaced by a fake.
"""
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.data import update_equities as up
from src.data.schema import MARKET_PRICES_DDL

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)

STORED = [
    ("2026-10-12T00:00:00Z", "AAPL", "stock", 200, 205, 198, 204.0, 1000),
    ("2026-10-13T00:00:00Z", "AAPL", "stock", 204, 210, 203, 209.0, 1100),
    ("2026-10-14T00:00:00Z", "AAPL", "stock", 209, 211, 201, 202.0, 900),
    ("2026-10-13T00:00:00Z", "^NSEI", "index", 22000, 22100, 21900, 22050.0, 5),
    ("2026-10-14T00:00:00Z", "^NSEI", "index", 22050, 22700, 22000, 22622.7, 6),
    ("2026-10-14T00:00:00Z", "BTC/USDT", "crypto", 81000, 83000, 80500, 82268.0, 12),
]


def frame(symbol, days_closes):
    """What src.data.stock_data.fetch_stock_data returns: one row per trading day."""
    return pd.DataFrame([
        {"timestamp": pd.Timestamp(day, tz="UTC"), "symbol": symbol,
         "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 100}
        for day, c in days_closes
    ])


GOOD = {
    "AAPL": [("2026-10-13", 209.0), ("2026-10-14", 202.0), ("2026-10-15", 205.0), ("2026-10-16", 207.5),
             ("2026-10-30", 210.0)],  # today: unfinished, must be ignored
    "^NSEI": [("2026-10-14", 22622.7), ("2026-10-15", 22700.1)],
    "^GSPC": [("2023-01-03", 3824.1), ("2023-01-04", 3852.9)],
}


def fake_fetch(data):
    calls = []

    def fetch(symbol, start):
        calls.append((symbol, start))
        if isinstance(data.get(symbol), Exception):
            raise data[symbol]
        return frame(symbol, data.get(symbol, []))

    fetch.calls = calls
    return fetch


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "finpulse.db"
    with sqlite3.connect(path) as conn:
        conn.execute(MARKET_PRICES_DDL)
        conn.executemany("INSERT INTO market_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)", STORED)
    return path


def rows(path, symbol=None):
    with sqlite3.connect(path) as conn:
        q = "SELECT timestamp, symbol, close, volume FROM market_prices"
        return conn.execute(q + (" WHERE symbol = ?" if symbol else "") + " ORDER BY symbol, timestamp",
                            (symbol,) if symbol else ()).fetchall()


def run(db, tmp_path, data, *flags):
    fetch = fake_fetch(data)
    code = up.main(["--db", str(db), "--backup-dir", str(tmp_path / "backups"), *flags], fetch=fetch, now=NOW)
    return code, fetch


def test_dry_run_reports_and_writes_nothing(db, tmp_path, capsys):
    before = rows(db)

    code, fetch = run(db, tmp_path, GOOD)

    out = capsys.readouterr().out
    assert code == 0
    assert rows(db) == before
    assert not (tmp_path / "backups").exists()
    assert "AAPL (stock): ready" in out
    assert "would add 2 bar(s): 2026-10-15 to 2026-10-16" in out
    assert "ignored 1 bar(s) dated today or later" in out
    assert "^GSPC (index): ready" in out
    assert "nothing stored (new symbol)" in out
    assert "Dry run: nothing was written. 5 bar(s) would be added." in out
    # Stored symbols are re-downloaded from 10 days before their newest bar; new ones from 2023.
    assert ("AAPL", "2026-10-04") in fetch.calls
    assert ("^GSPC", "2023-01-01") in fetch.calls


def test_apply_backs_up_then_appends_without_changing_existing_rows(db, tmp_path, capsys):
    before = rows(db)

    code, _ = run(db, tmp_path, GOOD, "--apply")

    out = capsys.readouterr().out
    assert code == 0
    after = rows(db)
    assert set(before) <= set(after)  # every original row is still there, unchanged
    assert len(after) == len(before) + 5
    assert [r[0][:10] for r in rows(db, "AAPL")] == ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]
    assert rows(db, "^GSPC")[0][0] == "2023-01-03T00:00:00Z"
    assert "Inserted 5 new bar(s)" in out

    (backup,) = (tmp_path / "backups").iterdir()
    assert backup.name == "finpulse-20261030-120000.db"
    assert rows(backup) == before  # the backup is the database as it was before the write


def test_a_changed_adjustment_basis_skips_the_symbol(db, tmp_path, capsys):
    shifted = {**GOOD, "AAPL": [(d, c * 0.99) for d, c in GOOD["AAPL"]]}  # e.g. after a dividend

    run(db, tmp_path, shifted, "--apply")

    out = capsys.readouterr().out
    assert "AAPL (stock): skipped" in out
    assert "mismatch 2026-10-13: stored 209.0000, Yahoo now 206.9100" in out
    assert len(rows(db, "AAPL")) == 3  # nothing added for AAPL
    assert len(rows(db, "^NSEI")) == 3  # the other symbols still update


def test_rounding_level_differences_still_match(db, tmp_path, capsys):
    tiny = {**GOOD, "AAPL": [(d, c * 1.0001) for d, c in GOOD["AAPL"]]}
    run(db, tmp_path, tiny)
    assert "AAPL (stock): ready" in capsys.readouterr().out


def test_no_overlap_means_no_write(db, tmp_path, capsys):
    gap = {**GOOD, "AAPL": [("2026-10-15", 205.0)]}
    run(db, tmp_path, gap, "--apply")
    out = capsys.readouterr().out
    assert "AAPL (stock): skipped" in out
    assert "No overlapping days" in out
    assert len(rows(db, "AAPL")) == 3


def test_download_and_validation_errors_are_reported_not_written(db, tmp_path, capsys):
    bad = {
        **GOOD,
        "AAPL": ValueError("No stock data returned for AAPL"),
        "^NSEI": [("2026-10-14", 22622.7), ("2026-10-15", -1.0)],  # negative price fails validation
    }
    code, _ = run(db, tmp_path, bad, "--apply")

    out = capsys.readouterr().out
    assert code == 0
    assert "AAPL (stock): error" in out and "No stock data returned" in out
    assert "^NSEI (index): error" in out and "non-positive price" in out
    assert len(rows(db, "AAPL")) == 3 and len(rows(db, "^NSEI")) == 2
    assert len(rows(db, "^GSPC")) == 2  # the healthy symbol still updates


def test_nothing_to_add_does_not_touch_the_database(db, tmp_path, capsys):
    current = {"AAPL": GOOD["AAPL"][:2], "^NSEI": GOOD["^NSEI"][:1], "^GSPC": []}
    current["^GSPC"] = ValueError("No stock data returned for ^GSPC")
    run(db, tmp_path, current, "--apply")

    out = capsys.readouterr().out
    assert "AAPL (stock): up to date" in out
    assert "Nothing to add; the database was not touched." in out
    assert not (tmp_path / "backups").exists()


def test_crypto_rows_are_never_touched(db, tmp_path):
    run(db, tmp_path, GOOD, "--apply")
    assert rows(db, "BTC/USDT") == [("2026-10-14T00:00:00Z", "BTC/USDT", 82268.0, 12.0)]


def test_a_missing_database_is_reported(tmp_path, capsys):
    code = up.main(["--db", str(tmp_path / "nope.db")], fetch=fake_fetch(GOOD), now=NOW)
    assert code == 1
    assert "Database not found" in capsys.readouterr().out


def test_backup_matches_the_source_row_for_row(db, tmp_path):
    copy = up.backup(db, tmp_path / "b", NOW)
    assert rows(copy) == rows(db)


# ---- --replace-newest ------------------------------------------------------------

AAPL_HISTORY = [("2026-10-08", 340.42), ("2026-10-09", 336.64), ("2026-10-12", 340.97), ("2026-10-13", 341.27)]
PARTIAL = ("2026-10-14T00:00:00Z", "AAPL", "stock", 341.0, 346.0, 340.5, 345.785, 6_475_112)
FINAL_14TH = 342.96


@pytest.fixture
def partial_db(tmp_path):
    """AAPL whose newest stored bar was saved mid-session; older days are final."""
    path = tmp_path / "partial.db"
    with sqlite3.connect(path) as conn:
        conn.execute(MARKET_PRICES_DDL)
        conn.executemany("INSERT INTO market_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            (f"{d}T00:00:00Z", "AAPL", "stock", c, c * 1.01, c * 0.99, c, 100) for d, c in AAPL_HISTORY
        ] + [PARTIAL])
    return path


def yahoo_with_final_14th(newer=(("2026-10-15", 344.1),)):
    return {"AAPL": [*AAPL_HISTORY, ("2026-10-14", FINAL_14TH), *newer], "^NSEI": [], "^GSPC": []}


def test_without_the_flag_a_partial_newest_bar_is_skipped_with_a_hint(partial_db, tmp_path, capsys):
    run(partial_db, tmp_path, yahoo_with_final_14th(), "--apply")

    out = capsys.readouterr().out
    assert "AAPL (stock): skipped" in out
    assert "--replace-newest AAPL would replace it" in out
    assert rows(partial_db, "AAPL")[-1] == ("2026-10-14T00:00:00Z", "AAPL", 345.785, 6_475_112)


def test_the_flag_replaces_only_the_newest_bar_then_appends(partial_db, tmp_path, capsys):
    older = rows(partial_db, "AAPL")[:-1]

    code, _ = run(partial_db, tmp_path, yahoo_with_final_14th(), "--apply", "--replace-newest", "AAPL")

    out = capsys.readouterr().out
    assert code == 0
    assert "replace 2026-10-14: close 345.7850 -> 342.9600, volume 6,475,112 -> 100" in out
    assert "replaced the newest stored bar of AAPL" in out
    after = rows(partial_db, "AAPL")
    assert after[:4] == older  # older rows untouched
    assert after[4] == ("2026-10-14T00:00:00Z", "AAPL", FINAL_14TH, 100)
    assert after[5][0] == "2026-10-15T00:00:00Z"

    (backup,) = (tmp_path / "backups").iterdir()
    assert rows(backup, "AAPL")[-1] == ("2026-10-14T00:00:00Z", "AAPL", 345.785, 6_475_112)


def test_the_flag_is_shown_in_a_dry_run_without_writing(partial_db, tmp_path, capsys):
    before = rows(partial_db)
    run(partial_db, tmp_path, yahoo_with_final_14th(), "--replace-newest", "AAPL")
    out = capsys.readouterr().out
    assert "1 bar(s) would be added and 1 replaced" in out
    assert rows(partial_db) == before


def test_the_flag_never_replaces_when_older_days_differ_too(partial_db, tmp_path, capsys):
    data = yahoo_with_final_14th()
    data["AAPL"] = [(d, c * 0.99) if d == "2026-10-12" else (d, c) for d, c in data["AAPL"]]

    run(partial_db, tmp_path, data, "--apply", "--replace-newest", "AAPL")

    out = capsys.readouterr().out
    assert "AAPL (stock): skipped" in out
    assert "not only the newest bar differs" in out
    assert rows(partial_db, "AAPL")[-1][2] == 345.785


def test_the_flag_needs_enough_matching_older_days(tmp_path, capsys):
    path = tmp_path / "short.db"
    with sqlite3.connect(path) as conn:
        conn.execute(MARKET_PRICES_DDL)
        conn.executemany("INSERT INTO market_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            ("2026-10-13T00:00:00Z", "AAPL", "stock", 341.27, 343, 339, 341.27, 100), PARTIAL])

    run(path, tmp_path, yahoo_with_final_14th(), "--apply", "--replace-newest", "AAPL")

    out = capsys.readouterr().out
    assert "fewer than 3 older days match" in out
    assert rows(path, "AAPL")[-1][2] == 345.785


def test_a_replacement_is_refused_if_the_row_changed_since_planning(partial_db):
    conn = sqlite3.connect(f"file:{partial_db.as_posix()}?mode=ro", uri=True)
    plan = up.plan_symbol(conn, "AAPL", "stock", fake_fetch(yahoo_with_final_14th()), NOW.date(), replace_newest=True)
    conn.close()
    with sqlite3.connect(partial_db) as conn:
        conn.execute("UPDATE market_prices SET close = 1 WHERE timestamp = '2026-10-14T00:00:00Z'")

    conn = sqlite3.connect(partial_db)
    with pytest.raises(RuntimeError, match="expected to replace 1 row, matched 0"):
        up.apply(conn, [plan])
    conn.close()
    assert len(rows(partial_db, "AAPL")) == 5  # the transaction rolled back: nothing appended either


def test_an_unknown_replace_symbol_stops_before_anything(db, tmp_path, capsys):
    code, fetch = run(db, tmp_path, GOOD, "--apply", "--replace-newest", "TSLA")
    assert code == 2
    assert "unknown symbol(s) TSLA" in capsys.readouterr().out
    assert fetch.calls == []


# ---- gold and silver futures -------------------------------------------------------

def test_the_newest_futures_bar_is_held_back(db, tmp_path, capsys):
    metals = {**GOOD, "GC=F": [("2026-10-27", 4074.6), ("2026-10-28", 4051.6), ("2026-10-29", 4011.2)]}

    run(db, tmp_path, metals, "--apply")

    out = capsys.readouterr().out
    assert "GC=F (commodity): ready" in out
    assert "ignored 1 bar(s) dated today or later, or the newest futures bar" in out
    # 2026-10-29 is before today, but it is the newest bar, which Yahoo may still be updating.
    assert [r[0][:10] for r in rows(db, "GC=F")] == ["2026-10-27", "2026-10-28"]
    assert len(rows(db, "AAPL")) == 5  # stocks still take their newest completed bar


def test_single_price_bars_are_reported_and_stored(db, tmp_path, capsys):
    thin = pd.DataFrame([
        {"timestamp": pd.Timestamp(day, tz="UTC"), "symbol": "SI=F", "open": o, "high": h, "low": low, "close": c,
         "volume": v}
        for day, o, h, low, c, v in [("2026-10-23", 53.71, 53.71, 53.71, 53.71, 15),
                                     ("2026-10-26", 54.10, 54.10, 54.10, 54.10, 128),
                                     ("2026-10-27", 53.73, 54.29, 53.65, 54.29, 229),
                                     ("2026-10-28", 53.92, 53.92, 53.40, 53.46, 331)]
    ])
    base = fake_fetch(GOOD)

    def fetch(symbol, start):
        return thin.copy() if symbol == "SI=F" else base(symbol, start)

    up.main(["--db", str(db), "--backup-dir", str(tmp_path / "backups"), "--apply"], fetch=fetch, now=NOW)

    out = capsys.readouterr().out
    assert "would add 3 bar(s): 2026-10-23 to 2026-10-27" in out
    assert "note: 2 of them have one price for open, high, low and close" in out
    assert len(rows(db, "SI=F")) == 3


# ---- crypto daily bars (Binance) ---------------------------------------------------

def test_crypto_daily_bars_are_appended_after_the_check(db, tmp_path, capsys):
    crypto = {**GOOD, "BTC/USDT": [("2026-10-13", 81500.0), ("2026-10-14", 82268.0), ("2026-10-15", 83010.5),
                                   ("2026-10-30", 84000.0)]}  # today: unfinished, ignored

    run(db, tmp_path, crypto, "--apply")

    out = capsys.readouterr().out
    assert "BTC/USDT (crypto): ready" in out
    assert [r[0][:10] for r in rows(db, "BTC/USDT")] == ["2026-10-14", "2026-10-15"]


def test_a_partial_crypto_bar_names_binance_and_can_be_replaced(db, tmp_path, capsys):
    crypto = {**GOOD, "BTC/USDT": [("2026-10-14", 81682.01), ("2026-10-15", 83010.5)]}

    run(db, tmp_path, crypto, "--apply")
    out = capsys.readouterr().out
    assert "mismatch 2026-10-14: stored 82268.0000, Binance now 81682.0100" in out
    assert "Binance's prices for stored days have changed" in out
    assert len(rows(db, "BTC/USDT")) == 1


def test_binance_daily_klines_are_paged_into_one_frame(monkeypatch):
    import httpx

    day = 86_400_000
    start = 1_791_590_400_000  # 2026-10-10
    pages = [[[start + i * day, "1", "2", "0.5", str(100 + i), "7", 0, "0", 0, "0", "0", "0"]
              for i in range(n)] for n in (up.BINANCE_PAGE, 3)]
    calls = []

    def fake_get(url, timeout, params):
        calls.append(params["startTime"])
        return httpx.Response(200, json=pages[len(calls) - 1], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    frame = up.fetch_binance_daily("BTC/USDT", "2026-10-10")

    assert len(frame) == up.BINANCE_PAGE + 3
    assert calls == [start, start + (up.BINANCE_PAGE - 1) * day + 1]
    assert frame["timestamp"].iloc[0] == pd.Timestamp("2026-10-10", tz="UTC")
    assert frame["close"].iloc[1] == 101.0 and frame["symbol"].iloc[0] == "BTC/USDT"
