"""The rule-based research assistant: plain-language questions answered with tools.

No AI model is involved. The question is matched against known instrument names
and question types; the matching tools in backend/research_tools.py run; the
answer is assembled from their facts with fixed templates. It cannot invent a
number or a source, and it says so when a question is outside what it handles.
"""
import re
from typing import Optional

from backend import research_tools as tools

# Alias -> instrument symbol. Longer aliases are matched first.
INSTRUMENT_ALIASES = {
    "AAPL": ["aapl", "apple"],
    "^GSPC": ["s&p 500", "s&p500", "s&p", "sp500", "sp 500", "spx", "gspc", "^gspc"],
    "^NSEI": ["nifty 50", "nifty", "nsei", "^nsei"],
    "BTC/USDT": ["bitcoin", "btc"],
    "ETH/USDT": ["ethereum", "ether", "eth"],
    "SOL/USDT": ["solana", "sol"],
    "BNB/USDT": ["bnb", "binance coin"],
    "XRP/USDT": ["xrp", "ripple"],
}
FX_ALIASES = {
    "USD/INR": ["usd/inr", "usdinr", "usd inr", "rupee", "inr"],
    "EUR/USD": ["eur/usd", "eurusd", "euro"],
    "GBP/USD": ["gbp/usd", "gbpusd", "pound", "sterling", "gbp"],
    "USD/JPY": ["usd/jpy", "usdjpy", "yen", "jpy"],
    "EUR/INR": ["eur/inr", "eurinr"],
    "EUR/GBP": ["eur/gbp", "eurgbp"],
    "EUR/JPY": ["eur/jpy", "eurjpy"],
}
OIL_ALIASES = {"RBRTE": ["brent"], "RWTC": ["wti"]}  # a bare "oil" or "crude" means both
MACRO_ALIASES = {
    "PCEPILFE": ["core pce", "pce"],
    "CPIAUCSL": ["cpi", "inflation", "consumer price"],
    "FEDFUNDS": ["fed funds", "federal funds", "interest rate", "policy rate", "fed rate"],
    "DGS10": ["10-year", "10 year", "ten-year", "10y"],
    "DGS2": ["2-year", "2 year", "two-year", "2y"],
    "GDPC1": ["gdp", "real gdp"],
    "UNRATE": ["unemployment", "jobless"],
    "PAYEMS": ["payrolls", "payroll", "jobs report"],
}
INTENT_WORDS = {
    "calendar": ["upcoming", "calendar", "this week", "next week", "schedule", "when is", "when's", "events"],
    "news": ["news", "headline", "headlines", "what happened", "latest on"],
    "compare": ["compare", " vs", " vs.", "versus", "against", "relative to", "beta", "correlat"],
    "backtest": ["backtest", "strategy", "signal", "signals"],
    "risk": ["risk", "risky", "volatil", "drawdown", "how far", "fallen", "crash"],
    "performance": ["perform", "return", "how has", "how did", "up or down", "gained", "lost"],
}

EXAMPLES = [
    "How has AAPL performed?",
    "Compare Bitcoin with the S&P 500",
    "How risky is ETH?",
    "Latest news on Bitcoin",
    "What's on the calendar this week?",
    "What is US inflation?",
    "USD/INR rate",
    "Brent oil price",
    "Backtest SOL",
]


def _find(text: str, aliases: dict[str, list[str]]) -> list[str]:
    """Matches in order of first appearance; each alias must be a whole word or phrase.

    A match inside a longer match is dropped, so "eur/inr" does not also count as "inr".
    """
    hits = []
    for key, names in aliases.items():
        for name in sorted(names, key=len, reverse=True):
            match = re.search(rf"(?<![\w^]){re.escape(name)}(?![\w])", text)
            if match:
                hits.append((match.start(), match.end(), key))
                break
    kept = [h for h in hits if not any(o is not h and o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0])
                                       for o in hits)]
    return [key for _, _, key in sorted(kept)]


NEWS_TOPICS = {"crypto": ["crypto"], "rates": ["fed", "rates", "central bank", "ecb"], "macro": ["macro", "economy", "economic"],
               "filings": ["filing", "filings", "sec "]}


def _default_benchmark(symbol: str) -> str:
    if symbol.endswith("/USDT") and symbol != "BTC/USDT":
        return "BTC/USDT"
    return "^GSPC" if symbol != "^GSPC" else "BTC/USDT"


def parse(question: str) -> dict:
    text = " " + question.lower().strip() + " "
    intents = [name for name, words in INTENT_WORDS.items() if any(w in text for w in words)]
    return {
        "instruments": _find(text, INSTRUMENT_ALIASES),
        "fx": _find(text, FX_ALIASES),
        "oil": _find(text, OIL_ALIASES),
        "macro": _find(text, MACRO_ALIASES),
        "intents": intents,
        "text": text,
    }


def plan(parsed: dict) -> tuple[list[tuple[str, dict]], str]:
    """(tool calls to make, a sentence saying what was understood)."""
    symbols, intents = parsed["instruments"], parsed["intents"]

    if "calendar" in intents:
        return [("calendar", {"days_ahead": 14})], "Scheduled data releases and central-bank meetings, next 14 days."
    if "news" in intents:
        if symbols:
            return [("news", {"instrument": s}) for s in symbols[:2]], f"Latest headlines on {', '.join(symbols[:2])}."
        topic = next((t for t, words in NEWS_TOPICS.items() if any(w in parsed["text"] for w in words)), None)
        return [("news", {"topic": topic})], f"Latest {topic + ' ' if topic else ''}headlines from all sources."
    if parsed["macro"]:
        ids = parsed["macro"][:3]
        return [("macro", {"series_id": i}) for i in ids], f"Latest US macro figures: {', '.join(ids)}."
    if parsed["fx"]:
        return [("fx", {"pair": p}) for p in parsed["fx"][:2]], f"ECB reference rates for {', '.join(parsed['fx'][:2])}."
    oil = parsed["oil"] or (["RWTC", "RBRTE"] if re.search(r"(?<![\w])(oil|crude)(?![\w])", parsed["text"]) else [])
    if oil:
        return [("oil", {"series_id": s}) for s in oil], "Crude oil spot prices from the EIA."
    if not symbols:
        return [], ""

    if "compare" in intents or len(symbols) >= 2:
        benchmark = symbols[1] if len(symbols) >= 2 else _default_benchmark(symbols[0])
        return [("compare", {"symbol": symbols[0], "benchmark": benchmark})], \
            f"{symbols[0]} measured against {benchmark} on their shared daily history."
    symbol = symbols[0]
    if "backtest" in intents:
        return [("backtest", {"symbol": symbol})], f"The six-rule signal backtest for {symbol} on daily candles."
    if "risk" in intents:
        return [("performance", {"symbol": symbol})], f"Volatility and drawdowns for {symbol}."
    return [("quote", {"symbol": symbol}), ("performance", {"symbol": symbol})], \
        f"Latest price and recent performance for {symbol}."


def _value(result: dict, label: str) -> Optional[str]:
    return next((f["value"] for f in result["facts"] if f["label"] == label), None)


def summarize(result: dict) -> list[dict]:
    """Template sentences from one tool result; every figure is copied from its facts."""
    if result["error"]:
        return [{"text": f"{result['title']}: {result['error']}", "kind": "unavailable"}]
    tool, a = result["tool"], result["args"]
    lines = []
    if tool == "quote":
        lines.append(f"{a['symbol']} is at {_value(result, 'Price')} ({_value(result, 'Freshness')}).")
    elif tool == "performance":
        year, month = _value(result, "Return, last 365 days"), _value(result, "Return, last 30 days")
        if year:
            lines.append(f"Over the last 365 days {a['symbol']} returned {year}" + (f"; over 30 days, {month}." if month else "."))
        vol, now = _value(result, "Volatility, last 365 days (annualized)"), _value(result, "Below its peak now")
        if vol:
            lines.append(f"Its annualized volatility over that year was {vol}; its current distance from its peak is {now}.")
        deepest = _value(result, "Deepest fall in the history shown")
        if deepest:
            lines.append(f"The deepest fall in the data was {deepest} ({_value(result, 'That fall: peak → trough')}); "
                         f"recovered: {_value(result, 'Recovered')}.")
    elif tool == "compare":
        lines.append(f"Over {_value(result, 'Shared trading days')} shared days ({_value(result, 'Window')}), {a['symbol']} returned "
                     f"{_value(result, a['symbol'] + ' return / yr')} a year against {_value(result, a['benchmark'] + ' return / yr')} "
                     f"for {a['benchmark']}.")
        lines.append(f"Beta {_value(result, 'Beta')}, correlation {_value(result, 'Correlation')}"
                     + (f" (latest 60 days: {_value(result, 'Correlation, latest 60 days')})" if _value(result, "Correlation, latest 60 days") else "")
                     + ".")
    elif tool == "backtest":
        lines.append(f"The signal strategy returned {_value(result, 'Strategy return')} against buy & hold's "
                     f"{_value(result, 'Buy & hold return')} ({_value(result, 'Trades')} trades).")
        if _value(result, "Latest 30%: strategy vs buy & hold"):
            lines.append(f"First 70% of the window: {_value(result, 'First 70%: strategy vs buy & hold')}; "
                         f"latest 30%: {_value(result, 'Latest 30%: strategy vs buy & hold')}.")
    elif tool == "macro":
        if _value(result, "12-month change"):
            lines.append(f"{result['title']} changed by {_value(result, '12-month change')} in the 12 months to "
                         f"{_value(result, 'Observation date')} (index level {_value(result, 'Latest value').split(' ')[0]}).")
        else:
            lines.append(f"{result['title']}: {_value(result, 'Latest value')} for {_value(result, 'Observation date')}"
                         + (f", {_value(result, 'Change from previous')} from the previous reading."
                            if _value(result, "Change from previous") else "."))
    elif tool == "fx":
        lines.append(f"{_value(result, 'Rate')} on {_value(result, 'Rate date')}"
                     + (f"; {_value(result, 'Change over a year')} over a year." if _value(result, "Change over a year") else "."))
    elif tool == "oil":
        lines.append(f"{result['title']}: {_value(result, 'Spot price')} on {_value(result, 'Price date')}.")
    elif tool in ("news", "calendar"):
        lines.append(f"{result['title']}: {len(result['facts'])} item(s), listed below with links.")
    kind = "data" if tool in ("quote", "macro", "oil", "news", "calendar") else "calculated"
    return [{"text": line, "kind": kind} for line in lines]


async def answer(question: str) -> dict:
    parsed = parse(question)
    calls, understood = plan(parsed)
    if not calls:
        return {
            "mode": "rules", "question": question, "understood": None,
            "summary": [{"text": "I could not match that to an instrument or a question type I can answer. "
                                 "Try one of the examples below.", "kind": "unavailable"}],
            "sections": [], "sources": [], "examples": EXAMPLES,
            "interpretation": None,
        }

    sections = []
    for name, args in calls:
        result = tools.TOOLS[name](**args)
        sections.append(await result if hasattr(result, "__await__") else result)

    sources, summary = [], []
    for section in sections:
        section["source_ids"] = []
        for source in section["sources"]:
            source = {**source, "id": f"S{len(sources) + 1}"}
            sources.append(source)
            section["source_ids"].append(source["id"])
        summary.extend(summarize(section))

    return {
        "mode": "rules", "question": question, "understood": understood,
        "summary": summary, "sections": sections, "sources": sources, "examples": EXAMPLES,
        "interpretation": None,  # the rule-based assistant reports figures only; it does not interpret
    }
