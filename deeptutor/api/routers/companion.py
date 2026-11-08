"""Mobile companion endpoints backed by existing Partners and Voice services."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from deeptutor.api.routers.partners import (
    ChatMessageRequest,
    CreatePartnerRequest,
    SoulSpec,
    create_partner,
    partner_chat_http,
    usable_partner,
)
from deeptutor.multi_user.context import get_current_user
from deeptutor.services.companion.study_memory_bridge import (
    build_mobile_greeting_context,
    remember_treehole,
)
from deeptutor.services.companion.teen_personas import (
    PERSONAS,
    PersonaId,
    greeting,
    parse_reply,
    soul_template,
)
from deeptutor.services.gamification.models import GameStore
from deeptutor.services.voice import synthesize_speech
from deeptutor.services.voice.audio import _parse_pcm_content_type, _pcm16_to_wav
from deeptutor.services.voice.base import VoiceProviderError

router = APIRouter()


class GreetingRequest(BaseModel):
    persona: PersonaId = "cyber_navigator"


class TreeholeRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    remember_note: str | None = Field(default=None, max_length=200)


async def _greeting(persona: PersonaId) -> dict:
    context = await asyncio.to_thread(build_mobile_greeting_context, get_current_user().id)
    return greeting(persona, context)


@router.post("/proactive-greeting")
async def proactive_greeting(payload: GreetingRequest) -> dict:
    return {
        **await _greeting(payload.persona),
        "audio_url": f"/api/v1/companion/greeting-audio?persona={payload.persona}",
    }


@router.get("/greeting-audio")
async def greeting_audio(persona: PersonaId = "cyber_navigator") -> Response:
    result = await _greeting(persona)
    try:
        audio, content_type = await synthesize_speech(result["text"])
    except (ValueError, VoiceProviderError) as exc:
        raise HTTPException(503, "Companion speech is unavailable") from exc
    if pcm_info := _parse_pcm_content_type(content_type):
        audio = _pcm16_to_wav(audio, sample_rate=pcm_info[0], channels=pcm_info[1])
        content_type = "audio/wav"
    return Response(audio, media_type=content_type, headers={"Cache-Control": "no-store"})


@router.post("/presets/{persona}")
async def create_companion(persona: PersonaId) -> dict:
    name, description = PERSONAS[persona]
    from uuid import uuid4

    result = await create_partner(
        CreatePartnerRequest(
            partner_id=f"{persona.replace('_', '-')}-{uuid4().hex[:10]}",
            name=name,
            description=description,
            language="zh",
            soul=SoulSpec(source="custom", content=soul_template(persona)),
            enabled_tools=[],
            builtin_tools=[],
            start=False,
        )
    )

    def select(user_id):
        game = GameStore()
        try:
            game.select_companion(user_id, result["partner_id"], persona, name)
        finally:
            game.engine.dispose()

    await asyncio.to_thread(select, get_current_user().id)
    return result


@router.post("/{partner_id}/treehole")
async def treehole(payload: TreeholeRequest, partner_id: str = Depends(usable_partner)) -> dict:
    result = await partner_chat_http(
        partner_id,
        ChatMessageRequest(
            content=payload.content,
            session_id=payload.session_id,
        ),
    )
    reply = parse_reply(result["content"])
    if payload.remember_note:
        await remember_treehole(payload.remember_note, reply["emotion_state"])
    return {"session_id": result["session_id"], **reply}


class MemoryNote(BaseModel):
    note: str = Field(min_length=1, max_length=200)


@router.post("/{partner_id}/memory-note")
async def save_memory_note(payload: MemoryNote, partner_id: str = Depends(usable_partner)):
    await remember_treehole(payload.note, "idle")
    return {"saved": True}
