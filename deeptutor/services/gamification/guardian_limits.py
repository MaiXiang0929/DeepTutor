"""PIN-protected supervisor settings and per-learner aggregate reports."""

from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from secrets import token_hex
from time import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import GuardianGameLimits, game_limits


def _hash(pin: str, salt: str) -> str:
    return pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


def set_limits(store, user_id, pin, minutes, trades):
    now = int(time())
    rejected = False
    with Session(store.engine) as session, session.begin():
        session.execute(text("BEGIN IMMEDIATE"))
        limits = session.get(GuardianGameLimits, user_id)
        if limits is None:
            salt = token_hex(16)
            limits = GuardianGameLimits(user_id=user_id, pin_hash=f"{salt}:{_hash(pin, salt)}")
            session.add(limits)
        else:
            salt, digest = limits.pin_hash.split(":")
            if now < limits.locked_until:
                rejected = True
            elif not compare_digest(_hash(pin, salt), digest):
                limits.failed_pins += 1
                if limits.failed_pins >= 5:
                    limits.failed_pins = 0
                    limits.locked_until = now + 300
                rejected = True
        if not rejected:
            limits.game_minutes = minutes
            limits.trades = trades
            limits.failed_pins = 0
            limits.locked_until = 0
    if rejected:
        raise PermissionError("PIN incorrect or temporarily locked")


def get_limits(store, user_id):
    with Session(store.engine) as session:
        minutes, trades = game_limits(session, user_id)
        return {
            "game_minutes": minutes,
            "trades": trades,
            "pin_set": session.get(GuardianGameLimits, user_id) is not None,
        }


def weekly_report(user_id):
    from deeptutor.multi_user.paths import get_path_service_for_scope, scope_for_user
    from deeptutor.services.memory.paths import memory_path_service_override
    from deeptutor.services.memory.trace import iter_since

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=6)
    daily = {
        (start + timedelta(days=i)).date().isoformat(): {"study_seconds": 0, "reward_count": 0}
        for i in range(7)
    }
    seen = set()
    service = get_path_service_for_scope(scope_for_user(user_id, is_admin=False))
    with memory_path_service_override(service):
        for surface in ("chat", "quiz", "book"):
            for event in iter_since(surface, start):
                day = event.ts[:10]
                key = (surface, event.turn_id or event.id)
                if event.kind != "study_completed" or day not in daily or key in seen:
                    continue
                seen.add(key)
                seconds = event.payload.get("duration_seconds")
                if type(seconds) is int and seconds > 0:
                    daily[day]["study_seconds"] += seconds
                if isinstance(event.payload.get("reward"), dict):
                    daily[day]["reward_count"] += 1
    return [{"date": day, **values} for day, values in daily.items()]
