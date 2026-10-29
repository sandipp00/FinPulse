"""Research-assistant routes: rule-based (always available) and local AI (Ollama, optional)."""
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend import assistant_local, assistant_rules

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class Question(BaseModel):
    question: str = Field(..., min_length=2, max_length=300)
    mode: Literal["rules", "local"] = "rules"


@router.get("/status")
async def status():
    return {
        "rules": {"available": True},
        "local": await assistant_local.status(),
        "examples": assistant_rules.EXAMPLES,
    }


@router.post("/ask")
async def ask(body: Question):
    """Answer a question from FinPulse's own data. Read-only: nothing is changed."""
    question = body.question.strip()
    if body.mode == "rules":
        return await assistant_rules.answer(question)
    try:
        return await assistant_local.answer(question)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="The local model took too long to answer.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"The local model failed ({type(exc).__name__}).") from exc
