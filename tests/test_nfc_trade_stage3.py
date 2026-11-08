from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.orm import Session

from deeptutor.services.gamification.models import GameStore, UserGameProfile


@pytest.fixture
def trade(tmp_path):
    from deeptutor.services.gamification.trade_engine import TradeEngine

    game = GameStore(tmp_path / "game.db")
    game.add_item("alice", "math_fragment", "desktop_study")
    game.add_item("bob", "coding_fragment", "desktop_study")
    return TradeEngine(game, "test-only-key"), game


def test_token_expiry_tampering_and_reuse(trade):
    engine, _ = trade
    token = engine.issue("alice", now=100)
    with pytest.raises(ValueError, match="expired"):
        engine.pair("bob", token, now=160)
    with pytest.raises(ValueError, match="signature"):
        engine.pair("bob", token[:-1] + ("0" if token[-1] != "0" else "1"), now=101)
    engine.pair("bob", token, now=101)
    with pytest.raises(ValueError, match="used"):
        engine.pair("bob", token, now=102)


def test_confirm_concurrently_and_invalidate_stale_offer(trade):
    engine, game = trade
    room = engine.pair("bob", engine.issue("alice"))
    session_id = room["session_id"]
    engine.update_offer("alice", session_id, {"math_fragment": 1})
    engine.update_offer("bob", session_id, {"coding_fragment": 1})
    engine.lock("alice", session_id)
    locked = engine.lock("bob", session_id)
    stale = locked["revision"]
    engine.confirm("alice", session_id, stale)
    edited = engine.update_offer("bob", session_id, {"coding_fragment": 1})
    assert not edited["initiator_confirmed"]
    with pytest.raises(ValueError):
        engine.confirm("bob", session_id, stale)
    engine.lock("alice", session_id)
    locked = engine.lock("bob", session_id)
    with ThreadPoolExecutor() as pool:
        states = list(
            pool.map(
                lambda user: engine.confirm(user, session_id, locked["revision"]), ["alice", "bob"]
            )
        )
    assert any(state["status"] == "completed" for state in states)
    assert game.profile("alice")["inventory"][0]["item_id"] == "coding_fragment"
    assert game.profile("bob")["inventory"][0]["item_id"] == "math_fragment"
    assert game.profile("alice")["daily_trade_count"] == 1


def test_daily_limit_and_cancellation(trade):
    engine, game = trade
    game.profile("alice")
    with Session(game.engine) as s, s.begin():
        s.get(UserGameProfile, "alice").daily_trade_count = 10
    with pytest.raises(ValueError, match="limit"):
        engine.pair("bob", engine.issue("alice"))
    with Session(game.engine) as s, s.begin():
        s.get(UserGameProfile, "alice").daily_trade_count = 9
    room = engine.pair("bob", engine.issue("alice"))
    assert engine.cancel("bob", room["session_id"])["status"] == "cancelled"
    assert game.profile("alice")["inventory"][0]["item_id"] == "math_fragment"


def test_room_rejects_text_and_broadcasts_completion(trade, monkeypatch):
    from fastapi import FastAPI, WebSocket
    from fastapi.testclient import TestClient

    from deeptutor.api.routers import nfc_trade

    engine, _ = trade
    room_id = engine.pair("bob", engine.issue("alice"))["session_id"]
    monkeypatch.setattr(nfc_trade, "_call", lambda method, *args: getattr(engine, method)(*args))
    app = FastAPI()

    @app.websocket("/room/{user}")
    async def room(ws: WebSocket, user: str):
        await nfc_trade.trade_websocket(ws, room_id, user)

    with TestClient(app) as client:
        with (
            client.websocket_connect("/room/alice") as alice,
            client.websocket_connect("/room/bob") as bob,
        ):
            alice.receive_json()
            bob.receive_json()
            alice.send_json({"type": "trade:quick_emote", "emote_id": "wow", "text": "free text"})
            assert alice.receive_json()["type"] == "trade:error"
            engine.update_offer("alice", room_id, {"math_fragment": 1})
            engine.update_offer("bob", room_id, {"coding_fragment": 1})
            engine.lock("alice", room_id)
            revision = engine.lock("bob", room_id)["revision"]
            alice.send_json({"type": "trade:confirm", "revision": revision})
            bob.send_json({"type": "trade:confirm", "revision": revision})
            for socket in (alice, bob):
                for _ in range(5):
                    frame = socket.receive_json()
                    if frame["type"] == "trade:completed":
                        break
                assert frame["type"] == "trade:completed"


def test_shared_quiz_hides_answers_and_scores_both_players(trade):
    engine, _ = trade
    session_id = engine.pair("bob", engine.issue("alice"))["session_id"]
    engine.update_offer("alice", session_id, {"math_fragment": 1})
    engine.update_offer("bob", session_id, {"coding_fragment": 1})
    engine.lock("alice", session_id)
    revision = engine.lock("bob", session_id)["revision"]
    engine.confirm("alice", session_id, revision)
    engine.confirm("bob", session_id, revision)
    state = engine.hangout(
        "alice",
        session_id,
        {
            "question": "2 + 2?",
            "options": {"A": "4", "B": "6"},
            "correct_answer": "A",
        },
    )
    assert "correct_answer" not in state["question"]
    assert engine.hangout("bob", session_id)["expires_at"] == state["expires_at"]
    assert engine.answer_hangout("alice", session_id, "A")["answered"]
    assert "scores" not in engine.hangout("bob", session_id)
    state = engine.answer_hangout("bob", session_id, "B")
    assert state["scores"] == {"initiator": 1, "responder": 0}
    assert engine.answer_hangout("bob", session_id, "A") == state
