"""Upload limits apply before multipart parsing, even without Content-Length."""

import asyncio

from app.core.upload_limit import UploadBodyLimit


def test_chunked_oversize_rejected_before_parser(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "1")
    called, messages = [], []

    async def downstream(scope, receive, send):
        called.append(True)

    async def receive():
        return {"type": "http.request", "body": b"x" * 65538, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(
        UploadBodyLimit(downstream)(
            {"type": "http", "method": "POST", "path": "/api/v1/imports"}, receive, send
        )
    )
    assert not called
    assert messages[0]["status"] == 413


def test_bounded_body_is_replayed_exactly(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "5")
    received = []
    incoming = iter([b"abc", b"def"])

    async def downstream(scope, receive, send):
        received.append((await receive())["body"])

    async def receive():
        chunk = next(incoming)
        return {"type": "http.request", "body": chunk, "more_body": chunk == b"abc"}

    async def send(message):
        pass

    asyncio.run(
        UploadBodyLimit(downstream)(
            {"type": "http", "method": "POST", "path": "/api/v1/imports"}, receive, send
        )
    )
    assert received == [b"abcdef"]
