import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.capabilities.obsidian.tools import ObsidianAppendTool, ObsidianReadTool
from deeptutor.services import obsidian_learning as L


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "光.md").write_text(
        "---\ntags: [ta]\n---\n# Light\nBody [[Other#Detail|next]]\n", encoding="utf8"
    )
    (root / "Other.md").write_text("# Detail\nMore", encoding="utf8")
    monkeypatch.setattr(L, "_state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(L, "_owner", lambda: "alice")
    monkeypatch.setattr(L, "_binding", lambda kb, write=False: (root, "immutable"))
    return root


@pytest.mark.asyncio
async def test_actual_read_sources_and_staged_tools(env):
    result = await ObsidianReadTool().execute(note="光", _vault_path=str(env), _vault_ref="kb")
    payload = json.loads(result.content)
    assert payload["references"][1]["heading"] == "Light"
    source = payload["references"][0]["href"].split("source=")[1].split("&")[0]
    preview = L.source_preview(source)
    assert preview["kb"] == "kb" and preview["path"] == "光.md"
    assert preview["links"][0]["label"] == "next"
    result = await ObsidianAppendTool().execute(
        note="光", content="addition", _vault_path=str(env), _vault_ref="kb"
    )
    assert json.loads(result.content)["status"] == "pending"
    assert "addition" not in (env / "光.md").read_text(encoding="utf8")


def test_create_save_repeat_and_owner(env, monkeypatch):
    draft = L.stage_draft("kb", env, "create", "new.md", "body", {"status": "draft"})
    assert not (env / "new.md").exists()
    saved = L.save_draft(draft["id"], "new.md", "edited", {"status": "done"})
    assert saved["status"] == "saved"
    assert L.save_draft(draft["id"], "elsewhere.md", "bad", {}) == saved
    assert "edited" in (env / "new.md").read_text()
    monkeypatch.setattr(L, "_owner", lambda: "bob")
    with pytest.raises(L.LearningError):
        L.get_draft(draft["id"])


def test_stale_and_binding_and_readonly(env, monkeypatch):
    draft = L.stage_draft("kb", env, "append", "光", "extra", {})
    (env / "光.md").write_text("user change", encoding="utf8")
    with pytest.raises(L.LearningError, match="changed"):
        L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert L.get_draft(draft["id"])["status"] == "pending"
    monkeypatch.setattr(L, "_binding", lambda kb, write=False: (env, "rebound"))
    with pytest.raises(L.LearningError, match="binding"):
        L.get_draft(draft["id"])


def test_property_preview_assets_and_traversal(env):
    draft = L.stage_draft("kb", env, "property", "光", "", {"status": "reviewed"})
    L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert L.note_preview("kb", "光", "Light")["frontmatter"]["status"] == "reviewed"
    (env / "pic.png").write_bytes(b"png")
    assert L.asset_path("kb", "pic.png") == env / "pic.png"
    for path in ("../secret.png", ".obsidian/pic.png", "https://evil/a.png", "C:/a.png"):
        with pytest.raises(L.LearningError):
            L.asset_path("kb", path)


def test_material_limits_and_empty_pdf():
    assert L.extract_material("a.md", b"# Hello")["text"] == "# Hello"
    assert L.extract_material("a.txt", b"x" * (L.MAX_TEXT + 1))["truncated"]
    import fitz

    doc = fitz.open()
    doc.new_page()
    with pytest.raises(L.LearningError, match="scanned|OCR"):
        L.extract_material("scan.pdf", doc.tobytes())


def test_related_links_and_source_heading_validation(env):
    (env / "光.md").write_text(
        '---\nrelated: ["[[Other#Detail|related]]"]\n---\n# Light\nBody', encoding="utf8"
    )
    preview = L.note_preview("kb", "光")
    assert preview["links"][0]["label"] == "related"
    source = (
        L.issue_source("kb", env, "光")["references"][0]["href"].split("source=")[1].split("&")[0]
    )
    with pytest.raises(L.LearningError, match="heading"):
        L.source_preview(source, "Invented heading")


def test_append_save_repeat_and_create_conflict(env):
    draft = L.stage_draft("kb", env, "append", "光", "extra", {})
    L.save_draft(draft["id"], draft["path"], "edited addition", draft["properties"])
    L.save_draft(draft["id"], draft["path"], "edited addition", draft["properties"])
    text = (env / "光.md").read_text(encoding="utf8")
    assert text.count("edited addition") == 1 and "Body" in text
    draft = L.stage_draft("kb", env, "create", "new.md", "draft")
    (env / "new.md").write_text("user note", encoding="utf8")
    with pytest.raises(L.LearningError, match="exists"):
        L.save_draft(draft["id"], draft["path"], "draft", {})
    assert (env / "new.md").read_text() == "user note"


def test_interrupted_save_retries_without_duplicate(env, monkeypatch):
    draft = L.stage_draft("kb", env, "append", "光", "addition")
    replace = L.os.replace

    def failed(*args):
        raise OSError("temporary save failure")

    monkeypatch.setattr(L.os, "replace", failed)
    with pytest.raises(OSError):
        L.save_draft(draft["id"], draft["path"], "addition", draft["properties"])
    assert L.get_draft(draft["id"])["status"] == "pending"
    assert "addition" not in (env / "光.md").read_text(encoding="utf8")
    monkeypatch.setattr(L.os, "replace", replace)
    L.save_draft(draft["id"], draft["path"], "revised addition", draft["properties"])
    assert (env / "光.md").read_text(encoding="utf8").count("revised addition") == 1


def test_simultaneous_process_saves_are_idempotent(env):
    import subprocess
    import sys

    draft = L.stage_draft("kb", env, "append", "光", "addition")
    script = """
import sys
from pathlib import Path
from deeptutor.services import obsidian_learning as L
root, identifier = Path(sys.argv[1]), sys.argv[2]
L._state_dir = lambda: root.parent / 'state'
L._owner = lambda: 'alice'
L._binding = lambda kb, write=False: (root, 'immutable')
d = L.get_draft(identifier)
assert L.save_draft(identifier, d['path'], d['content'], d['properties'])['status'] == 'saved'
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(env), draft["id"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    for child in children:
        stdout, stderr = child.communicate(timeout=30)
        assert child.returncode == 0, stderr.decode(errors="replace")
    assert (env / "光.md").read_text(encoding="utf8").count("addition") == 1


@pytest.mark.asyncio
async def test_url_material_uses_safe_fetch(monkeypatch):
    async def fetch(url, **kwargs):
        return SimpleNamespace(ok=True, markdown="text", title="Page", url=url, truncated=False)

    monkeypatch.setattr("deeptutor.tools.web_fetch.fetch_url_as_markdown", fetch)
    assert (await L.url_material("https://example.com"))["title"] == "Page"


def test_issued_links_pin_originating_workspace(env, monkeypatch):
    from deeptutor.services.workspace import context

    monkeypatch.setattr(context, "current_workspace_id", lambda: "workspace-a")
    receipt = L.issue_source("kb", env, "光")
    assert all("dt_workspace=workspace-a" in r["href"] for r in receipt["references"])
    assert all("dt_workspace=workspace-a" in r["href"] for r in L.note_preview("kb", "光")["links"])
    draft = L.stage_draft("kb", env, "create", "new.md", "body")
    assert "dt_workspace=workspace-a" in draft["preview_href"]
    saved = L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert "dt_workspace=workspace-a" in saved["note_href"]


def test_property_save_refuses_body_rewrite(env):
    draft = L.stage_draft("kb", env, "property", "光", "", {"status": "done"})
    original = (env / "光.md").read_bytes()
    with pytest.raises(L.LearningError, match="body"):
        L.save_draft(draft["id"], draft["path"], "replacement body", draft["properties"])
    assert (env / "光.md").read_bytes() == original
    L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert L.note_preview("kb", "光")["body"] == draft["content"]


def test_retry_after_file_write_before_acknowledgement(env, monkeypatch):
    draft = L.stage_draft("kb", env, "append", "光", "once")
    put = L._put

    def fail_ack(db, row):
        if row.get("status") == "saved":
            raise RuntimeError("worker stopped before acknowledgement")
        return put(db, row)

    monkeypatch.setattr(L, "_put", fail_ack)
    with pytest.raises(RuntimeError):
        L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert L.get_draft(draft["id"])["status"] == "pending"
    monkeypatch.setattr(L, "_put", put)
    assert (
        L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])["status"]
        == "saved"
    )
    assert (env / "光.md").read_text(encoding="utf8").count("once") == 1


def test_real_state_directory_isolates_workspace_contexts(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from deeptutor.services.workspace import context

    monkeypatch.setattr(
        "deeptutor.multi_user.paths.get_current_path_service",
        lambda: SimpleNamespace(get_runtime_state_dir=lambda: tmp_path / "account-runtime"),
    )
    token = context._scope.set(context.WorkspaceScope("workspace-a", tmp_path, tmp_path / "a"))
    try:
        first = L._state_dir()
        L._store({"id": "receipt", "_kind": "source"})
        context._scope.set(context.WorkspaceScope("workspace-b", tmp_path, tmp_path / "b"))
        second = L._state_dir()
        assert second != first
        with L._db() as db, pytest.raises(L.LearningError):
            L._load(db, "receipt", "source")
        context._scope.set(None)
        assert L._state_dir() not in {first, second}
    finally:
        context._scope.reset(token)


def test_interrupted_create_never_publishes_partial_note(env, monkeypatch):
    from contextlib import contextmanager

    draft = L.stage_draft("kb", env, "create", "new.md", "complete content")
    original_open = Path.open
    original_fdopen = L.os.fdopen

    class InterruptedWriter:
        def __init__(self, stream):
            self.stream = stream

        def write(self, data):
            self.stream.write(data[: len(data) // 2])
            self.stream.flush()
            raise OSError("interrupted disk write")

    @contextmanager
    def interrupted(stream):
        with stream:
            yield InterruptedWriter(stream)

    def path_open(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return interrupted(stream) if mode == "xb" else stream

    def fd_open(fd, mode="r", *args, **kwargs):
        stream = original_fdopen(fd, mode, *args, **kwargs)
        return interrupted(stream) if mode == "wb" else stream

    monkeypatch.setattr(Path, "open", path_open)
    monkeypatch.setattr(L.os, "fdopen", fd_open)
    with pytest.raises(OSError, match="interrupted"):
        L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert not (env / "new.md").exists()
    assert L.get_draft(draft["id"])["status"] == "pending"
    monkeypatch.setattr(Path, "open", original_open)
    monkeypatch.setattr(L.os, "fdopen", original_fdopen)
    assert (
        L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])["status"]
        == "saved"
    )
    assert (env / "new.md").read_text(encoding="utf8") == "complete content"


def test_create_publish_failure_is_retryable_and_never_overwrites(env, monkeypatch):
    draft = L.stage_draft("kb", env, "create", "new.md", "draft content")
    link = L.os.link

    def unsupported(*args, **kwargs):
        raise OSError("filesystem does not support hard links")

    monkeypatch.setattr(L.os, "link", unsupported)
    with pytest.raises(L.LearningError, match="hard-link support"):
        L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert not (env / "new.md").exists()
    assert L.get_draft(draft["id"])["status"] == "pending"
    assert not list(env.glob("*.tmp"))

    def concurrent_create(source, target):
        Path(target).write_text("concurrent user content", encoding="utf8")
        return link(source, target)

    monkeypatch.setattr(L.os, "link", concurrent_create)
    with pytest.raises(L.LearningError, match="already exists"):
        L.save_draft(draft["id"], draft["path"], draft["content"], draft["properties"])
    assert (env / "new.md").read_text(encoding="utf8") == "concurrent user content"


def test_source_preview_resolves_all_links_with_one_vault_snapshot(env, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    for index in range(9):
        (env / f"Target{index}.md").write_text(f"# Target {index}", encoding="utf8")
    for folder in ("one", "two"):
        (env / folder).mkdir()
        (env / folder / "Duplicate.md").write_text("Ambiguous basename", encoding="utf8")
    (env / "Aliased.md").write_text("---\naliases: [Shortcut]\n---\n# Alias", encoding="utf8")
    (env / "Index.md").write_text(
        '---\nrelated: ["[[Shortcut#Alias|Related alias]]", "Target1"]\n---\n'
        + "\n".join(f"[[Target{i}]]" for i in range(9))
        + "\n[[Duplicate]]\n[[one/Duplicate|Explicit duplicate]]",
        encoding="utf8",
    )
    source_href = L.issue_source("kb", env, "Index.md")["references"][0]["href"]
    source = parse_qs(urlsplit(source_href).query)["source"][0]
    reads = []
    read_text = L.V._read_text

    def counted_read(path):
        reads.append(path)
        return read_text(path)

    monkeypatch.setattr(L.V, "_read_text", counted_read)
    preview = L.source_preview(source)
    assert len(reads) <= len(list(env.rglob("*.md"))) + 1
    links = {item["label"]: parse_qs(urlsplit(item["href"]).query) for item in preview["links"]}
    assert "Duplicate" not in links
    assert links["Explicit duplicate"]["note"] == ["one/Duplicate.md"]
    assert links["Related alias"]["note"] == ["Aliased.md"]
    assert links["Related alias"]["heading"] == ["Alias"]
    assert len(preview["links"]) == 11
