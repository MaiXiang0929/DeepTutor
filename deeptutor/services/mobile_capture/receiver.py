"""Phone-only HTTP surface and an on-demand LAN listener for local desktops."""

from __future__ import annotations

import asyncio
import atexit
import socket
import threading
import time
import uuid

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse

from .mobile_page import PHONE_HTML
from .store import CaptureError

PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def phone_router(get_store):
    async def private_response(response: Response):
        response.headers.update(PRIVATE_HEADERS)

    router = APIRouter(dependencies=[Depends(private_response)])

    def token(authorization):
        return authorization.removeprefix("Bearer ") if authorization else ""

    @router.get("", response_class=HTMLResponse)
    async def page():
        return HTMLResponse(
            PHONE_HTML,
            headers={
                **PRIVATE_HEADERS,
                "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; "
                "style-src 'unsafe-inline'; img-src blob: data:; connect-src 'self'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            },
        )

    @router.get("/status")
    async def status(authorization: str | None = Header(default=None)):
        try:
            return await asyncio.to_thread(get_store().phone_status, token(authorization))
        except CaptureError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @router.post("/files")
    async def upload(
        file: UploadFile = File(...),
        client_file_id: str = Form(..., min_length=1, max_length=80),
        authorization: str | None = Header(default=None),
    ):
        try:
            store = get_store()
            policy = await asyncio.to_thread(store.phone_status, token(authorization))
            data = bytearray()
            while chunk := await file.read(64 * 1024):
                if len(data) + len(chunk) > policy["max_file_bytes"]:
                    raise CaptureError("Photo exceeds the file size limit.", 413)
                data.extend(chunk)
            return await asyncio.to_thread(
                store.upload, token(authorization), client_file_id, bytes(data)
            )
        except CaptureError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        finally:
            await file.close()

    return router


class BodyLimit:
    """Count actual body bytes, including chunked multipart, before parsing files."""

    def __init__(self, app, limit=26 * 1024 * 1024, path_prefix="/capture", get_store=None):
        self.app, self.limit = app, limit
        self.path_prefix, self.get_store = path_prefix, get_store

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith(self.path_prefix + "/files")
        ):
            return await self.app(scope, receive, send)
        if self.get_store:
            headers = dict(scope.get("headers", []))
            token = headers.get(b"authorization", b"").decode("latin1").removeprefix("Bearer ")
            try:
                await asyncio.to_thread(self.get_store().phone_status, token)
            except CaptureError as exc:
                return await JSONResponse(
                    {"detail": str(exc)}, status_code=exc.status, headers=PRIVATE_HEADERS
                )(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.limit:
                raise HTTPException(413, "Upload request is too large.")
            return message

        await self.app(scope, bounded_receive, send)


class LanReceiver:
    def __init__(self):
        self.lock = threading.Lock()
        self.server = None
        self.port = None
        self.identity = ""
        self.thread = None

    def start(self, store):
        import uvicorn

        with self.lock:
            if (
                self.server
                and not self.server.should_exit
                and self.thread
                and self.thread.is_alive()
            ):
                return self.port
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("0.0.0.0", 0))
            listener.listen(32)
            self.port = listener.getsockname()[1]
            self.identity = uuid.uuid4().hex
            store.heartbeat(self.identity)
            app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
            app.include_router(phone_router(lambda: store), prefix="/capture")
            app.add_middleware(BodyLimit, get_store=lambda: store)

            @app.middleware("http")
            async def private_responses(request, call_next):
                response = await call_next(request)
                response.headers.update(PRIVATE_HEADERS)
                return response

            server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
            self.server = server

            def serve():
                try:
                    server.run(sockets=[listener])
                finally:
                    server.should_exit = True
                    listener.close()

            self.thread = threading.Thread(target=serve, name="phone-capture-http", daemon=True)
            self.thread.start()

            def expire():
                while not server.should_exit:
                    time.sleep(10)
                    store.cleanup()
                    if self.stop_if_idle(server, store):
                        break
                    if not server.should_exit:
                        store.heartbeat(self.identity)

            threading.Thread(target=expire, name="phone-capture-expiry", daemon=True).start()
            atexit.register(self.stop)
            return self.port

    def stop(self):
        with self.lock:
            if self.server:
                self.server.should_exit = True
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def stop_if_idle(self, server, store):
        with self.lock:
            if self.server is not server or store.has_active(self.identity or None):
                return False
            server.should_exit = True
            return True


lan_receiver = LanReceiver()


def lan_addresses():
    """Offer local interface choices; never encode loopback in a phone QR."""
    import ipaddress

    candidates = []
    # UDP connect selects a route without sending a packet.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        candidates.extend(
            item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    return list(
        dict.fromkeys(
            value
            for value in candidates
            if ipaddress.ip_address(value).is_private
            and not ipaddress.ip_address(value).is_loopback
            and not ipaddress.ip_address(value).is_link_local
        )
    )
