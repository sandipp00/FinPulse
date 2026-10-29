"""The research assistant: question parsing, templates, number checks and the local-AI loop.

Tools and Ollama are mocked, so these tests use no network and no model.
"""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import assistant_local, assistant_rules, config, main
from backend import research_tools as tools


# ---- parsing and planning -------------------------------------------------------------

@pytest.mark.parametrize("question, expected", [
    ("How has AAPL performed?", [("quote", {"symbol": "AAPL"}), ("performance", {"symbol": "AAPL"})]),
    ("Compare Bitcoin with the S&P 500", [("compare", {"symbol": "BTC/USDT", "benchmark": "^GSPC"})]),
    ("compare nifty and s&p", [("compare", {"symbol": "^NSEI", "benchmark": "^GSPC"})]),
    ("beta of solana", [("compare", {"symbol": "SOL/USDT", "benchmark": "BTC/USDT"})]),
    ("How risky is ETH?", [("performance", {"symbol": "ETH/USDT"})]),
    ("Backtest SOL", [("backtest", {"symbol": "SOL/USDT"})]),
    ("Latest news on Bitcoin", [("news", {"instrument": "BTC/USDT"})]),
    ("crypto news", [("news", {"topic": "crypto"})]),
    ("What's on the calendar this week?", [("calendar", {"days_ahead": 14})]),
    ("What is US inflation?", [("macro", {"series_id": "CPIAUCSL"})]),
    ("core pce", [("macro", {"series_id": "PCEPILFE"})]),
    ("10 year treasury yield", [("macro", {"series_id": "DGS10"})]),
    ("EUR/INR rate", [("fx", {"pair": "EUR/INR"})]),
    ("USD/INR rate", [("fx", {"pair": "USD/INR"})]),
    ("Brent oil price", [("oil", {"series_id": "RBRTE"})]),
    ("oil prices", [("oil", {"series_id": "RWTC"}), ("oil", {"series_id": "RBRTE"})]),
])
def test_questions_route_to_the_right_tools(question, expected):
    calls, understood = assistant_rules.plan(assistant_rules.parse(question))
    assert calls == expected
    assert understood


@pytest.mark.parametrize("question", ["what is the weather", "method acting", "solid gold toilet", "soil quality"])
def test_words_that_only_contain_a_name_do_not_match(question):
    assert assistant_rules.plan(assistant_rules.parse(question)) == ([], "")


# ---- templates and sources -------------------------------------------------------------

def fake_result(tool, args, facts, error=None, sources=None):
    return {"tool": tool, "args": args, "title": f"{tool} title", "error": error, "notes": [],
            "facts": [{"label": label, "value": value, "kind": "calculated"} for label, value in facts],
            "sources": sources if sources is not None else [{"name": f"{tool} source", "provider": "test", "as_of": "2026-10-28"}]}


def test_answers_copy_figures_from_tool_facts_and_number_sources(monkeypatch):
    async def performance(symbol):
        return fake_result("performance", {"symbol": symbol}, [
            ("Return, last 365 days", "+28.29%"), ("Return, last 30 days", "+1.60%"),
            ("Volatility, last 365 days (annualized)", "23.96%"), ("Below its peak now", "-1.26%"),
        ])

    def quote(symbol):
        return fake_result("quote", {"symbol": symbol}, [("Price", "343.83 USD"), ("Freshness", "end of day")])

    monkeypatch.setitem(tools.TOOLS, "performance", performance)
    monkeypatch.setitem(tools.TOOLS, "quote", quote)
    body = asyncio.run(assistant_rules.answer("How has AAPL performed?"))

    texts = [s["text"] for s in body["summary"]]
    assert texts[0] == "AAPL is at 343.83 USD (end of day)."
    assert "returned +28.29%; over 30 days, +1.60%" in texts[1]
    assert [s["id"] for s in body["sources"]] == ["S1", "S2"]
    assert [sec["source_ids"] for sec in body["sections"]] == [["S1"], ["S2"]]
    assert body["interpretation"] is None


def test_a_failing_tool_is_reported_as_unavailable(monkeypatch):
    async def backtest(symbol):
        return fake_result("backtest", {"symbol": symbol}, [], error="Signal backtests run on live crypto only.", sources=[])

    monkeypatch.setitem(tools.TOOLS, "backtest", backtest)
    body = asyncio.run(assistant_rules.answer("Backtest AAPL"))
    assert body["summary"] == [{"text": "backtest title: Signal backtests run on live crypto only.", "kind": "unavailable"}]
    assert body["sources"] == []


def test_an_unknown_question_offers_examples():
    body = asyncio.run(assistant_rules.answer("what is the weather"))
    assert body["summary"][0]["kind"] == "unavailable"
    assert body["examples"] == assistant_rules.EXAMPLES
    assert body["sections"] == []


# ---- the local model's number check ---------------------------------------------------

SECTIONS = [fake_result("performance", {"symbol": "AAPL"}, [
    ("Return, last 365 days", "+28.29%"), ("Last close", "343.83 USD"), ("Last close date", "2026-10-28"),
    ("Shared trading days", 959),
])]


def test_numbers_from_tool_results_are_verified():
    answer = "AAPL closed at $343.83 on 2026-10-28 [S1], up 28.29% over the year across 959 days."
    assert assistant_local.unverified_numbers(answer, SECTIONS) == []


def test_invented_numbers_are_flagged():
    answer = "AAPL closed at 343.83 [S1] and analysts expect 410 next year, a 19.2% gain."
    assert assistant_local.unverified_numbers(answer, SECTIONS) == ["19.2", "410"]


def test_source_markers_and_small_counts_are_not_flagged():
    assert assistant_local.unverified_numbers("Two points [S1][S2]: 1) price 2) return.", SECTIONS) == []


def test_tool_arguments_are_restricted_to_the_tool_parameters():
    assert assistant_local._clean_args("compare", {"symbol": "AAPL", "benchmark": "^GSPC", "evil": "x"}) == \
        {"symbol": "AAPL", "benchmark": "^GSPC"}
    assert assistant_local._clean_args("compare", {"symbol": "AAPL"}) is None  # benchmark missing
    assert assistant_local._clean_args("news", {}) == {}  # instrument is optional
    assert assistant_local._clean_args("quote", '{"symbol": "AAPL"}') == {"symbol": "AAPL"}
    assert assistant_local._clean_args("quote", "not json") is None


def test_tool_definitions_list_every_tool_with_required_fields():
    defs = {d["function"]["name"]: d["function"] for d in assistant_local.tool_definitions()}
    assert set(defs) == set(tools.TOOLS)
    assert defs["compare"]["parameters"]["required"] == ["symbol", "benchmark"]
    assert defs["news"]["parameters"]["required"] == []


# ---- the local model's tool loop (Ollama mocked) -------------------------------------

class FakeOllama:
    def __init__(self, replies, models=("qwen2.5:3b",)):
        self.replies, self.models, self.chats = list(replies), list(models), []

    def handler(self, request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in self.models]})
        body = json.loads(request.content)
        self.chats.append(body)
        return httpx.Response(200, json={"message": self.replies.pop(0)})


@pytest.fixture
def ollama(monkeypatch):
    def install(fake):
        transport = httpx.MockTransport(fake.handler)
        monkeypatch.setattr(assistant_local, "_client",
                            lambda timeout=1: httpx.AsyncClient(transport=transport, base_url="http://ollama.test"))
        monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen2.5:3b")
        return fake
    return install


def test_the_model_calls_a_tool_then_answers_from_it(ollama, monkeypatch):
    async def performance(symbol):
        return fake_result("performance", {"symbol": symbol}, [("Return, last 365 days", "+28.29%")])

    monkeypatch.setitem(tools.TOOLS, "performance", performance)
    fake = ollama(FakeOllama([
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "performance", "arguments": {"symbol": "AAPL"}}}]},
        {"role": "assistant", "content": "AAPL returned 28.29% over the year [S1]."},
    ]))

    body = asyncio.run(assistant_local.answer("How has AAPL done?"))

    assert body["answer"] == "AAPL returned 28.29% over the year [S1]."
    assert body["unverified"] == []
    assert [s["id"] for s in body["sources"]] == ["S1"]
    tool_message = fake.chats[1]["messages"][-1]
    assert tool_message["role"] == "tool" and json.loads(tool_message["content"])["source_ids"] == ["S1"]
    assert fake.chats[0]["options"]["temperature"] == 0
    assert fake.chats[0]["messages"][0]["content"].startswith("You are the research assistant inside FinPulse")


def test_unknown_tools_and_bad_arguments_are_refused_not_run(ollama):
    fake = ollama(FakeOllama([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "place_order", "arguments": {"symbol": "BTC/USDT"}}},
            {"function": {"name": "compare", "arguments": {"symbol": "AAPL"}}},
        ]},
        {"role": "assistant", "content": "I could not get that data."},
    ]))
    body = asyncio.run(assistant_local.answer("Buy bitcoin"))
    errors = [json.loads(m["content"])["error"] for m in fake.chats[1]["messages"] if m["role"] == "tool"]
    assert errors == ["Unknown tool or invalid arguments: place_order", "Unknown tool or invalid arguments: compare"]
    assert body["sections"] == [] and body["sources"] == []


def test_the_loop_stops_after_the_round_limit(ollama, monkeypatch):
    monkeypatch.setitem(tools.TOOLS, "calendar", lambda days_ahead=14: fake_result("calendar", {}, [("x", "y")]))
    looping = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "calendar", "arguments": {}}}]}
    ollama(FakeOllama([looping] * assistant_local.MAX_TOOL_ROUNDS))
    body = asyncio.run(assistant_local.answer("calendar"))
    assert body["answer"] == "The local model did not finish within the tool-call limit."


def test_unavailable_when_the_model_is_not_installed(ollama):
    ollama(FakeOllama([], models=["llama3.2:1b"]))
    body = asyncio.run(assistant_local.answer("anything"))
    assert body["available"] is False
    assert "ollama pull qwen2.5:3b" in body["error"]


def test_unavailable_when_ollama_is_not_running(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(assistant_local, "_client",
                        lambda timeout=1: httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://ollama.test"))
    status = asyncio.run(assistant_local.status())
    assert status["available"] is False and "not running" in status["error"]


# ---- API ------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "finpulse.db")
    monkeypatch.setattr(main, "DATABASE_PATH", tmp_path / "finpulse.db")
    monkeypatch.setattr(config, "LIVE_FEED_ENABLED", False)
    with TestClient(main.app) as test_client:
        yield test_client


def test_ask_rules_endpoint(client):
    body = client.post("/api/assistant/ask", json={"question": "what is the weather"}).json()
    assert body["mode"] == "rules" and body["summary"][0]["kind"] == "unavailable"


@pytest.mark.parametrize("payload", [{"question": "x"}, {"question": "a" * 301}, {"question": "AAPL", "mode": "cloud"}, {}])
def test_ask_validates_input(client, payload):
    assert client.post("/api/assistant/ask", json=payload).status_code == 422


def test_ask_from_another_site_is_refused(client):
    response = client.post("/api/assistant/ask", json={"question": "AAPL"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
