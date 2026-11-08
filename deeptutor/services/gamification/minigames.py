"""Server-authoritative energy reservation and minigame settlement."""

from contextlib import contextmanager
import random
from time import time
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import (
    GameStore,
    MiniGameRound,
    MobileGameProgress,
    UserInventory,
    _profile,
    game_limits,
)

ENERGY_COST = 15
DURATIONS = {"match": 60, "turtle": 300}
PUZZLES = (
    ("数学 · 7 × 8", "56"),
    ("物理 · 水在标准气压下的沸点", "100 °C"),
    ("文学 · 海内存知己", "天涯若比邻"),
    ("历史 · 秦统一六国", "公元前221年"),
    ("编程 · Python 列表长度", "len(list)"),
    ("英文 · bio-", "生命"),
)
RIDDLES = [
    (
        "为什么同一杯水，放在高山上会比海边更早沸腾？",
        "海拔高导致空气稀薄，外界气压较低，水的沸点下降。",
    ),
    (
        "同一根吸管插入清水，看起来却在水面折断了，为什么？",
        "光从水进入空气时速度改变并折射，视觉把光沿直线反推，水下吸管看起来偏移。",
    ),
]


class MiniGames:
    def __init__(self, store: GameStore):
        self.store = store

    @contextmanager
    def _write(self):
        with Session(self.store.engine) as session, session.begin():
            session.execute(text("BEGIN IMMEDIATE"))
            yield session

    def _get(self, session, user_id, round_id):
        round = session.get(MiniGameRound, round_id)
        if round is None or round.user_id != user_id:
            raise LookupError("Game not found")
        return round

    def _progress(self, session, user_id):
        progress = session.get(MobileGameProgress, user_id)
        if progress is None:
            progress = MobileGameProgress(user_id=user_id, coins=0, affinity=0)
            session.add(progress)
        return progress

    def _expire(self, session, round):
        if round.status == "active" and time() >= round.expires_at:
            self._settle(session, round, "expired")

    def _public(self, session, round):
        progress = self._progress(session, round.user_id)
        result = {
            "id": round.id,
            "mode": round.mode,
            "status": round.status,
            "expires_at": round.expires_at,
            "version": round.version,
            "score": round.score,
            "coins": progress.coins,
            "affinity": progress.affinity,
            "last_answer": round.last_answer,
        }
        if round.mode == "match":
            result.update(left=round.payload["left"], right=round.payload["right"])
        else:
            result["prompt"] = round.payload["prompt"]
            if round.status != "active":
                result["explanation"] = round.payload["truth"]
        return result

    def _settle(self, session, round, status):
        if round.status != "active":
            return
        round.status = status
        progress = self._progress(session, round.user_id)
        if round.mode == "match":
            progress.coins += round.score
            progress.affinity += 2 * round.score
        elif status == "completed":
            progress.affinity += 10
            session.add(
                UserInventory(
                    user_id=round.user_id,
                    item_id="physics_rare_fragment",
                    quantity=1,
                    acquired_source="minigame",
                )
            )

    def start(self, user_id, mode, request_id):
        if mode not in DURATIONS:
            raise ValueError("Unknown game")
        with self._write() as session:
            existing = session.scalar(
                select(MiniGameRound).where(
                    MiniGameRound.user_id == user_id, MiniGameRound.request_id == request_id
                )
            )
            if existing:
                if existing.mode != mode:
                    raise ValueError("Start request ID is already used")
                self._expire(session, existing)
                return self._public(session, existing)
            for current in session.scalars(
                select(MiniGameRound).where(
                    MiniGameRound.user_id == user_id, MiniGameRound.status == "active"
                )
            ):
                self._expire(session, current)
                if current.status == "active":
                    raise ValueError("Finish the active game first")
            profile = _profile(session, user_id)
            if profile.energy_points < ENERGY_COST:
                raise ValueError("Not enough energy")
            minutes = DURATIONS[mode] // 60
            if profile.daily_game_minutes_used + minutes > game_limits(session, user_id)[0]:
                raise ValueError("Daily game time limit reached")
            profile.energy_points -= ENERGY_COST
            profile.daily_game_minutes_used += minutes
            if mode == "match":
                left = [{"id": uuid4().hex, "label": a} for a, _ in PUZZLES]
                right = [{"id": uuid4().hex, "label": b} for _, b in PUZZLES]
                pairs = {a["id"]: b["id"] for a, b in zip(left, right)}
                random.shuffle(left)
                random.shuffle(right)
                payload = {"left": left, "right": right, "pairs": pairs}
            else:
                prompt, truth = random.choice(RIDDLES)
                payload = {"prompt": prompt, "truth": truth}
            round = MiniGameRound(
                id=uuid4().hex,
                user_id=user_id,
                mode=mode,
                request_id=request_id,
                expires_at=int(time()) + DURATIONS[mode],
                payload=payload,
            )
            session.add(round)
            session.flush()
            return self._public(session, round)

    def state(self, user_id, round_id):
        with self._write() as session:
            round = self._get(session, user_id, round_id)
            self._expire(session, round)
            return self._public(session, round)

    def _check_move(self, session, user_id, round_id, mode, version):
        round = self._get(session, user_id, round_id)
        if round.status != "active" or round.mode != mode or round.version != version:
            raise ValueError("Game state changed")
        return round

    def match(self, user_id, round_id, left, right, version):
        with self._write() as session:
            round = self._check_move(session, user_id, round_id, "match", version)
            self._expire(session, round)
            if round.status != "active":
                return self._public(session, round)
            if round.payload["pairs"].get(left) != right:
                raise ValueError("The items do not match")
            pairs = {key: value for key, value in round.payload["pairs"].items() if key != left}
            round.payload = {
                "pairs": pairs,
                "left": [item for item in round.payload["left"] if item["id"] != left],
                "right": [item for item in round.payload["right"] if item["id"] != right],
            }
            round.score += 1
            round.version += 1
            if not pairs:
                self._settle(session, round, "completed")
            return self._public(session, round)

    def riddle(self, user_id, round_id, version):
        with Session(self.store.engine) as session:
            round = self._check_move(session, user_id, round_id, "turtle", version)
            if time() >= round.expires_at:
                raise ValueError("Game expired")
            return round.payload["prompt"], round.payload["truth"]

    def answer(self, user_id, round_id, verdict, guess, version):
        with self._write() as session:
            round = self._check_move(session, user_id, round_id, "turtle", version)
            self._expire(session, round)
            if round.status != "active":
                return self._public(session, round)
            round.version += 1
            round.last_answer = verdict
            if guess and verdict == "yes":
                round.score = 1
                self._settle(session, round, "completed")
            elif round.version >= 10:
                self._settle(session, round, "lost")
            return self._public(session, round)
