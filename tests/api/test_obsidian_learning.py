from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers.obsidian import router
from deeptutor.core.errors import AccessError
from deeptutor.services import obsidian_learning as L


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "Note.md").write_text("# Heading\noriginal", encoding="utf8")
    monkeypatch.setattr(L, "_state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(L, "_owner", lambda: "alice")
    monkeypatch.setattr(
        "deeptutor.multi_user.knowledge_access.resolve_kb",
        lambda kb, require_write=False: SimpleNamespace(id="id", base_dir=tmp_path, name="kb"),
    )
    manager = SimpleNamespace(
        get_metadata=lambda name: {"type": "obsidian", "vault_path": str(root)}
    )
    monkeypatch.setattr(
        "deeptutor.multi_user.knowledge_access.manager_for_resource", lambda resource: manager
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return root, TestClient(app)


def test_http_contract_and_material(env):
    root, client = env
    preview = client.get(
        "/api/obsidian/note", params={"kb": "kb", "note": "Note", "heading": "Heading"}
    )
    assert preview.status_code == 200
    assert preview.json()["heading"] == "Heading"
    assert preview.json()["obsidian_uri"].startswith("obsidian://")
    draft = L.stage_draft("kb", root, "create", "新.md", "draft")
    response = client.post(
        f"/api/obsidian/drafts/{draft['id']}/save",
        json={"path": "新.md", "content": "edited", "properties": {"tags": ["ta"]}},
    )
    assert response.status_code == 200 and response.json()["status"] == "saved"
    assert (root / "新.md").is_file()
    result = client.post(
        "/api/obsidian/material", files={"file": ("a.md", b"# text", "text/markdown")}
    )
    assert result.status_code == 200 and result.json()["text"] == "# text"
    assert (
        client.get("/api/obsidian/asset", params={"kb": "kb", "path": "../a.png"}).status_code
        == 400
    )


def test_revoked_access_and_readonly_cannot_stage_or_save(env, monkeypatch):
    root, client = env
    source = (
        L.issue_source("kb", root, "Note")["references"][0]["href"]
        .split("source=")[1]
        .split("&")[0]
    )
    draft = L.stage_draft("kb", root, "append", "Note", "extra")

    def readonly(kb, require_write=False):
        if require_write:
            raise AccessError(status_code=403, detail="read only")
        return SimpleNamespace(id="id", base_dir=root.parent, name="kb")

    monkeypatch.setattr("deeptutor.multi_user.knowledge_access.resolve_kb", readonly)
    with pytest.raises(AccessError):
        L.stage_draft("kb", root, "create", "bad.md", "body")
    assert (
        client.post(
            f"/api/obsidian/drafts/{draft['id']}/save",
            json={"path": draft["path"], "content": "extra", "properties": {}},
        ).status_code
        == 403
    )
    assert (root / "Note.md").read_text() == "# Heading\noriginal"

    def denied(*args, **kwargs):
        raise AccessError(status_code=403, detail="revoked")

    monkeypatch.setattr("deeptutor.multi_user.knowledge_access.resolve_kb", denied)
    assert client.get("/api/obsidian/sources/" + source).status_code == 403
    assert client.get("/api/obsidian/note", params={"kb": "kb", "note": "Note"}).status_code == 403


def test_source_changes_and_scope(env, monkeypatch):
    root, client = env
    ref = (
        L.issue_source("kb", root, "Note")["references"][0]["href"]
        .split("source=")[1]
        .split("&")[0]
    )
    (root / "Note.md").write_text("new content", encoding="utf8")
    assert client.get("/api/obsidian/sources/" + ref).json()["changed"] is True
    monkeypatch.setattr(L, "_owner", lambda: "bob")
    assert client.get("/api/obsidian/sources/" + ref).status_code == 404
    monkeypatch.setattr(L, "_owner", lambda: "alice")
    monkeypatch.setattr(L, "_state_dir", lambda: root.parent / "other-workspace")
    assert client.get("/api/obsidian/sources/" + ref).status_code == 404
