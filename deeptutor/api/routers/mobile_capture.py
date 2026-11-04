"""Owner-scoped management API; phone capabilities expose upload and receipts only."""

from __future__ import annotations

import asyncio
import base64
from functools import lru_cache
import io
import ipaddress
import threading
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from deeptutor.api.routers.auth import require_auth
from deeptutor.runtime.home import get_runtime_data_root
from deeptutor.services.mobile_capture.receiver import (
    PRIVATE_HEADERS,
    lan_addresses,
    lan_receiver,
    phone_router,
)
from deeptutor.services.mobile_capture.store import CaptureError, CaptureStore


@lru_cache(maxsize=1)
def get_store():
    from deeptutor.utils.secret_files import ensure_private_directory

    root = get_runtime_data_root() / "user" / ".runtime" / "mobile-capture"
    ensure_private_directory(root)
    store = CaptureStore(root / "capture.sqlite")

    def sweep():
        while True:
            time.sleep(60)
            store.cleanup()

    threading.Thread(target=sweep, name="phone-capture-cleanup", daemon=True).start()
    return store


async def private_response(response: Response):
    response.headers.update(PRIVATE_HEADERS)


router = APIRouter(dependencies=[Depends(private_response)])
router.include_router(phone_router(get_store), prefix="/phone")


async def owner(
    client: str = Header(alias="X-Capture-Client", min_length=32, max_length=128),
    auth=Depends(require_auth),
):
    from deeptutor.multi_user.learning_access import assert_learning_surface

    try:
        assert_learning_surface("chat")
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    identity = (auth.user_id or auth.username) if auth else "local"
    return identity + ":" + client


class StartCapture(BaseModel):
    target: str = Field(min_length=1, max_length=256)
    title: str = Field(default="DeepTutor", max_length=120)
    origin: str = Field(max_length=500)


class CaptureState(BaseModel):
    paused: bool


async def call(method, *args):
    try:
        return await asyncio.to_thread(method, *args)
    except CaptureError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


def qr_data(url):
    import qrcode
    from qrcode.image.svg import SvgPathImage

    image = qrcode.make(url, image_factory=SvgPathImage, box_size=6, border=4)
    output = io.BytesIO()
    image.save(output)
    return "data:image/svg+xml;base64," + base64.b64encode(output.getvalue()).decode()


@router.post("/sessions")
async def start(payload: StartCapture, request: Request, key=Depends(owner)):
    from deeptutor.services.config.runtime_settings import get_chat_attachment_limits

    parsed = urlsplit(payload.origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise HTTPException(400, "Invalid application origin.")
    if request.headers.get("origin", "").rstrip("/") != payload.origin.rstrip("/"):
        raise HTTPException(403, "Create the QR code from the current application.")
    host = parsed.hostname
    local = host == "localhost"
    try:
        local = local or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    addresses = await asyncio.to_thread(lan_addresses) if local else []
    if local and not addresses:
        raise HTTPException(
            503, "No LAN address found. Connect the computer to Wi-Fi or a hotspot."
        )
    limits = get_chat_attachment_limits()
    store = get_store()
    session = await call(
        store.create,
        key,
        payload.target,
        payload.title,
        min(limits.max_file_bytes, 25 * 1024 * 1024),
        min(limits.max_total_bytes, 100 * 1024 * 1024),
    )
    try:
        if local:
            port = await asyncio.to_thread(lan_receiver.start, store)
            await call(store.bind_receiver, key, session["id"], lan_receiver.identity)
            links = [
                f"http://{address}:{port}/capture?session={session['id']}#{session['phone_token']}"
                for address in addresses
            ]
        else:
            links = [
                f"{payload.origin.rstrip('/')}/api/mobile-capture/phone?session={session['id']}#{session['phone_token']}"
            ]
        codes = await asyncio.to_thread(lambda: [{"url": url, "qr": qr_data(url)} for url in links])
    except Exception:
        await call(store.close, key, session["id"])
        raise
    return {
        "id": session["id"],
        "target": session["target"],
        "title": session["title"],
        "expires_at": session["expires_at"],
        "local": local,
        "links": codes,
    }


@router.get("/sessions/{capture_id}")
async def status(capture_id: str, key=Depends(owner)):
    return await call(get_store().status, key, capture_id)


@router.patch("/sessions/{capture_id}")
async def pause(capture_id: str, payload: CaptureState, key=Depends(owner)):
    await call(get_store().set_paused, key, capture_id, payload.paused)
    return {"ok": True}


@router.get("/sessions/{capture_id}/files/{file_id}")
async def download(capture_id: str, file_id: str, key=Depends(owner)):
    data, _ = await call(get_store().file, key, capture_id, file_id)
    return Response(data, media_type="image/jpeg", headers=PRIVATE_HEADERS)


@router.post("/sessions/{capture_id}/files/{file_id}/ack")
async def ack(capture_id: str, file_id: str, key=Depends(owner)):
    await call(get_store().ack, key, capture_id, file_id)
    return {"ok": True}


@router.delete("/sessions/{capture_id}")
async def close(capture_id: str, key=Depends(owner)):
    await call(get_store().close, key, capture_id)
    return {"ok": True}


@router.post("/sessions/{capture_id}/files/{file_id}/consume")
async def consume(capture_id: str, file_id: str, key=Depends(owner)):
    await call(get_store().consume, key, capture_id, file_id)
    return {"ok": True}
