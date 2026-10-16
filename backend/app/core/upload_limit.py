"""Bound upload bodies before the multipart parser allocates temporary files."""

from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.uploads import UploadSettings


class UploadBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/api/v1/imports"
        ):
            await self.app(scope, receive, send)
            return
        maximum = UploadSettings.from_env().max_bytes + 65536  # bounded multipart headers/fields
        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > maximum:
                    await JSONResponse({"detail": "UPLOAD_TOO_LARGE"}, status_code=413)(
                        scope, receive, send
                    )
                    return
                body.write(chunk)
                if not message.get("more_body", False):
                    break
            body.seek(0)

            async def replay() -> Message:
                chunk = body.read(65536)
                return {"type": "http.request", "body": chunk, "more_body": body.tell() < total}

            await self.app(scope, replay, send)
