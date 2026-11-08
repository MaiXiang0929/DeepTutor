"""Authenticated trade commands and a participant-only room on /ws."""

import asyncio
import base64
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from deeptutor.multi_user.context import get_current_user
from deeptutor.multi_user.identity import load_or_create_auth_secret
from deeptutor.services.gamification.models import GameStore
from deeptutor.services.gamification.trade_engine import TOKEN_SECONDS, TradeEngine

router = APIRouter()


class PairRequest(BaseModel):
    handshake_token: str = Field(min_length=10, max_length=2048)


class TradeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal[
        "trade:update_offer", "trade:lock", "trade:confirm", "trade:cancel", "trade:quick_emote"
    ]
    items: dict[str, StrictInt] = Field(default_factory=dict, max_length=3)
    revision: StrictInt | None = None
    emote_id: Literal["thumbs_up", "please", "thank_you", "wow"] | None = None


def _call(method, *args):
    store = GameStore()
    try:
        engine = TradeEngine(store, load_or_create_auth_secret())
        return getattr(engine, method)(*args)
    finally:
        store.engine.dispose()


@router.post("/token")
async def issue_token():
    token = await asyncio.to_thread(_call, "issue", get_current_user().id)
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[0]))
    return {"handshake_token": token, "session_id": payload["nonce"], "expires_in": TOKEN_SECONDS}


@router.post("/pair")
async def pair(payload: PairRequest):
    try:
        result = await asyncio.to_thread(
            _call, "pair", get_current_user().id, payload.handshake_token
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {**result, "websocket_path": f"/ws?trade_session_id={result['session_id']}"}


@router.get("/{session_id}")
async def trade_state(session_id: str):
    try:
        return await asyncio.to_thread(_call, "state", get_current_user().id, session_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


def _command(command: TradeCommand) -> tuple:
    if command.type == "trade:update_offer":
        return ("update_offer", command.items)
    if command.type == "trade:quick_emote" and command.emote_id is not None:
        return ("emote", command.emote_id)
    if command.type == "trade:cancel":
        return ("cancel",)
    if command.type in ("trade:lock", "trade:confirm") and command.revision is not None:
        return (command.type.split(":")[1], command.revision)
    raise ValueError("Command is missing a required field")


async def trade_websocket(ws: WebSocket, session_id: str, user_id: str) -> None:
    try:
        state = await asyncio.to_thread(_call, "state", user_id, session_id)
    except LookupError:
        await ws.close(code=1008)
        return

    await ws.accept()
    previous = None
    try:
        while True:
            key = (state["version"], state["status"])
            if key != previous:
                kind = "trade:completed" if state["status"] == "completed" else "trade:state"
                await ws.send_json({"type": kind, "state": state})
                previous = key
            if state["status"] in ("completed", "cancelled", "expired"):
                await ws.close()
                return
            try:
                raw = await asyncio.wait_for(ws.receive_json(), timeout=0.5)
            except TimeoutError:
                state = await asyncio.to_thread(_call, "state", user_id, session_id)
                continue
            except ValueError:
                await ws.send_json({"type": "trade:error", "message": "Invalid JSON"})
                continue
            try:
                method, *args = _command(TradeCommand.model_validate(raw))
                state = await asyncio.to_thread(_call, method, user_id, session_id, *args)
            except ValidationError:
                await ws.send_json({"type": "trade:error", "message": "Invalid trade command"})
            except ValueError as exc:
                await ws.send_json({"type": "trade:error", "message": str(exc)})
    except WebSocketDisconnect:
        return


@router.post("/{session_id}/partner-hangout")
async def partner_hangout(session_id: str):
    """Share a generated question without transferring private partner memory."""
    user_id = get_current_user().id
    try:
        cached = await asyncio.to_thread(_call, "hangout", user_id, session_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if cached:
        return cached

    from deeptutor.agents.question.coordinator import AgentCoordinator
    from deeptutor.modules.catalog import ModuleUnavailable, require_module

    try:
        require_module("questions")
    except ModuleUnavailable as exc:
        raise HTTPException(503, "Question generation is unavailable") from exc
    result = await AgentCoordinator(language="zh", enable_idea_rag=False).generate_from_topic(
        user_topic="适合10–14岁学生的90秒科学常识抢答题，不涉及个人信息",
        num_questions=1,
        question_types=["single_choice"],
    )
    questions = result.get("results") or []
    if not result.get("success") or not questions:
        raise HTTPException(503, "Question generation is unavailable")
    question = questions[0].get("qa_pair", {})
    if not question.get("question") or not isinstance(question.get("options"), dict):
        raise HTTPException(503, "Question generation did not return a playable quiz")
    return await asyncio.to_thread(_call, "hangout", user_id, session_id, question)


class HangoutAnswer(BaseModel):
    option: str = Field(min_length=1, max_length=20)


@router.get("/{session_id}/partner-hangout")
async def hangout_state(session_id: str):
    try:
        result = await asyncio.to_thread(_call, "hangout", get_current_user().id, session_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "Quiz has not started")
    return result


@router.post("/{session_id}/partner-hangout/answer")
async def answer_hangout(session_id: str, payload: HangoutAnswer):
    try:
        return await asyncio.to_thread(
            _call, "answer_hangout", get_current_user().id, session_id, payload.option
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
