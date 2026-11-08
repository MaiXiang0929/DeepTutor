import pytest

from deeptutor.services.gamification.models import GameStore


def test_seed_and_synthesis(tmp_path):
    store = GameStore(tmp_path / "game.db")
    catalog = store.catalog()
    assert len([x for x in catalog if x["category"] == "card_fragment"]) >= 5
    target = next(x for x in catalog if x["category"] == "companion_skin")
    with pytest.raises(ValueError):
        store.synthesize("u", target["item_id"])
    recipe = target["synthesis_recipe_json"]
    for item in recipe:
        store.add_item("u", item, "desktop_study")
    store.synthesize("u", target["item_id"])
    inv = store.profile("u")["inventory"]
    assert next(x for x in inv if x["item_id"] == target["item_id"])["quantity"] == 1
    assert not any(x["item_id"] in recipe for x in inv)


@pytest.mark.asyncio
async def test_reward_is_atomic_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    from deeptutor.services.gamification.reward_hook import on_capability_turn_completed

    reward = await on_capability_turn_completed(
        "u", "deep_solve", {"desktop": True, "turn_id": "turn-1"}
    )
    assert 10 <= reward["energy_points"] <= 50
    assert reward["item"]["category"] == "card_fragment"
    assert (
        await on_capability_turn_completed(
            "u", "deep_solve", {"desktop": True, "turn_id": "turn-1"}
        )
        == reward
    )
    assert (
        await on_capability_turn_completed(
            "u", "deep_solve", {"desktop": False, "turn_id": "turn-2"}
        )
        is None
    )
    profile = GameStore().profile("u")
    assert profile["energy_points"] == reward["energy_points"]
    assert sum(x["quantity"] for x in profile["inventory"]) == 1


def test_lucky_subject_weight():
    import random

    from deeptutor.services.gamification.reward_hook import choose_subject

    rng = random.Random(42)
    draws = [choose_subject("math", rng) for _ in range(10000)]
    assert draws.count("math") > 2 * max(
        draws.count(x) for x in ("physics", "history", "coding", "literature")
    )


def test_synthesis_rolls_back_and_equip(tmp_path):
    store = GameStore(tmp_path / "game.db")
    store.add_item("u", "math_fragment", "desktop_study")
    with pytest.raises(ValueError):
        store.synthesize("u", "math_skin")
    assert store.profile("u")["inventory"][0]["quantity"] == 1
    store.add_item("u", "math_fragment", "desktop_study")
    store.synthesize("u", "math_skin")
    store.equip("u", "math_skin", True)
    assert next(x for x in store.profile("u")["inventory"] if x["item_id"] == "math_skin")[
        "is_equipped"
    ]
    store.equip("u", "math_skin", False)
    with pytest.raises(ValueError):
        store.equip("other", "math_skin", True)


@pytest.mark.asyncio
async def test_desktop_turn_done_contains_reward(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from deeptutor.app.container import RuntimeRegistry
    from deeptutor.app.service import TurnApplicationService
    from deeptutor.core.stream import StreamEvent, StreamEventType
    from deeptutor.multi_user.context import get_current_user
    from deeptutor.runtime.coordination import MemoryCoordinator
    from deeptutor.services.gamification.reward_hook import desktop_request
    from deeptutor.services.path_service import PathService
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from deeptutor.services.session.turns.title_service import SessionTitleService

    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    monkeypatch.setattr(PathService, "_instance", PathService(workspace_root=tmp_path / "data"))

    class Builder:
        def __init__(self, *args, **kwargs):
            pass

        async def build(self, **kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class Orchestrator:
        async def handle(self, context):
            yield StreamEvent(type=StreamEventType.CONTENT, content="answer", source="deep_solve")
            yield StreamEvent(
                type=StreamEventType.DONE, source="deep_solve", metadata={"status": "completed"}
            )

    async def noop(*args, **kwargs):
        pass

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", Builder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", Orchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_store", lambda: SimpleNamespace(emit=noop)
    )
    monkeypatch.setattr(SessionTitleService, "_maybe_generate_session_title", noop)
    store = SQLiteSessionStore(tmp_path / "sessions.db")
    coordinator = MemoryCoordinator(lease_ttl_seconds=30)
    service = TurnApplicationService(
        SimpleNamespace(get=lambda: store), RuntimeRegistry(coordinator, "worker"), coordinator
    )
    token = desktop_request.set(True)
    try:
        _, turn = await service.start_turn({"content": "solve", "capability": "deep_solve"})
        events = [event async for event in service.subscribe_turn(turn["id"])]
    finally:
        desktop_request.reset(token)
    done = next(event for event in events if event["type"] == "done")
    reward = done["metadata"]["gamification_reward"]
    assert reward["item"]["category"] == "card_fragment"
    assert GameStore().profile(get_current_user().id)["energy_points"] == reward["energy_points"]
    persisted = await store.get_events(turn["id"])
    assert (
        next(event for event in persisted if event["type"] == "done")["metadata"][
            "gamification_reward"
        ]
        == reward
    )

    class FailedOrchestrator:
        async def handle(self, context):
            yield StreamEvent(
                type=StreamEventType.ERROR,
                source="deep_solve",
                content="failed",
                metadata={"turn_terminal": True, "status": "failed"},
            )
            yield StreamEvent(
                type=StreamEventType.DONE, source="deep_solve", metadata={"status": "failed"}
            )

    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FailedOrchestrator)
    token = desktop_request.set(True)
    try:
        _, failed_turn = await service.start_turn({"content": "fail", "capability": "deep_solve"})
        failed_events = [event async for event in service.subscribe_turn(failed_turn["id"])]
    finally:
        desktop_request.reset(token)
    failed_done = next(event for event in failed_events if event["type"] == "done")
    assert "gamification_reward" not in failed_done["metadata"]
    assert GameStore().profile(get_current_user().id)["energy_points"] == reward["energy_points"]


def test_profile_and_inventory_api(tmp_path, monkeypatch):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from deeptutor.api.routers.auth import require_auth
    from deeptutor.api.routers.gamification import router

    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/gamification", dependencies=[Depends(require_auth)])
    with TestClient(app) as client:
        profile = client.get("/api/v1/gamification/profile")
        assert profile.status_code == 200
        assert profile.json()["daily_game_minutes_remaining"] == 60
        from deeptutor.multi_user.paths import local_admin_user

        game = GameStore()
        for _ in range(2):
            game.add_item(local_admin_user().id, "math_fragment", "desktop_study")
        made = client.post("/api/v1/gamification/synthesize", json={"target_item_id": "math_skin"})
        assert made.status_code == 200
        equipped = client.post(
            "/api/v1/gamification/equip", json={"item_id": "math_skin", "equipped": True}
        )
        assert equipped.status_code == 200
        assert next(x for x in equipped.json()["inventory"] if x["item_id"] == "math_skin")[
            "is_equipped"
        ]
        assert (
            client.post(
                "/api/v1/gamification/equip", json={"item_id": "math_skin", "equipped": False}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/gamification/synthesize", json={"target_item_id": "math_skin"}
            ).status_code
            == 400
        )
        assert (
            client.post("/api/v1/gamification/equip", json={"item_id": "math_fragment"}).status_code
            == 400
        )


def test_practice_review_reward_is_retry_safe(tmp_path, monkeypatch):
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from deeptutor.api.routers import practice
    from deeptutor.multi_user.paths import local_admin_user
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore

    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    store = SQLiteSessionStore(tmp_path / "practice.db")
    monkeypatch.setattr(practice, "get_sqlite_session_store", lambda: store)

    async def seed():
        await store.ensure_notebook_session("lesson", "Lesson")
        await store.upsert_notebook_entries(
            "lesson",
            [
                {
                    "question_id": "q1",
                    "question": "2+2?",
                    "question_type": "single_choice",
                    "options": {"A": "3", "B": "4"},
                    "correct_answer": "B",
                    "user_answer": "A",
                    "is_correct": False,
                }
            ],
        )
        return await store.find_notebook_entry("lesson", "q1")

    entry = asyncio.run(seed())
    app = FastAPI()
    app.include_router(practice.router)
    payload = {"request_id": "review_request_00001", "version": 0, "rating": "good", "answer": "B"}
    with TestClient(app, headers={"user-agent": "Mozilla/5.0"}) as client:
        first = client.post(f"/questions/{entry['id']}/review", json=payload)
        second = client.post(f"/questions/{entry['id']}/review", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["gamification_reward"] == second.json()["gamification_reward"]
    assert GameStore().profile(local_admin_user().id)["energy_points"] == 10


def test_synthesis_rolls_back_prior_ingredient(tmp_path):
    from sqlalchemy.orm import Session

    from deeptutor.services.gamification.models import ItemCatalog

    store = GameStore(tmp_path / "game.db")
    with Session(store.engine) as session, session.begin():
        session.add(
            ItemCatalog(
                item_id="mixed_badge",
                name="Mixed",
                category="badge",
                subject_tag="math",
                rarity="rare",
                synthesis_recipe_json=["math_fragment", "physics_fragment"],
            )
        )
    store.add_item("u", "math_fragment", "desktop_study")
    with pytest.raises(ValueError, match="Insufficient"):
        store.synthesize("u", "mixed_badge")
    assert store.profile("u")["inventory"][0]["quantity"] == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_rewards_are_once(tmp_path, monkeypatch):
    import asyncio

    from deeptutor.services.gamification.reward_hook import on_capability_turn_completed

    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    rewards = await asyncio.gather(
        *(
            on_capability_turn_completed("u", "deep_research", {"desktop": True, "turn_id": "same"})
            for _ in range(8)
        )
    )
    assert all(reward == rewards[0] for reward in rewards)
    profile = GameStore().profile("u")
    assert profile["energy_points"] == 50
    assert sum(row["quantity"] for row in profile["inventory"]) == 1


def test_profile_daily_counters_reset(tmp_path):
    from datetime import date, timedelta

    from sqlalchemy.orm import Session

    from deeptutor.services.gamification.models import UserGameProfile

    store = GameStore(tmp_path / "game.db")
    store.profile("u")
    with Session(store.engine) as session, session.begin():
        profile = session.get(UserGameProfile, "u")
        profile.daily_date = date.today() - timedelta(days=1)
        profile.daily_game_minutes_used = 30
        profile.daily_trade_count = 2
    profile = store.profile("u")
    assert profile["daily_game_minutes_remaining"] == 60
    assert profile["daily_trade_count"] == 0
