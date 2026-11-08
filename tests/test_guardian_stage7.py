import pytest
from sqlalchemy.orm import Session

from deeptutor.services.gamification.guardian_limits import get_limits, set_limits
from deeptutor.services.gamification.minigames import MiniGames
from deeptutor.services.gamification.models import GameStore, UserGameProfile
from deeptutor.services.gamification.trade_engine import TradeEngine


def test_pin_and_shared_limits_are_enforced(tmp_path):
    game = GameStore(tmp_path / "game.db")
    game.profile("learner")
    with Session(game.engine) as session, session.begin():
        session.get(UserGameProfile, "learner").energy_points = 60
    set_limits(game, "learner", "123456", 0, 0)
    with pytest.raises(PermissionError):
        set_limits(game, "learner", "654321", 60, 10)
    assert get_limits(game, "learner") == {"game_minutes": 0, "trades": 0, "pin_set": True}
    with pytest.raises(ValueError, match="time limit"):
        MiniGames(game).start("learner", "match", "one")
    assert game.profile("learner")["energy_points"] == 60
    trade = TradeEngine(game, "test")
    with pytest.raises(ValueError, match="trade limit"):
        trade.pair("learner", trade.issue("peer"))
    set_limits(game, "learner", "123456", 1, 1)
    assert MiniGames(game).start("learner", "match", "two")["status"] == "active"
    assert trade.pair("learner", trade.issue("peer"))["status"] == "active"
