"""Account/workspace scoped read receipts and explicitly saved Obsidian drafts.

State lives outside the vault. SQLite serializes saves across workers; a durable
write intent permits retry after a worker stops between the file and DB writes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import stat
import tempfile
from urllib.parse import urlencode
from uuid import uuid4

from deeptutor.capabilities.obsidian import vault as V
from deeptutor.services.workspace.context import workspace_url

MAX_UPLOAD = 20 * 1024 * 1024
MAX_TEXT = 100_000
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif"}


class LearningError(V.VaultError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _state_dir():
    from deeptutor.multi_user.paths import get_current_path_service
    from deeptutor.services.workspace.context import current_workspace_id

    workspace_key = hashlib.sha256(current_workspace_id().encode("utf8")).hexdigest()
    return get_current_path_service().get_runtime_state_dir() / "obsidian-learning" / workspace_key


def _owner():
    from deeptutor.multi_user.context import get_current_user

    return get_current_user().id


def _binding(kb, write=False):
    from deeptutor.multi_user.knowledge_access import manager_for_resource, resolve_kb

    resource = resolve_kb(kb, require_write=write)
    meta = manager_for_resource(resource).get_metadata(resource.name)
    if not meta or meta.get("type") != "obsidian":
        raise LearningError("This knowledge base is not an Obsidian vault.", 404)
    root = Path(meta.get("vault_path") or "").resolve()
    if not meta.get("vault_path") or not root.is_dir():
        raise LearningError("The vault is unavailable.", 404)
    return root, f"{resource.base_dir.resolve()}:{resource.id}:{root}"


class _Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def _db():
    directory = _state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / "state.sqlite3", timeout=30, factory=_Connection)
    db.execute(
        "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, owner TEXT, kind TEXT, payload TEXT)"
    )
    return db


def _put(db, row):
    db.execute(
        "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)",
        (
            row["id"],
            _owner(),
            row["_kind"],
            json.dumps(row, ensure_ascii=False, default=_json_scalar),
        ),
    )


def _json_scalar(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _store(row):
    with _db() as db:
        _put(db, row)


def _load(db, identifier, kind):
    row = db.execute(
        "SELECT payload FROM records WHERE id=? AND owner=? AND kind=?",
        (identifier, _owner(), kind),
    ).fetchone()
    if row is None:
        raise LearningError("Reference not found in this account and workspace.", 404)
    return json.loads(row[0])


def _bound(row, write=False):
    root, binding = _binding(row["kb"], write)
    if binding != row["_binding"] or str(root.resolve()) != row["_root"]:
        raise LearningError("The knowledge base binding changed; prepare a new draft or read.", 409)
    return root


def _safe(root, path, markdown=False):
    path = str(path).replace("\\", "/")
    if not path or path.startswith("/") or PureWindowsPath(path).drive or ":" in path:
        raise LearningError("A vault-relative path is required.")
    parts = Path(path).parts
    if any(p.casefold() in V.IGNORED_DIRS or p in {".", ".."} or p.startswith(".") for p in parts):
        raise LearningError("Internal or escaping paths are not allowed.")
    if markdown and not path.lower().endswith(".md"):
        path += ".md"
    target = (root / path).resolve()
    if root.resolve() not in target.parents:
        raise LearningError("Path escapes the vault.")
    if any(p.casefold() in V.IGNORED_DIRS for p in target.relative_to(root.resolve()).parts):
        raise LearningError("Internal vault paths are not allowed.")
    # Reject symlinks even when they currently resolve inside the vault.
    current = root
    for part in Path(path).parts:
        current = current / part
        reparse = current.exists() and getattr(current.lstat(), "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
        )
        if current.is_symlink() or reparse:
            raise LearningError("Symlinks and directory junctions are not allowed.")
    return target


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _href(kb, note, heading=""):
    return workspace_url("/obsidian?" + urlencode({"kb": kb, "note": note, "heading": heading}))


def _read(root, note):
    result = V.read_note(root, note)
    _safe(root, result["path"], True)
    return result


def issue_source(kb, root, note):
    actual, binding = _binding(kb)
    if actual.resolve() != root.resolve():
        raise LearningError("The vault binding changed.", 409)
    data = _read(root, note)
    identifier = uuid4().hex
    headings = re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", data["body"], re.M)
    _store(
        {
            "id": identifier,
            "_kind": "source",
            "kb": kb,
            "path": data["path"],
            "_root": str(root.resolve()),
            "_binding": binding,
            "_digest": _digest(_safe(root, data["path"]).read_bytes()),
            "_headings": headings,
        }
    )
    data["references"] = [
        {
            "title": Path(data["path"]).stem,
            "heading": h,
            "href": workspace_url("/obsidian?" + urlencode({"source": identifier, "heading": h})),
        }
        for h in ["", *dict.fromkeys(headings)]
    ]
    return data


def note_preview(kb, note, heading=""):
    root, _ = _binding(kb)
    data = _read(root, note)
    links = []
    related = data["frontmatter"].get("related", [])
    if isinstance(related, str):
        related = [related]
    if not isinstance(related, list):
        related = []
    targets = [m[1] for m in re.finditer(r"(?<!!)\[\[([^\]\n]+)\]\]", data["body"])]
    targets += [r.removeprefix("[[").removesuffix("]]") for r in related if isinstance(r, str)]
    seen = set()
    names = None
    for value in targets:
        raw, _, label = value.partition("|")
        target, _, section = raw.partition("#")
        try:
            if target:
                lookup = V._reference_target(target)
                if names is None and "/" not in lookup and not lookup.lower().endswith(".md"):
                    # Alias and basename resolution reads metadata. Share one
                    # operation-local snapshot across body and related links.
                    names, _ = V._note_snapshot(root)
                resolved = V._resolve_reference(root, target, names)
            else:
                resolved = root / data["path"]
            if resolved:
                rel = resolved.relative_to(root.resolve()).as_posix()
                _safe(root, rel, True)
                href = _href(kb, rel, section)
                if href not in seen:
                    seen.add(href)
                    links.append({"label": label or raw, "href": href})
        except (V.VaultError, ValueError):
            continue
    return {
        "kb": kb,
        **data,
        "heading": heading,
        "obsidian_uri": "obsidian://open?"
        + urlencode(
            {"vault": root.name, "file": data["path"] + ("#" + heading if heading else "")}
        ),
        "links": links,
    }


def source_preview(identifier, heading=""):
    with _db() as db:
        row = _load(db, identifier, "source")
    root = _bound(row)
    if heading and heading not in row.get("_headings", []):
        raise LearningError("This heading was not present in the cited read.", 404)
    data = note_preview(row["kb"], row["path"], heading)
    data["changed"] = _digest(_safe(root, row["path"]).read_bytes()) != row["_digest"]
    return data


def _public(row):
    keys = (
        "id",
        "kb",
        "path",
        "content",
        "properties",
        "mode",
        "status",
        "preview_href",
        "note_href",
    )
    return {k: row[k] for k in keys if k in row}


def stage_draft(kb, root, mode, note, content, properties=None):
    if not kb:
        raise LearningError("No server-owned vault reference is available.")
    if len(content) > MAX_TEXT:
        raise LearningError("Draft exceeds the text limit.")
    actual, binding = _binding(kb, True)
    if actual.resolve() != root.resolve():
        raise LearningError("The vault binding changed.", 409)
    if mode not in {"create", "append", "property"}:
        raise LearningError("Unknown draft mode.")
    properties = properties or {}
    original = None
    if mode == "create":
        path = _safe(root, note, True)
        if path.exists():
            raise LearningError("Note already exists; choose a new path.", 409)
        if not content.strip():
            raise LearningError("Draft content must be non-empty.")
    else:
        data = _read(root, note)
        path = _safe(root, data["path"], True)
        raw = path.read_bytes()
        try:
            raw.decode("utf8")
        except UnicodeDecodeError as exc:
            raise LearningError(
                "Note is not valid UTF-8; fix its encoding before editing."
            ) from exc
        original = _digest(raw)
        if mode == "property":
            content = data["body"]
        properties = {**data["frontmatter"], **properties}
    identifier = uuid4().hex
    row = {
        "id": identifier,
        "_kind": "draft",
        "kb": kb,
        "_binding": binding,
        "_root": str(root.resolve()),
        "_original": original,
        "path": path.relative_to(root.resolve()).as_posix(),
        "content": content,
        "properties": properties,
        "mode": mode,
        "status": "pending",
        "preview_href": workspace_url("/obsidian?" + urlencode({"draft": identifier})),
    }
    _store(row)
    return _public(row)


def get_draft(identifier):
    with _db() as db:
        row = _load(db, identifier, "draft")
    _bound(row)
    return _public(row)


def save_draft(identifier, path, content, properties):
    if len(content) > MAX_TEXT or len(json.dumps(properties)) > MAX_TEXT:
        raise LearningError("Draft exceeds the text limit.")
    db = _db()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = _load(db, identifier, "draft")
        root = _bound(row, True)  # Recheck access even for an idempotent repeat.
        if row["status"] == "saved":
            return _public(row)
        if "_intent" in row:
            previous = _safe(root, row["path"], True)
            previous_digest = _digest(previous.read_bytes()) if previous.exists() else None
            if previous_digest == row["_intent_digest"]:
                # Recover a file write completed before its DB acknowledgement.
                row.update(status="saved", note_href=_href(row["kb"], row["path"]))
                _put(db, row)
                db.commit()
                return _public(row)
            if previous_digest != row["_original"]:
                raise LearningError("The note changed; this save cannot overwrite it.", 409)
            # No file write happened: permit the user's revised edits on retry.
            row.pop("_intent")
            row.pop("_intent_digest")
        target = _safe(root, path, True)
        rel = target.relative_to(root.resolve()).as_posix()
        if row["mode"] != "create" and rel != row["path"]:
            raise LearningError("An existing-note draft cannot change its target.", 409)
        if "_intent" not in row:
            raw = target.read_bytes() if target.exists() else None
            if row["mode"] == "create" and raw is not None:
                raise LearningError("Note already exists; choose another path.", 409)
            if row["mode"] != "create" and (raw is None or _digest(raw) != row["_original"]):
                raise LearningError(
                    "The note changed since this draft was prepared. Read it again and prepare a new draft.",
                    409,
                )
            body = content
            if row["mode"] == "property":
                _, original_body = V.split_frontmatter(raw.decode("utf8"))
                if content.replace("\r\n", "\n") != original_body.replace("\r\n", "\n"):
                    raise LearningError("Property drafts cannot change the note body.", 409)
                body = original_body
            if row["mode"] == "append":
                _, original_body = V.split_frontmatter(raw.decode("utf8"))
                separator = "" if not original_body or original_body.endswith("\n") else "\n"
                body = original_body + separator + content
            rendered = V._compose_note(properties, body)
            row.update(
                path=rel,
                content=content,
                properties=properties,
                _intent=rendered,
                _intent_digest=_digest(rendered.encode("utf8")),
            )
            _put(db, row)
            db.commit()  # Durable intent before filesystem mutation.
            db.execute("BEGIN IMMEDIATE")
            row = _load(db, identifier, "draft")
            root = _bound(row, True)
            target = _safe(root, row["path"], True)
            if row["status"] == "saved":
                return _public(row)
        else:
            target = _safe(root, row["path"], True)
        raw = target.read_bytes() if target.exists() else None
        current_digest = _digest(raw) if raw is not None else None
        if current_digest != row["_intent_digest"]:
            if current_digest != row["_original"]:
                raise LearningError("The note changed; this save cannot overwrite it.", 409)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(row["_intent"].encode("utf8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                if row["mode"] == "create":
                    # Publish only a complete, flushed file. link() creates the
                    # destination exclusively, so a concurrent user note wins.
                    # Never fall back to replace(), which could overwrite it.
                    try:
                        os.link(temp, target)
                    except FileExistsError as exc:
                        raise LearningError(
                            "Note already exists; choose another path.", 409
                        ) from exc
                    except OSError as exc:
                        raise LearningError(
                            "This filesystem could not publish the note safely. "
                            "Check folder permissions and hard-link support, then retry "
                            "or choose a folder on a filesystem supporting hard links."
                        ) from exc
                else:
                    if _digest(target.read_bytes()) != row["_original"]:
                        raise LearningError("The note changed during save.", 409)
                    os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        row.update(status="saved", note_href=_href(row["kb"], row["path"]))
        _put(db, row)
        db.commit()
        return _public(row)
    finally:
        db.close()


def asset_path(kb, path):
    root, _ = _binding(kb)
    target = _safe(root, path)
    if target.suffix.lower() not in IMAGE_EXTENSIONS or not target.is_file():
        raise LearningError("Only existing local image assets are supported.", 404)
    return target


def extract_material(filename, data):
    if len(data) > MAX_UPLOAD:
        raise LearningError("File exceeds the 20 MB limit.", 413)
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".txt", ".markdown"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise LearningError("Save the text file as UTF-8 and upload it again.") from exc
    elif suffix == ".pdf":
        import fitz

        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise LearningError("Unlock the PDF before uploading it.")
                chunks, size = [], 0
                for page in doc:
                    chunk = page.get_text()
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_TEXT:
                        break
                text = "\n".join(chunks)
        except LearningError:
            raise
        except Exception as exc:
            raise LearningError("The PDF could not be read; upload an unlocked text PDF.") from exc
        if not text.strip():
            raise LearningError(
                "This PDF is empty or scanned. Run OCR first, or upload Markdown/text."
            )
    else:
        raise LearningError("Upload a Markdown, TXT, or text PDF file.")
    if not text.strip():
        raise LearningError("The material contains no readable text.")
    return {
        "text": text[:MAX_TEXT],
        "source": filename,
        "title": Path(filename).stem,
        "truncated": len(text) > MAX_TEXT,
    }


async def url_material(url):
    from deeptutor.tools.web_fetch import fetch_url_as_markdown

    result = await fetch_url_as_markdown(url, max_chars=MAX_TEXT)
    if not result.ok:
        raise LearningError(result.error)
    if not result.markdown.strip():
        raise LearningError("The webpage contains no readable text; upload its text instead.")
    return {
        "text": result.markdown[:MAX_TEXT],
        "source": result.url,
        "title": result.title,
        "truncated": result.truncated or len(result.markdown) > MAX_TEXT,
    }
