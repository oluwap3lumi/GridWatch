"""Exercise both health routes through the ASGI application without extra clients."""

import asyncio
import json
from typing import Any

import pytest

from app.main import app


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_http_response(path: str) -> None:
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("localhost", 8000),
            },
            receive,
            send,
        )
    )
    assert messages[0]["status"] == 200
    assert json.loads(messages[1]["body"]) == {"status": "ok"}


def test_health_openapi_contract() -> None:
    schema = app.openapi()
    assert "/api/v1/health" in schema["paths"]
    assert "/health" not in schema["paths"]
    assert (
        schema["components"]["schemas"]["HealthResponse"]["properties"]["status"]["const"] == "ok"
    )
