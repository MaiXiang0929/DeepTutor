"""Project recent learning activity from the authenticated user's memory."""

from datetime import datetime, timezone

from deeptutor.multi_user.context import get_current_user
from deeptutor.services.memory import get_memory_store
from deeptutor.services.memory.trace import TraceEvent, iter_since

SURFACES = ("chat", "quiz", "book")


def build_mobile_greeting_context(user_id: str) -> dict:
    if user_id != get_current_user().id:
        raise PermissionError("Learning memory belongs to the current user")
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    events = sorted(
        (event for surface in SURFACES for event in iter_since(surface, midnight)),
        key=lambda event: event.ts,
        reverse=True,
    )
    topics, trace_ids, seen_turns = [], set(), set()
    duration = 0
    reward = None
    for event in events:
        if event.kind != "study_completed":
            continue
        key = (event.surface, event.turn_id or event.id)
        if key in seen_turns:
            continue
        seen_turns.add(key)
        trace_ids.add(event.id)
        topic = event.payload.get("topic")
        if isinstance(topic, str) and topic.strip() and topic.strip() not in topics:
            topics.append(topic.strip()[:120])
        elapsed = event.payload.get("duration_seconds")
        if isinstance(elapsed, int) and elapsed >= 0:
            duration += elapsed
        if reward is None and isinstance(event.payload.get("reward"), dict):
            reward = {**event.payload["reward"], "already_granted": True}
    store = get_memory_store()
    facts = [
        entry.text
        for surface in SURFACES
        for entry in store.read_doc("L2", surface).all_entries()
        if trace_ids.intersection(entry.refs)
    ]
    return {
        "topics": topics[:5],
        "duration_seconds": duration,
        "facts": facts[:5],
        "reward": reward,
    }


async def remember_treehole(note: str, emotion_state: str) -> None:
    """Save only the learner's explicitly selected note, with an L1 reference."""
    note = " ".join(note.split())[:200]
    if not note:
        return
    store = get_memory_store()
    event = TraceEvent.new(
        "partner", "companion_note", {"note": note, "emotion_state": emotion_state}
    )
    await store.emit(event)
    await store.apply_ops_payload(
        "L2",
        "partner",
        [
            {"op": "add", "section": "Companion notes", "text": note, "refs": [event.id]},
        ],
    )
