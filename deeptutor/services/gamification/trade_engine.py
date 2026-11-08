"""Short-lived pairing and SQLite-serialized inventory transfers."""

import base64
from collections import Counter
from contextlib import contextmanager
import hashlib
import hmac
import json
import secrets
from time import time

from sqlalchemy import select, text
from sqlalchemy.orm import Session, object_session

from .models import (
    GameCompanion,
    GameStore,
    ItemCatalog,
    TradeSession,
    UserInventory,
    _profile,
    game_limits,
)

QUICK_EMOTES = frozenset({"thumbs_up", "please", "thank_you", "wow"})
TOKEN_SECONDS = 60
ROOM_SECONDS = 180


class TradeEngine:
    def __init__(self, store: GameStore, secret: str):
        self.store = store
        self.key = hmac.digest(secret.encode(), b"deeptutor-trade-v1", hashlib.sha256)

    def _signature(self, body: str) -> str:
        return hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()

    def issue(self, user_id: str, *, now: float | None = None) -> str:
        now = time() if now is None else now
        payload = {
            "user_id": user_id,
            "nonce": secrets.token_hex(16),
            "exp": int(now) + TOKEN_SECONDS,
        }
        body = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
        return f"{body}.{self._signature(body)}"

    @contextmanager
    def _write(self):
        with Session(self.store.engine) as session, session.begin():
            session.execute(text("BEGIN IMMEDIATE"))
            yield session

    def _quota(self, session, user_id):
        profile = _profile(session, user_id)
        if profile.daily_trade_count >= game_limits(session, user_id)[1]:
            raise ValueError("Daily trade limit reached")
        return profile

    def pair(self, user_id, token, *, now=None):
        now = time() if now is None else now
        body, _, sig = token.partition(".")
        if not hmac.compare_digest(sig.encode(), self._signature(body).encode()):
            raise ValueError("Invalid handshake signature")
        payload = json.loads(base64.urlsafe_b64decode(body))
        if now >= payload["exp"]:
            raise ValueError("Handshake expired")
        other = payload["user_id"]
        if other == user_id:
            raise ValueError("Trade requires two accounts")
        with self._write() as session:
            if session.get(TradeSession, payload["nonce"]):
                raise ValueError("Handshake already used")
            self._quota(session, other)
            self._quota(session, user_id)
            room = TradeSession(
                session_id=payload["nonce"],
                initiator_user_id=other,
                responder_user_id=user_id,
                created_at=int(now),
                expires_at=int(now) + ROOM_SECONDS,
            )
            session.add(room)
            session.flush()
            return self._state(room, user_id)

    def _room(self, session, user_id, room_id):
        room = session.get(TradeSession, room_id)
        if room is None or user_id not in (room.initiator_user_id, room.responder_user_id):
            raise LookupError("Trade room not found")
        return room

    def _side(self, room, user_id):
        return "initiator" if room.initiator_user_id == user_id else "responder"

    def _state(self, room, user_id):
        result = {
            name: getattr(room, name)
            for name in (
                "session_id",
                "status",
                "initiator_items_json",
                "responder_items_json",
                "initiator_locked",
                "responder_locked",
                "initiator_confirmed",
                "responder_confirmed",
                "expires_at",
                "revision",
                "version",
                "quick_emote",
            )
        }
        if room.status in ("active", "locked") and time() >= room.expires_at:
            result["status"] = "expired"
        result["side"] = self._side(room, user_id)
        result["synthesis_unlocks"] = room.synthesis_unlocks.get(result["side"], [])
        peer_id = (
            room.responder_user_id if result["side"] == "initiator" else room.initiator_user_id
        )
        peer = object_session(room).get(GameCompanion, peer_id)
        result["peer_companion"] = (
            {"name": peer.name, "persona_id": peer.persona_id} if peer else None
        )
        return result

    def state(self, user_id, room_id):
        with Session(self.store.engine) as session:
            return self._state(self._room(session, user_id, room_id), user_id)

    def _editable(self, room):
        if time() >= room.expires_at:
            raise ValueError("Trade expired")
        if room.status not in ("active", "locked"):
            raise ValueError("Trade is closed")

    def _inventory(self, session, user, items):
        available = {}
        for item_id, quantity in items.items():
            rows = session.scalars(
                select(UserInventory)
                .where(
                    UserInventory.user_id == user,
                    UserInventory.item_id == item_id,
                    UserInventory.quantity > 0,
                    UserInventory.is_equipped.is_(False),
                )
                .order_by(UserInventory.id)
            ).all()
            if sum(row.quantity for row in rows) < quantity:
                raise ValueError("Insufficient unequipped inventory")
            available[item_id] = rows
        return available

    def update_offer(self, user_id, room_id, items):
        if (
            not items
            or any(type(qty) is not int or qty < 1 for qty in items.values())
            or sum(items.values()) > 3
        ):
            raise ValueError("Offer must contain 1 to 3 items")
        with self._write() as session:
            room = self._room(session, user_id, room_id)
            self._editable(room)
            self._inventory(session, user_id, items)
            setattr(room, f"{self._side(room, user_id)}_items_json", dict(items))
            room.initiator_locked = room.responder_locked = False
            room.initiator_confirmed = room.responder_confirmed = False
            room.status = "active"
            room.revision += 1
            room.version += 1
            return self._state(room, user_id)

    def lock(self, user_id, room_id, revision=None):
        with self._write() as session:
            room = self._room(session, user_id, room_id)
            self._editable(room)
            if revision is not None and revision != room.revision:
                raise ValueError("Offer changed")
            if not room.initiator_items_json or not room.responder_items_json:
                raise ValueError("Both sides must submit offers")
            setattr(room, f"{self._side(room, user_id)}_locked", True)
            if room.initiator_locked and room.responder_locked:
                room.status = "locked"
            room.version += 1
            return self._state(room, user_id)

    def confirm(self, user_id, room_id, revision):
        with self._write() as session:
            room = self._room(session, user_id, room_id)
            if room.status == "completed":
                return self._state(room, user_id)
            self._editable(room)
            if room.status != "locked" or revision != room.revision:
                raise ValueError("Lock the current offer before confirming")
            setattr(room, f"{self._side(room, user_id)}_confirmed", True)
            if room.initiator_confirmed and room.responder_confirmed:
                self._exchange(session, room)
                room.status = "completed"
            room.version += 1
            return self._state(room, user_id)

    def _exchange(self, session, room):
        users = [room.initiator_user_id, room.responder_user_id]
        offers = [room.initiator_items_json, room.responder_items_json]
        inventory = [self._inventory(session, user, offer) for user, offer in zip(users, offers)]
        before = [self._available_recipes(session, user) for user in users]
        for user in users:
            self._quota(session, user).daily_trade_count += 1
        for idx, offer in enumerate(offers):
            for item_id, quantity in offer.items():
                remaining = quantity
                for row in inventory[idx][item_id]:
                    deducted = min(remaining, row.quantity)
                    row.quantity -= deducted
                    remaining -= deducted
                    if not remaining:
                        break
                session.add(
                    UserInventory(
                        user_id=users[1 - idx],
                        item_id=item_id,
                        quantity=quantity,
                        acquired_source="nfc_trade",
                    )
                )

        session.flush()
        room.synthesis_unlocks = {
            side: sorted(self._available_recipes(session, user) - previous)
            for side, user, previous in zip(("initiator", "responder"), users, before)
        }

    def _available_recipes(self, session, user_id):
        inventory = Counter()
        for item in session.scalars(select(UserInventory).where(UserInventory.user_id == user_id)):
            inventory[item.item_id] += item.quantity
        return {
            item.item_id
            for item in session.scalars(
                select(ItemCatalog).where(ItemCatalog.category.in_(("companion_skin", "badge")))
            )
            if item.synthesis_recipe_json and Counter(item.synthesis_recipe_json) <= inventory
        }

    def cancel(self, user_id, room_id):
        with self._write() as session:
            room = self._room(session, user_id, room_id)
            if room.status in ("active", "locked"):
                room.status = "expired" if time() >= room.expires_at else "cancelled"
                room.version += 1
            return self._state(room, user_id)

    def emote(self, user_id, room_id, emote_id):
        if emote_id not in QUICK_EMOTES:
            raise ValueError("Unknown quick emote")
        with self._write() as session:
            room = self._room(session, user_id, room_id)
            self._editable(room)
            room.version += 1
            room.quick_emote = {
                "side": self._side(room, user_id),
                "emote_id": emote_id,
                "seq": room.version,
            }
            return self._state(room, user_id)

    def _quiz_state(self, room, user_id):
        quiz = room.hangout_question
        question = quiz["question"]
        entries = quiz["answers"]
        side = self._side(room, user_id)
        finished = len(entries) == 2 or time() >= quiz["expires_at"]
        result = {
            "duration_seconds": 90,
            "expires_at": quiz["expires_at"],
            "question": {"question": question["question"], "options": question["options"]},
            "answered": side in entries,
            "finished": finished,
        }
        if finished:
            correct = question["correct_answer"]
            result["scores"] = {
                participant: int(answer == correct or question["options"].get(answer) == correct)
                for participant, answer in entries.items()
            }
        return result

    def hangout(self, user_id, room_id, question=None):
        with self._write() as session:
            room = self._room(session, user_id, room_id)
            if room.status != "completed":
                raise ValueError("Complete the exchange before starting a hangout")
            if question is not None and room.hangout_question is None:
                room.hangout_question = {
                    "question": question,
                    "answers": {},
                    "expires_at": int(time()) + 90,
                }
            return self._quiz_state(room, user_id) if room.hangout_question else None

    def answer_hangout(self, user_id, room_id, answer):
        with self._write() as session:
            room = self._room(session, user_id, room_id)
            quiz = room.hangout_question
            if not quiz:
                raise ValueError("Start the quiz first")
            if time() >= quiz["expires_at"]:
                return self._quiz_state(room, user_id)
            if answer not in quiz["question"]["options"]:
                raise ValueError("Unknown answer")
            answers = dict(quiz["answers"])
            answers.setdefault(self._side(room, user_id), answer)
            room.hangout_question = {**quiz, "answers": answers}
            return self._quiz_state(room, user_id)
