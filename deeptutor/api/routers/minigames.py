"""Authenticated minigame commands."""

import asyncio
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeptutor.multi_user.context import get_current_user
from deeptutor.services.gamification.minigames import MiniGames
from deeptutor.services.gamification.models import GameStore

router = APIRouter()
_TURTLE_RULES = (
    Path(__file__).parents[2] / "services/gamification/turtle_soup/SKILL.md"
).read_text(encoding="utf-8")


class StartGame(BaseModel):
    mode: Literal["match", "turtle"]
    request_id: str = Field(min_length=8, max_length=100)


class MatchMove(BaseModel):
    left: str = Field(min_length=1, max_length=80)
    right: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=0)


class TurtleMove(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    guess: bool = False
    version: int = Field(ge=0)


def _execute(method, user_id, args):
    store = GameStore()
    try:
        return getattr(MiniGames(store), method)(user_id, *args)
    finally:
        store.engine.dispose()


async def _call(method, *args):
    try:
        return await asyncio.to_thread(_execute, method, get_current_user().id, args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/start")
async def start(payload: StartGame):
    return await _call("start", payload.mode, payload.request_id)


@router.get("/{round_id}")
async def state(round_id: str):
    return await _call("state", round_id)


@router.post("/{round_id}/match")
async def match(round_id: str, payload: MatchMove):
    return await _call("match", round_id, payload.left, payload.right, payload.version)


async def _judge(mystery, truth, move):
    from deeptutor.core.context import UnifiedContext
    from deeptutor.core.stream import StreamEventType
    from deeptutor.runtime.orchestrator import ChatOrchestrator

    rule = (
        "仅当猜测说明了核心科学机制才回复 yes，否则回复 no。"
        if move.guess
        else "只按谜底回答 yes、no 或 unrelated。"
    )
    context = UnifiedContext(
        user_message=move.question,
        language="zh",
        enabled_tools=[],
        allowed_builtin_tools=[],
        persona_context=(
            _TURTLE_RULES
            + "\n"
            + f"谜面：{mystery}。秘密谜底：{truth}。{rule}只输出这三个单词之一。"
        ),
    )
    async for event in ChatOrchestrator().handle(context):
        if event.type == StreamEventType.RESULT:
            verdict = str(event.metadata.get("response", "")).strip().casefold()
            if verdict in ("yes", "no", "unrelated"):
                return verdict
    raise HTTPException(503, "谜题裁判暂不可用，请重试")


@router.post("/{round_id}/ask")
async def ask(round_id: str, payload: TurtleMove):
    prompt, truth = await _call("riddle", round_id, payload.version)
    verdict = await _judge(prompt, truth, payload)
    return await _call("answer", round_id, verdict, payload.guess, payload.version)
