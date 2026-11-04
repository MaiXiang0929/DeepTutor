"""Durable capture receipts and bounded temporary image storage.

SQLite transactions make retries and quotas consistent across API workers.
Only hashes of browser ownership keys and phone capabilities are persisted.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


class CaptureError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def normalize_image(data: bytes) -> tuple[bytes, str, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise CaptureError("Use JPEG, PNG or WebP images. Convert HEIC photos first.")
                if source.width * source.height > 40_000_000:
                    raise CaptureError("Image exceeds the 40 megapixel limit.", 413)
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    flat = Image.new("RGB", rgba.size, "white")
                    flat.paste(rgba, mask=rgba.getchannel("A"))
                    image = flat
                else:
                    image = image.convert("RGB")
                # No source metadata is copied into the normalized image.
                image.save(out, "JPEG", quality=85)
                return out.getvalue(), "image/jpeg", "jpg"
    except CaptureError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise CaptureError("The photo could not be decoded. Choose another image.") from exc


class CaptureStore:
    def __init__(self, path: Path, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS captures (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, token TEXT UNIQUE NOT NULL,
                    target TEXT NOT NULL, title TEXT NOT NULL, created REAL NOT NULL,
                    expires REAL NOT NULL, hard_expires REAL NOT NULL,
                    max_file INTEGER NOT NULL, max_total INTEGER NOT NULL,
                    closed INTEGER NOT NULL DEFAULT 0, paused INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS capture_files (
                    id TEXT PRIMARY KEY, capture_id TEXT NOT NULL REFERENCES captures(id)
                    ON DELETE CASCADE, client_id TEXT NOT NULL, filename TEXT NOT NULL,
                    size INTEGER NOT NULL, state TEXT NOT NULL, data BLOB,
                    UNIQUE(capture_id, client_id)
                );
                CREATE INDEX IF NOT EXISTS capture_files_session ON capture_files(capture_id);
                CREATE TABLE IF NOT EXISTS capture_receivers (id TEXT PRIMARY KEY, seen REAL NOT NULL);
            """)
            db.execute("BEGIN IMMEDIATE")
            if "receiver_id" not in {
                row["name"] for row in db.execute("PRAGMA table_info(captures)")
            }:
                db.execute("ALTER TABLE captures ADD COLUMN receiver_id TEXT NOT NULL DEFAULT ''")
        self.cleanup()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _owner(self, db, owner, capture_id):
        row = db.execute(
            "SELECT * FROM captures WHERE id=? AND owner=?", (capture_id, digest(owner))
        ).fetchone()
        if row is None:
            raise CaptureError("Capture session not found.", 404)
        return row

    def _phone(self, db, token):
        row = db.execute("SELECT * FROM captures WHERE token=?", (digest(token),)).fetchone()
        if row is None or not self._active(db, row):
            raise CaptureError("This upload link has expired. Scan a new QR code.", 410)
        return row

    def _active(self, db, row):
        if row["closed"] or row["expires"] <= self.clock():
            return False
        if row["receiver_id"]:
            receiver = db.execute(
                "SELECT seen FROM capture_receivers WHERE id=?", (row["receiver_id"],)
            ).fetchone()
            return bool(receiver and receiver["seen"] > self.clock() - 30)
        return True

    def create(self, owner, target, title, max_file_bytes, max_total_bytes):
        self.cleanup()
        now = self.clock()
        capture_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT COUNT(*) FROM captures WHERE closed=0 AND expires>?", (now,)
            ).fetchone()[0]
            owned = db.execute(
                "SELECT COUNT(*) FROM captures WHERE owner=? AND closed=0 AND expires>?",
                (digest(owner), now),
            ).fetchone()[0]
            if active >= 64 or owned >= 4:
                raise CaptureError("End an existing capture session before starting another.", 429)
            db.execute(
                "INSERT INTO captures(id,owner,token,target,title,created,expires,hard_expires,"
                "max_file,max_total) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    capture_id,
                    digest(owner),
                    digest(token),
                    target,
                    title,
                    now,
                    now + 300,
                    now + 3600,
                    max_file_bytes,
                    max_total_bytes,
                ),
            )
        return {
            "id": capture_id,
            "phone_token": token,
            "expires_at": now + 300,
            "target": target,
            "title": title,
        }

    def _status(self, db, row):
        files = [
            dict(item)
            for item in db.execute(
                "SELECT id,client_id,filename,size,state FROM capture_files WHERE capture_id=? ORDER BY rowid",
                (row["id"],),
            )
        ]
        return {
            "id": row["id"],
            "target": row["target"],
            "title": row["title"],
            "active": self._active(db, row),
            "paused": bool(row["paused"]),
            "expires_at": row["expires"],
            "max_file_bytes": row["max_file"],
            "max_total_bytes": row["max_total"],
            "pending_bytes": sum(f["size"] for f in files if f["state"] != "consumed"),
            "files": files,
        }

    def phone_status(self, token):
        with self._db() as db:
            return self._status(db, self._phone(db, token))

    def status(self, owner, capture_id):
        with self._db() as db:
            return self._status(db, self._owner(db, owner, capture_id))

    def upload(self, token, client_id, data):
        with self._db() as db:
            row = self._phone(db, token)
            prior = db.execute(
                "SELECT id,state FROM capture_files WHERE capture_id=? AND client_id=?",
                (row["id"], client_id),
            ).fetchone()
            if prior:
                return dict(prior)
            if len(data) > row["max_file"]:
                raise CaptureError("Photo exceeds the file size limit.", 413)
        normalized, _, ext = normalize_image(data)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._phone(db, token)
            prior = db.execute(
                "SELECT id,state FROM capture_files WHERE capture_id=? AND client_id=?",
                (row["id"], client_id),
            ).fetchone()
            if prior:
                return dict(prior)
            if row["paused"]:
                raise CaptureError(
                    "Return to the target conversation on the computer to continue.", 409
                )
            count, size = db.execute(
                "SELECT COALESCE(SUM(CASE WHEN state='received' THEN 1 ELSE 0 END),0),"
                "COALESCE(SUM(size),0) FROM capture_files "
                "WHERE capture_id=? AND state!='consumed'",
                (row["id"],),
            ).fetchone()
            if (
                count >= 10
                or size + len(normalized) > row["max_total"]
                or len(normalized) > row["max_file"]
            ):
                raise CaptureError(
                    "Upload queue is full. Send or remove attachments on the computer first.", 413
                )
            total = db.execute(
                "SELECT COUNT(*) FROM capture_files WHERE capture_id=?", (row["id"],)
            ).fetchone()[0]
            if total >= 500:
                raise CaptureError("Start a new capture session to upload more photos.", 429)
            file_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO capture_files VALUES(?,?,?,?,?,?,?)",
                (
                    file_id,
                    row["id"],
                    client_id,
                    f"photo-{total + 1}.{ext}",
                    len(normalized),
                    "received",
                    normalized,
                ),
            )
            db.execute(
                "UPDATE captures SET expires=? WHERE id=?",
                (min(self.clock() + 300, row["hard_expires"]), row["id"]),
            )
            return {"id": file_id, "state": "received"}

    def file(self, owner, capture_id, file_id):
        with self._db() as db:
            self._owner(db, owner, capture_id)
            row = db.execute(
                "SELECT data,filename FROM capture_files WHERE capture_id=? AND id=?",
                (capture_id, file_id),
            ).fetchone()
            if row is None or row["data"] is None:
                raise CaptureError("Photo is no longer pending.", 404)
            return row["data"], row["filename"]

    def ack(self, owner, capture_id, file_id):
        with self._db() as db:
            self._owner(db, owner, capture_id)
            db.execute(
                "UPDATE capture_files SET state='attached' WHERE capture_id=? AND id=? AND state='received'",
                (capture_id, file_id),
            )

    def consume(self, owner, capture_id, file_id):
        """Release the recovery copy only after explicit sending/removal."""
        with self._db() as db:
            self._owner(db, owner, capture_id)
            db.execute(
                "UPDATE capture_files SET state='consumed',data=NULL WHERE capture_id=? AND id=?",
                (capture_id, file_id),
            )

    def set_paused(self, owner, capture_id, paused):
        with self._db() as db:
            self._owner(db, owner, capture_id)
            db.execute("UPDATE captures SET paused=? WHERE id=?", (int(paused), capture_id))

    def close(self, owner, capture_id):
        with self._db() as db:
            self._owner(db, owner, capture_id)
            db.execute("UPDATE captures SET closed=1 WHERE id=?", (capture_id,))
            db.execute("DELETE FROM capture_files WHERE capture_id=?", (capture_id,))

    def cleanup(self):
        with self._db() as db:
            db.execute(
                "DELETE FROM captures WHERE expires<? OR (closed=1 AND expires<?)",
                (self.clock() - 3600, self.clock() - 600),
            )
            db.execute("DELETE FROM capture_receivers WHERE seen<?", (self.clock() - 3600,))

    def has_active(self, receiver_id=None):
        with self._db() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM captures c LEFT JOIN capture_receivers r ON c.receiver_id=r.id "
                    "WHERE c.closed=0 AND c.expires>? AND (c.receiver_id='' OR r.seen>?) "
                    "AND (? IS NULL OR c.receiver_id=?) LIMIT 1",
                    (self.clock(), self.clock() - 30, receiver_id, receiver_id),
                ).fetchone()
            )

    def heartbeat(self, receiver_id):
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO capture_receivers VALUES(?,?)", (receiver_id, self.clock())
            )

    def bind_receiver(self, owner, capture_id, receiver_id):
        with self._db() as db:
            self._owner(db, owner, capture_id)
            db.execute("UPDATE captures SET receiver_id=? WHERE id=?", (receiver_id, capture_id))
