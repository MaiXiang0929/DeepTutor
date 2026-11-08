"""Best-effort rewards for completed desktop learning activities."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from ipaddress import ip_address
import random

from .models import SUBJECTS, GameStore

# The WebSocket adapter sets this once after authentication. Tasks spawned by
# the turn runtime inherit it, while CLI, SDK, and partner turns default off.
desktop_request: ContextVar[bool] = ContextVar("gamification_desktop", default=False)
ENERGY_BY_CAPABILITY = {
    "deep_solve": 30,
    "mastery_path": 25,
    "immersive_reading": 20,
    "deep_research": 50,
    "practice": 10,
}


def is_desktop_user_agent(user_agent: str) -> bool:
    return "OpenDeepTutor/" in user_agent


def allows_learning_reward(
    user_agent: str, *, client_host: str = "", web_learning: bool = False
) -> bool:
    """Recognize eligible requests at the authenticated learning adapters."""
    if is_desktop_user_agent(user_agent) or web_learning or client_host == "localhost":
        return True
    try:
        return ip_address(client_host).is_loopback
    except ValueError:
        return False


def choose_subject(lucky_subject: str, rng=random) -> str:
    return rng.choices(SUBJECTS, weights=[4 if x == lucky_subject else 1 for x in SUBJECTS], k=1)[0]


async def on_capability_turn_completed(
    user_id: str, capability_name: str, turn_metadata: dict
) -> dict | None:
    """Grant one reward off the event loop, returning the replayable receipt."""
    energy = ENERGY_BY_CAPABILITY.get(capability_name.lower())
    if not energy or not user_id or not turn_metadata.get("desktop"):
        return None
    identifier = str(turn_metadata.get("turn_id") or "")
    event_id = f"{capability_name.lower()}:{identifier}" if identifier else ""

    def grant():
        store = GameStore()
        try:
            return store.grant_reward(user_id, event_id, energy, choose_subject)
        finally:
            store.engine.dispose()

    return await asyncio.to_thread(grant)
