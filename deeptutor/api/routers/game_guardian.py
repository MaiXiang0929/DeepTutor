"""Extend existing guardian authorization to game limits and reporting."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deeptutor.api.routers.auth import require_auth
from deeptutor.api.routers.multi_user import _log_supervisor_action, _require_guardian_access
from deeptutor.services.gamification.guardian_limits import get_limits, set_limits, weekly_report
from deeptutor.services.gamification.models import GameStore

router = APIRouter()


class GameLimitsRequest(BaseModel):
    pin: str = Field(pattern=r"^[0-9]{6}$")
    game_minutes: int = Field(ge=0, le=60)
    trades: int = Field(ge=0, le=10)


def _authorize(current, user_id, permission):
    if current is None:
        raise HTTPException(401, "Guardian sign-in is required")
    return _require_guardian_access(current, user_id, permission)[2:]


def _limits(user_id, payload=None):
    store = GameStore()
    try:
        if payload is not None:
            set_limits(store, user_id, payload.pin, payload.game_minutes, payload.trades)
        return get_limits(store, user_id)
    finally:
        store.engine.dispose()


@router.get("/{user_id}/limits")
async def read_limits(user_id: str, current=Depends(require_auth)):
    _authorize(current, user_id, "manage_restrictions")
    return await asyncio.to_thread(_limits, user_id)


@router.put("/{user_id}/limits")
async def change_limits(user_id: str, payload: GameLimitsRequest, current=Depends(require_auth)):
    actor, admin = _authorize(current, user_id, "manage_restrictions")
    try:
        limits = await asyncio.to_thread(_limits, user_id, payload)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    _log_supervisor_action(
        "guardian_game_limits_set",
        actor_user_id=actor,
        learner_user_id=user_id,
        is_admin=admin,
        summary={"game_minutes": limits["game_minutes"], "trades": limits["trades"]},
    )
    return limits


@router.get("/{user_id}/weekly-report")
async def report(user_id: str, current=Depends(require_auth)):
    actor, admin = _authorize(current, user_id, "view_reports")
    rows = await asyncio.to_thread(weekly_report, user_id)
    _log_supervisor_action(
        "guardian_game_report_view",
        actor_user_id=actor,
        learner_user_id=user_id,
        is_admin=admin,
    )
    return {"days": rows}
