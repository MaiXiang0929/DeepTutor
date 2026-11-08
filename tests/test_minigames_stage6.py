import pytest
from sqlalchemy.orm import Session

from deeptutor.services.gamification.models import GameStore, UserGameProfile


def test_match_spends_once_and_settles_server_validated_moves(tmp_path):
    from deeptutor.services.gamification.minigames import MiniGames

    game = GameStore(tmp_path / "game.db")
    engine = MiniGames(game)
    game.profile("alice")
    with pytest.raises(ValueError, match="energy"):
        engine.start("alice", "match", "one")
    with Session(game.engine) as session, session.begin():
        session.get(UserGameProfile, "alice").energy_points = 30
    round = engine.start("alice", "match", "one")
    assert engine.start("alice", "match", "one") == round
    assert game.profile("alice")["energy_points"] == 15
    assert game.profile("alice")["daily_game_minutes_used"] == 1
    from deeptutor.services.gamification.minigames import PUZZLES

    for left, right in PUZZLES:
        left_id = next(item["id"] for item in round["left"] if item["label"] == left)
        right_id = next(item["id"] for item in round["right"] if item["label"] == right)
        round = engine.match("alice", round["id"], left_id, right_id, round["version"])
    assert round["status"] == "completed"
    assert round["coins"] == 6
    assert round["affinity"] == 12
    with pytest.raises(ValueError):
        engine.match("alice", round["id"], "0", "0", round["version"])


def test_turtle_reward_cannot_settle_twice(tmp_path):
    from deeptutor.services.gamification.minigames import MiniGames

    game = GameStore(tmp_path / "game.db")
    game.profile("alice")
    with Session(game.engine) as session, session.begin():
        session.get(UserGameProfile, "alice").energy_points = 15
    engine = MiniGames(game)
    round = engine.start("alice", "turtle", "one")
    solved = engine.answer("alice", round["id"], "yes", True, round["version"])
    assert solved["status"] == "completed"
    assert game.profile("alice")["inventory"][0]["rarity"] == "rare"
    with pytest.raises(ValueError):
        engine.answer("alice", round["id"], "yes", True, round["version"])
