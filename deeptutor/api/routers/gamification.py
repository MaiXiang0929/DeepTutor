"""Authenticated gamification profile and inventory endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeptutor.api.routers.minigames import router as minigames_router
from deeptutor.multi_user.context import get_current_user
from deeptutor.services.gamification.models import GameStore

router = APIRouter()
router.include_router(minigames_router, prefix="/games")


class SynthesizeRequest(BaseModel):
    target_item_id: str = Field(min_length=1, max_length=200)


class EquipRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    equipped: bool = True


def _run(method, *args):
    store = GameStore()
    try:
        return getattr(store, method)(*args)
    finally:
        store.engine.dispose()


@router.get("/catalog")
async def catalog():
    return await asyncio.to_thread(_run, "catalog")


@router.get("/profile")
async def profile():
    return await asyncio.to_thread(_run, "profile", get_current_user().id)


@router.post("/synthesize")
async def synthesize(payload: SynthesizeRequest):
    user_id = get_current_user().id
    try:
        await asyncio.to_thread(_run, "synthesize", user_id, payload.target_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(_run, "profile", user_id)


@router.post("/equip")
async def equip(payload: EquipRequest):
    user_id = get_current_user().id
    try:
        await asyncio.to_thread(_run, "equip", user_id, payload.item_id, payload.equipped)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(_run, "profile", user_id)
