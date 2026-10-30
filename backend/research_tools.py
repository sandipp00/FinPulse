"""Read-only research tools shared by the rule-based and the local-AI assistant.

Each tool returns the same shape:

    {"tool", "args", "title", "facts": [{"label", "value", "kind"}], "sources": [...],
     "notes": [...], "error": None | str}

* `kind` is "data" (a figure as a source published it) or "calculated" (computed by
  FinPulse's tested functions from that data). Tools never interpret or predict.
* `sources` name where every figure came from, with its observation time.
* A tool that cannot answer sets `error` and returns no facts; it never fills in.

None of these tools changes anything: no orders, no writes.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import HTTPException

from backend import (
    asset_news, candles as candle_source, config, econ_calendar, eia, fred, fx, instruments, news, quant_api, signal_service,
)
from src.analytics import quant

LIVE_LABEL = {"real_time": "live", "stale": "stale (no recent update)", "historical": "end of day", "cached": "kept copy"}


def _fact(label: str, value, kind: str = "data") -> dict:
    return {"label": label, "value": value, "kind": kind}


def _result(tool: str, args: dict, title: str, facts=None, sources=None, notes=None, error=None) -> dict:
    return {"tool": tool, "args": args, "title": title, "facts": facts or [], "sources": sources or [],
            "notes": notes or [], "error": error}


def _pct(value: Optional[float], signed: bool = True) -> Optional[str]:
    if value is None:
        return None
    return f"{value:+.2f}%" if signed else f"{value:.2f}%"


def _price(value: Optional[float], currency: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = f"{value:,.4f}" if abs(value) < 10 else f"{value:,.2f}"
    return f"{text} {currency}" if currency else text


def _day(ts) -> Optional[str]:
    return None if ts is None else pd.Timestamp(ts).strftime("%Y-%m-%d")


def _meta_source(name: str, meta, url: Optional[str] = None) -> dict:
    meta = meta if isinstance(meta, dict) else (meta.model_dump(mode="json") if meta is not None else {})
    return {
        "name": name,
        "provider": meta.get("provider"),
        "as_of": meta.get("source_timestamp"),
        "retrieved_at": meta.get("retrieved_at"),
        "status": meta.get("status"),
        "url": url,
    }


# ---- prices -------------------------------------------------------------------

def quote(symbol: str) -> dict:
    """Latest observation for one instrument, with its freshness."""
    from backend import main  # the quotes route already assembles live and stored data

    args = {"symbol": symbol}
    records = {q.symbol: q for q in main.market_quotes()["quotes"]}
    record = records.get(symbol)
    if record is None or record.status == "unavailable":
        return _result("quote", args, f"Latest {symbol}", error=f"No price is available for {symbol}.")
    return _result(
        "quote", args, f"Latest {symbol}",
        facts=[
            _fact("Price", _price(record.price, record.currency)),
            _fact(f"Change ({record.change_window})", _pct(record.change_pct)),
            _fact("Freshness", LIVE_LABEL.get(record.status, record.status)),
        ],
        sources=[{"name": f"{symbol} quote", "provider": record.provider, "status": record.status,
                  "as_of": record.source_timestamp.isoformat() if record.source_timestamp else None,
                  "retrieved_at": record.retrieved_at.isoformat() if record.retrieved_at else None, "url": None}],
    )


async def _daily(symbol: str) -> tuple[pd.Series, dict]:
    history = await instruments.history(symbol=symbol, interval="1d", limit=1000, source="auto")
    closes = quant_api._closes(history)
    return closes, history


async def performance(symbol: str) -> dict:
    """Returns over 1 month and 1 year, annualized volatility and drawdowns, from daily closes."""
    args = {"symbol": symbol}
    catalogue = instruments.catalogue()
    if symbol not in catalogue:
        return _result("performance", args, f"{symbol} performance", error=f"{symbol} is not a supported instrument.")
    try:
        closes, history = await _daily(symbol)
    except HTTPException as exc:
        return _result("performance", args, f"{symbol} performance", error=str(exc.detail))
    if len(closes) < 2:
        return _result("performance", args, f"{symbol} performance", error="Not enough daily history.")

    last_day = closes.index[-1]

    def since(days: int) -> Optional[float]:
        window = closes[closes.index >= last_day - timedelta(days=days)]
        if window.index[0] > last_day - timedelta(days=days - 5):  # history does not reach back far enough
            return None
        return quant.total_return(window)

    periods = quant.periods_for(catalogue[symbol].asset_class)
    returns = quant.simple_returns(closes)
    year = returns[returns.index >= last_day - timedelta(days=365)]
    dd = quant.drawdown_stats(closes)
    current_dd = float(quant.drawdown_series(closes).iloc[-1])
    facts = [
        _fact("Last close", _price(float(closes.iloc[-1]), history["currency"])),
        _fact("Last close date", _day(last_day)),
        _fact("Return, last 30 days", _pct(_x100(since(30))), "calculated"),
        _fact("Return, last 365 days", _pct(_x100(since(365))), "calculated"),
        _fact("Volatility, last 365 days (annualized)", _pct(_x100(quant.annualized_volatility(year, periods)), False), "calculated"),
        _fact("Below its peak now", _pct(current_dd * 100), "calculated"),
        _fact("Deepest fall in the history shown", _pct(_x100(dd.max_drawdown)), "calculated"),
        _fact("That fall: peak → trough", f"{_day(dd.peak_date)} → {_day(dd.trough_date)}" if dd.peak_date else None, "calculated"),
        _fact("Recovered", (f"yes, {_day(dd.recovery_date)}" if dd.recovered else "not yet") if dd.peak_date else None, "calculated"),
    ]
    return _result(
        "performance", args, f"{symbol} performance",
        facts=[f for f in facts if f["value"] is not None],
        sources=[_meta_source(f"{symbol} daily closes ({history['source']})", history["meta"])],
        notes=[f"{len(closes)} daily closes, {_day(closes.index[0])} to {_day(last_day)}. "
               "Returns use closing prices only (no dividends or fees)."],
    )


def _x100(value: Optional[float]) -> Optional[float]:
    return None if value is None else value * 100


async def compare(symbol: str, benchmark: str) -> dict:
    args = {"symbol": symbol, "benchmark": benchmark}
    title = f"{symbol} relative to {benchmark}"
    try:
        body = await quant_api.relative(symbol=symbol, benchmark=benchmark, window=60)
    except HTTPException as exc:
        return _result("compare", args, title, error=str(exc.detail))
    m = body["metrics"]
    if m["beta"] is None and m["correlation"] is None:
        return _result("compare", args, title, error=body.get("note") or "Not enough shared history to compare.")
    facts = [
        _fact("Shared trading days", body["overlap"], "calculated"),
        _fact("Window", f"{body['start_date']} to {body['end_date']}", "calculated"),
        _fact(f"{symbol} return / yr", _pct(m["asset_return_pct"]), "calculated"),
        _fact(f"{benchmark} return / yr", _pct(m["benchmark_return_pct"]), "calculated"),
        _fact("Excess return / yr", _pct(m["excess_return_pct"]), "calculated"),
        _fact("Beta", None if m["beta"] is None else f"{m['beta']:.2f}", "calculated"),
        _fact("Correlation", None if m["correlation"] is None else f"{m['correlation']:.2f}", "calculated"),
        _fact("Tracking error / yr", _pct(m["tracking_error_pct"], False), "calculated"),
    ]
    if body["rolling"]:
        facts.append(_fact("Correlation, latest 60 days", f"{body['rolling'][-1]['correlation']:.2f}", "calculated"))
    return _result(
        "compare", args, title,
        facts=[f for f in facts if f["value"] is not None],
        sources=[_meta_source(f"{name} daily closes ({s['source']})", s["meta"]) for name, s in body["sources"].items()],
        notes=["Measured on the dates both have. Correlation describes past co-movement, not causation."],
    )


async def backtest(symbol: str) -> dict:
    args = {"symbol": symbol}
    title = f"{symbol} signal backtest (daily)"
    if symbol not in config.LIVE_SYMBOLS:
        return _result("backtest", args, title,
                       error=f"Signal backtests run on live crypto only ({', '.join(config.LIVE_SYMBOLS)}).")
    try:
        body = await signal_service.backtest_for(symbol, "1d", 0.001)
    except (candle_source.CandleSourceError, ValueError) as exc:
        return _result("backtest", args, title, error=str(exc))
    split = body.get("split") or {}
    facts = [
        _fact("Strategy return", _pct(body["strategy_return_pct"]), "calculated"),
        _fact("Buy & hold return", _pct(body["buy_hold_return_pct"]), "calculated"),
        _fact("50/200 trend rule return", _pct(body["baselines"]["trend"]["return_pct"]), "calculated"),
        _fact("Strategy max drawdown", _pct(body["strategy_max_drawdown_pct"]), "calculated"),
        _fact("Trades", body["trades"]["count"], "calculated"),
    ]
    if split:
        facts += [
            _fact("First 70%: strategy vs buy & hold",
                  f"{_pct(split['in_sample']['strategy_return_pct'])} vs {_pct(split['in_sample']['buy_hold_return_pct'])}", "calculated"),
            _fact("Latest 30%: strategy vs buy & hold",
                  f"{_pct(split['out_of_sample']['strategy_return_pct'])} vs {_pct(split['out_of_sample']['buy_hold_return_pct'])}", "calculated"),
        ]
    notes = ["0.1% fee per fill, fills at the next candle's open, long only. Past results do not predict future ones."]
    if body["sample_warning"]:
        notes.append("Fewer than 10 trades: too few to draw conclusions.")
    start = datetime.fromtimestamp(body["period"]["start"], tz=timezone.utc).date().isoformat()
    end = datetime.fromtimestamp(body["period"]["end"], tz=timezone.utc).date().isoformat()
    return _result("backtest", args, title, facts=facts, notes=notes,
                   sources=[{"name": f"{symbol} daily candles (Binance)", "provider": "binance",
                             "as_of": end, "detail": f"{start} to {end}", "url": None}])


# ---- other categories ------------------------------------------------------------

async def news_items(instrument: Optional[str] = None, topic: Optional[str] = None, limit: int = 5) -> dict:
    args = {"instrument": instrument, "topic": topic}
    title = "Latest headlines" + (f" on {instrument}" if instrument else "") + (f" ({topic})" if topic else "")
    asset = asset_news.find(instrument) if instrument else None
    if asset is not None and asset.yahoo_news:
        # The asset's own headline feed (as on its asset page), plus its tagged general news.
        items = (await asset_news.asset_headlines(asset))["items"]
    else:
        items, _ = await news.collect()
        if instrument:
            items = [i for i in items if instrument in i["instruments"]]
    if topic:
        items = [i for i in items if topic in i["topics"]]
    if not items:
        return _result("news", args, title, error="No matching headlines in the current feeds.")
    picked = items[:limit]
    return _result(
        "news", args, title,
        facts=[_fact(i["published_at"][:16].replace("T", " ") + " UTC", i["title"]) for i in picked],
        sources=[{"name": i["title"], "provider": i["source_name"], "as_of": i["published_at"], "url": i["url"]} for i in picked],
        notes=["Headlines as published; follow the links for the full articles."],
    )


async def calendar(days_ahead: int = 14) -> dict:
    args = {"days_ahead": days_ahead}
    body = await econ_calendar.build(0, days_ahead)
    upcoming = [e for e in body["events"] if e["status"] != "past"]
    if not upcoming:
        return _result("calendar", args, f"Next {days_ahead} days", error="No scheduled events in that window.",
                       notes=body["notes"])
    facts = [_fact(e["date"] + (f" {e['time_utc'][11:16]} UTC" if e["time_utc"] else ""),
                   e["title"] + (" (tentative)" if e["tentative"] else "")) for e in upcoming]
    return _result("calendar", args, f"Scheduled in the next {days_ahead} days", facts=facts,
                   sources=[{"name": e["title"], "provider": e["source"], "as_of": e["date"], "url": e["source_url"]}
                            for e in upcoming],
                   notes=body["notes"] + [body["consensus_note"]])


async def macro(series_id: str) -> dict:
    args = {"series_id": series_id}
    label = fred.LABELS.get(series_id, series_id)
    if series_id not in fred.SERIES:
        return _result("macro", args, label, error=f"{series_id} is not a tracked series.")
    if not fred.configured():
        return _result("macro", args, label, error="Macro data needs FRED_API_KEY on the server.")
    try:
        data = await fred.fetch_series(series_id)
    except fred.FredError as exc:
        return _result("macro", args, label, error=str(exc))
    latest, previous = fred.latest_two(data.observations)
    if not latest:
        return _result("macro", args, label, error="FRED returned no values.")
    units = data.info.get("units_short") or data.info.get("units")
    is_index = "index" in str(units).lower()
    change = latest["value"] - previous["value"] if previous else None
    facts = [
        _fact("Latest value", f"{latest['value']:,.2f}" + (" (index level)" if is_index else f" {units}")),
        _fact("Observation date", latest["date"]),
        _fact("Previous value", f"{previous['value']:,.2f} ({previous['date']})" if previous else None),
    ]
    if is_index:
        # For a price index, the meaningful figure is the change over 12 months (the inflation rate).
        year_earlier = (pd.Timestamp(latest["date"]) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
        base = next((o for o in data.observations if o["date"] == year_earlier and o["value"] is not None), None)
        if base:
            facts.append(_fact("12-month change", _pct((latest["value"] / base["value"] - 1) * 100), "calculated"))
    elif change is not None:
        facts.append(_fact("Change from previous", f"{change:+,.2f} {'percentage points' if '%' in str(units) else units}",
                           "calculated"))
    return _result("macro", args, label, facts=[f for f in facts if f["value"] is not None],
                   sources=[{"name": f"{data.info.get('title')} ({series_id})", "provider": "FRED", "as_of": latest["date"],
                             "url": f"https://fred.stlouisfed.org/series/{series_id}"}],
                   notes=[fred.NOTICE])


async def fx_rate(pair: str) -> dict:
    args = {"pair": pair}
    if pair not in fx.PAIRS:
        return _result("fx", args, pair, error=f"{pair} is not a tracked pair.")
    try:
        rates = await fx.euro_rates()
    except fx.FxError as exc:
        return _result("fx", args, pair, error=str(exc))
    series = fx.pair_series(rates, pair)
    if not series:
        return _result("fx", args, pair, error="No rates for this pair.")
    latest = series[-1]
    year_ago = [p for p in series if p["date"] <= (datetime.fromisoformat(latest["date"]) - timedelta(days=365)).date().isoformat()]
    base, quote_ccy = fx.PAIRS[pair]
    facts = [
        _fact("Rate", f"1 {base} = {latest['rate']:.4f} {quote_ccy}" if latest["rate"] < 10 else f"1 {base} = {latest['rate']:.2f} {quote_ccy}",
              "calculated" if fx.is_derived(pair) else "data"),
        _fact("Rate date", latest["date"]),
        _fact("Change over a year", _pct((latest["rate"] / year_ago[-1]["rate"] - 1) * 100) if year_ago else None, "calculated"),
    ]
    notes = ["ECB reference rate, published around 16:00 CET; not a live quote."]
    if fx.is_derived(pair):
        notes.append("Cross rate derived by FinPulse from two ECB euro rates; the ECB does not publish it.")
    return _result("fx", args, pair, facts=[f for f in facts if f["value"] is not None], notes=notes,
                   sources=[{"name": "ECB euro reference rates (via Frankfurter)", "provider": "ECB",
                             "as_of": latest["date"], "url": fx.ECB_URL}])


async def oil(series_id: str) -> dict:
    args = {"series_id": series_id}
    label = eia.SERIES.get(series_id, series_id)
    if series_id not in eia.SERIES:
        return _result("oil", args, label, error=f"{series_id} is not a tracked series.")
    if not eia.configured():
        return _result("oil", args, label, error="Oil prices need EIA_API_KEY on the server.")
    try:
        prices = await eia.oil_prices()
    except eia.EiaError as exc:
        return _result("oil", args, label, error=str(exc))
    latest, previous = eia.latest_two(prices.series.get(series_id, []))
    if not latest:
        return _result("oil", args, label, error="EIA returned no prices.")
    facts = [
        _fact("Spot price", f"{latest['value']:.2f} USD per barrel"),
        _fact("Price date", latest["date"]),
        _fact("Previous", f"{previous['value']:.2f} USD ({previous['date']})" if previous else None),
    ]
    return _result("oil", args, label, facts=[f for f in facts if f["value"] is not None],
                   notes=["EIA releases these daily prices weekly, so the newest can be several days old."],
                   sources=[{"name": f"{label} ({series_id})", "provider": "U.S. Energy Information Administration",
                             "as_of": latest["date"], "url": eia.SOURCE_URL}])


TOOLS = {
    "quote": quote, "performance": performance, "compare": compare, "backtest": backtest,
    "news": news_items, "calendar": calendar, "macro": macro, "fx": fx_rate, "oil": oil,
}
