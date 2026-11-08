"""SQLite-backed game profiles, catalog and transactional inventory."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
import random

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from deeptutor.runtime.home import get_runtime_home

SUBJECTS = ("math", "physics", "literature", "history", "coding")
DAILY_GAME_MINUTES = 60


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class UserGameProfile(Base):
    __tablename__ = "game_profiles"
    __table_args__ = (
        CheckConstraint("energy_points >= 0"),
        CheckConstraint("daily_game_minutes_used >= 0"),
        CheckConstraint("daily_trade_count >= 0"),
        CheckConstraint("lucky_subject IN ('math','physics','literature','history','coding')"),
    )
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    energy_points: Mapped[int] = mapped_column(default=0)
    lucky_subject: Mapped[str] = mapped_column(String)
    daily_game_minutes_used: Mapped[int] = mapped_column(default=0)
    daily_trade_count: Mapped[int] = mapped_column(default=0)
    daily_date: Mapped[date] = mapped_column(Date, default=date.today)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ItemCatalog(Base):
    __tablename__ = "item_catalog"
    __table_args__ = (
        CheckConstraint("category IN ('card_fragment','companion_skin','room_decor','badge')"),
        CheckConstraint("rarity IN ('common','rare','epic','legendary')"),
    )
    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    subject_tag: Mapped[str] = mapped_column(String)
    rarity: Mapped[str] = mapped_column(String)
    synthesis_recipe_json: Mapped[list] = mapped_column(JSON, default=list)


class UserInventory(Base):
    __tablename__ = "user_inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0"),
        CheckConstraint("acquired_source IN ('desktop_study','minigame','nfc_trade','synthesis')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("item_catalog.item_id"))
    quantity: Mapped[int] = mapped_column(default=1)
    is_equipped: Mapped[bool] = mapped_column(Boolean, default=False)
    acquired_source: Mapped[str] = mapped_column(String)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RewardReceipt(Base):
    __tablename__ = "game_reward_receipts"
    __table_args__ = (UniqueConstraint("user_id", "event_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    event_id: Mapped[str] = mapped_column(String)
    reward: Mapped[dict] = mapped_column(JSON)


class TradeSession(Base):
    __tablename__ = "game_trade_sessions"
    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    initiator_user_id: Mapped[str] = mapped_column(String)
    responder_user_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    initiator_items_json: Mapped[dict] = mapped_column(JSON, default=dict)
    responder_items_json: Mapped[dict] = mapped_column(JSON, default=dict)
    initiator_locked: Mapped[bool] = mapped_column(default=False)
    responder_locked: Mapped[bool] = mapped_column(default=False)
    initiator_confirmed: Mapped[bool] = mapped_column(default=False)
    responder_confirmed: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=0)
    quick_emote: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hangout_question: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    synthesis_unlocks: Mapped[dict] = mapped_column(JSON, default=dict)


class MiniGameRound(Base):
    __tablename__ = "game_minigame_rounds"
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    request_id: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    expires_at: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(default=0)
    payload: Mapped[dict] = mapped_column(JSON)
    score: Mapped[int] = mapped_column(default=0)
    last_answer: Mapped[str | None] = mapped_column(String, nullable=True)


class MobileGameProgress(Base):
    __tablename__ = "game_mobile_progress"
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    coins: Mapped[int] = mapped_column(default=0)
    affinity: Mapped[int] = mapped_column(default=0)


class GameCompanion(Base):
    __tablename__ = "game_companion_identity"
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    partner_id: Mapped[str] = mapped_column(String)
    persona_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)


class GuardianGameLimits(Base):
    __tablename__ = "game_guardian_limits"
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    game_minutes: Mapped[int] = mapped_column(default=DAILY_GAME_MINUTES)
    trades: Mapped[int] = mapped_column(default=10)
    pin_hash: Mapped[str] = mapped_column(String)
    failed_pins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[int] = mapped_column(default=0)


def game_limits(session, user_id):
    limits = session.get(GuardianGameLimits, user_id)
    return (limits.game_minutes, limits.trades) if limits else (DAILY_GAME_MINUTES, 10)


def _profile(session, user_id):
    session.execute(
        insert(UserGameProfile)
        .values(
            user_id=user_id,
            lucky_subject=random.choice(SUBJECTS),
            energy_points=0,
            daily_game_minutes_used=0,
            daily_trade_count=0,
            daily_date=date.today(),
            updated_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    profile = session.get(UserGameProfile, user_id)
    if profile.daily_date != date.today():
        profile.daily_date = date.today()
        profile.daily_game_minutes_used = 0
        profile.daily_trade_count = 0
        profile.updated_at = utcnow()
    return profile


class GameStore:
    def __init__(self, path=None):
        path = Path(path or get_runtime_home() / "data" / "user" / "gamification.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})
        seeds = [
            dict(
                item_id=f"{subject}_fragment",
                name=f"{subject} fragment",
                category="card_fragment",
                subject_tag=subject,
                rarity="common",
                synthesis_recipe_json=[],
            )
            for subject in SUBJECTS
        ]
        seeds.extend(
            [
                dict(
                    item_id="math_skin",
                    name="Math skin",
                    category="companion_skin",
                    subject_tag="math",
                    rarity="rare",
                    synthesis_recipe_json=["math_fragment", "math_fragment"],
                ),
                dict(
                    item_id="physics_rare_fragment",
                    name="Refraction prism",
                    category="card_fragment",
                    subject_tag="physics",
                    rarity="rare",
                    synthesis_recipe_json=[],
                ),
                dict(
                    item_id="spectrum_skin",
                    name="Spectrum skin",
                    category="companion_skin",
                    subject_tag="physics",
                    rarity="epic",
                    synthesis_recipe_json=["math_fragment", "physics_fragment", "coding_fragment"],
                ),
                dict(
                    item_id="coding_badge",
                    name="Coding badge",
                    category="badge",
                    subject_tag="coding",
                    rarity="rare",
                    synthesis_recipe_json=["coding_fragment", "coding_fragment"],
                ),
            ]
        )
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                Base.metadata.create_all(connection)
                connection.execute(
                    insert(ItemCatalog)
                    .values(seeds)
                    .on_conflict_do_nothing(index_elements=["item_id"])
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def catalog(self):
        with Session(self.engine) as s:
            return [
                dict(
                    item_id=x.item_id,
                    name=x.name,
                    category=x.category,
                    subject_tag=x.subject_tag,
                    rarity=x.rarity,
                    synthesis_recipe_json=x.synthesis_recipe_json,
                )
                for x in s.scalars(select(ItemCatalog))
            ]

    def add_item(self, user_id, item_id, source):
        with Session(self.engine) as s, s.begin():
            if not s.get(ItemCatalog, item_id):
                raise ValueError("Unknown item")
            s.add(
                UserInventory(user_id=user_id, item_id=item_id, quantity=1, acquired_source=source)
            )

    def select_companion(self, user_id, partner_id, persona_id, name):
        with Session(self.engine) as session, session.begin():
            session.merge(
                GameCompanion(
                    user_id=user_id,
                    partner_id=partner_id,
                    persona_id=persona_id,
                    name=name,
                )
            )

    def profile(self, user_id):
        with Session(self.engine) as s, s.begin():
            p = _profile(s, user_id)
            companion = s.get(GameCompanion, user_id)
            rows = s.execute(
                select(UserInventory, ItemCatalog)
                .join(ItemCatalog, UserInventory.item_id == ItemCatalog.item_id)
                .where(UserInventory.user_id == user_id, UserInventory.quantity > 0)
            ).all()
            inventory = [
                dict(
                    id=row.id,
                    item_id=row.item_id,
                    quantity=row.quantity,
                    is_equipped=row.is_equipped,
                    acquired_source=row.acquired_source,
                    acquired_at=row.acquired_at.isoformat(),
                    name=item.name,
                    category=item.category,
                    subject_tag=item.subject_tag,
                    rarity=item.rarity,
                )
                for row, item in rows
            ]
            return dict(
                user_id=user_id,
                companion=(
                    {
                        "partner_id": companion.partner_id,
                        "persona_id": companion.persona_id,
                        "name": companion.name,
                    }
                    if companion
                    else None
                ),
                energy_points=p.energy_points,
                lucky_subject=p.lucky_subject,
                daily_game_minutes_used=p.daily_game_minutes_used,
                daily_trade_count=p.daily_trade_count,
                daily_game_minutes_remaining=max(
                    0, game_limits(s, user_id)[0] - p.daily_game_minutes_used
                ),
                inventory=inventory,
            )

    def grant_reward(self, user_id, event_id, energy, chooser):
        with Session(self.engine) as s:
            s.execute(text("BEGIN IMMEDIATE"))
            try:
                receipt = (
                    s.scalar(
                        select(RewardReceipt).where(
                            RewardReceipt.user_id == user_id, RewardReceipt.event_id == event_id
                        )
                    )
                    if event_id
                    else None
                )
                if receipt:
                    return receipt.reward
                p = _profile(s, user_id)
                subject = chooser(p.lucky_subject)
                item = s.get(ItemCatalog, f"{subject}_fragment")
                p.energy_points += energy
                p.updated_at = utcnow()
                s.add(
                    UserInventory(
                        user_id=user_id,
                        item_id=item.item_id,
                        quantity=1,
                        acquired_source="desktop_study",
                    )
                )
                reward = {
                    "energy_points": energy,
                    "item": {
                        "item_id": item.item_id,
                        "name": item.name,
                        "category": item.category,
                        "subject_tag": subject,
                        "rarity": item.rarity,
                        "quantity": 1,
                    },
                }
                if event_id:
                    s.add(RewardReceipt(user_id=user_id, event_id=event_id, reward=reward))
                s.commit()
                return reward
            except Exception:
                s.rollback()
                raise

    def synthesize(self, user_id, target_item_id):
        with Session(self.engine) as s:
            s.execute(text("BEGIN IMMEDIATE"))
            try:
                target = s.get(ItemCatalog, target_item_id)
                if (
                    not target
                    or target.category not in ("companion_skin", "badge")
                    or not target.synthesis_recipe_json
                ):
                    raise ValueError("Invalid synthesis target")
                for item_id, count in Counter(target.synthesis_recipe_json).items():
                    ingredient = s.get(ItemCatalog, item_id)
                    if ingredient is None or ingredient.category != "card_fragment":
                        raise ValueError("Invalid synthesis recipe")
                    rows = s.scalars(
                        select(UserInventory)
                        .where(
                            UserInventory.user_id == user_id,
                            UserInventory.item_id == item_id,
                            UserInventory.quantity > 0,
                        )
                        .order_by(UserInventory.id)
                    ).all()
                    if sum(row.quantity for row in rows) < count:
                        raise ValueError("Insufficient fragments")
                    for row in rows:
                        used = min(row.quantity, count)
                        row.quantity -= used
                        count -= used
                        if not count:
                            break
                s.add(
                    UserInventory(
                        user_id=user_id,
                        item_id=target_item_id,
                        quantity=1,
                        acquired_source="synthesis",
                    )
                )
                s.commit()
            except Exception:
                s.rollback()
                raise

    def equip(self, user_id, item_id, equipped):
        with Session(self.engine) as s:
            s.execute(text("BEGIN IMMEDIATE"))
            try:
                item = s.get(ItemCatalog, item_id)
                if item is None or item.category not in ("companion_skin", "room_decor"):
                    raise ValueError("Item cannot be equipped")
                rows = s.scalars(
                    select(UserInventory).where(
                        UserInventory.user_id == user_id,
                        UserInventory.item_id == item_id,
                        UserInventory.quantity > 0,
                    )
                ).all()
                if not rows:
                    raise ValueError("Item not owned")
                if equipped:
                    others = s.scalars(
                        select(UserInventory)
                        .join(ItemCatalog, UserInventory.item_id == ItemCatalog.item_id)
                        .where(
                            UserInventory.user_id == user_id,
                            ItemCatalog.category == item.category,
                            UserInventory.is_equipped.is_(True),
                        )
                    ).all()
                    for row in others:
                        row.is_equipped = False
                    rows[0].is_equipped = True
                else:
                    for row in rows:
                        row.is_equipped = False
                s.commit()
            except Exception:
                s.rollback()
                raise
