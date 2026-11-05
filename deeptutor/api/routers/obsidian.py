"""Access-checked note previews, explicit draft saves, and material extraction."""

from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from deeptutor.core.errors import AccessError
from deeptutor.services import obsidian_learning as learning

router = APIRouter(prefix="/obsidian", tags=["obsidian"])


class NoteLink(BaseModel):
    label: str
    href: str


class NotePreview(BaseModel):
    kb: str
    path: str
    body: str
    frontmatter: dict[str, Any]
    heading: str
    obsidian_uri: str
    links: list[NoteLink]
    changed: bool | None = None


class NoteDraft(BaseModel):
    id: str
    kb: str
    path: str
    content: str
    properties: dict[str, Any]
    mode: Literal["create", "append", "property"]
    status: Literal["pending", "saved"]
    preview_href: str
    note_href: str | None = None


class Material(BaseModel):
    text: str
    source: str
    title: str
    truncated: bool


async def _call(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except (learning.LearningError, AccessError) as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=getattr(exc, "detail", str(exc))
        ) from exc
    except learning.V.VaultError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="The note or material could not be read or saved. Check its path and permissions, then retry.",
        ) from exc


@router.get("/sources/{identifier}", response_model=NotePreview, response_model_exclude_none=True)
async def source(identifier: str, heading: str = ""):
    return await _call(learning.source_preview, identifier, heading)


@router.get("/note", response_model=NotePreview, response_model_exclude_none=True)
async def note(kb: str, note: str, heading: str = ""):
    return await _call(learning.note_preview, kb, note, heading)


@router.get("/asset")
async def asset(kb: str, path: str):
    target = await _call(learning.asset_path, kb, path)
    return FileResponse(
        target, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
    )


@router.get("/drafts/{identifier}", response_model=NoteDraft, response_model_exclude_none=True)
async def draft(identifier: str):
    return await _call(learning.get_draft, identifier)


class SaveDraft(BaseModel):
    path: str = Field(max_length=2048)
    content: str = Field(max_length=learning.MAX_TEXT)
    properties: dict = Field(default_factory=dict)


@router.post(
    "/drafts/{identifier}/save", response_model=NoteDraft, response_model_exclude_none=True
)
async def save(identifier: str, body: SaveDraft):
    return await _call(learning.save_draft, identifier, body.path, body.content, body.properties)


@router.post("/material", response_model=Material)
async def material(file: UploadFile = File(...)):
    data = await file.read(learning.MAX_UPLOAD + 1)
    return await _call(learning.extract_material, file.filename or "material.txt", data)


@router.get("/changes")
async def changes(kb: str):
    from deeptutor.services.obsidian_changes import scan_changes

    return await _call(scan_changes, kb)


@router.get("/notes")
async def notes(kb: str):
    return await _call(learning.list_vault_notes, kb)


@router.get("/link-suggestions")
async def link_suggestions(kb: str, note: str):
    return await _call(learning.link_suggestions, kb, note)


class LinkDraft(BaseModel):
    kb: str
    note: str
    paths: list[str] = Field(min_length=1, max_length=30)


@router.post("/link-draft", response_model=NoteDraft, response_model_exclude_none=True)
async def link_draft(body: LinkDraft):
    return await _call(learning.stage_link_draft, body.kb, body.note, body.paths)


class UrlMaterial(BaseModel):
    url: str = Field(max_length=8192)


@router.post("/material/url", response_model=Material)
async def material_url(body: UrlMaterial):
    try:
        return await learning.url_material(body.url)
    except learning.LearningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
