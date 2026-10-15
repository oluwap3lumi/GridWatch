"""Correlation, concurrency, bounded metrics, errors and log privacy through ASGI."""

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import APIRouter
from starlette.types import Message, Receive, Scope, Send

from app.core.observability import (
    JsonFormatter,
    ObservedAPI,
    RequestMetrics,
    RequestObservability,
    metrics,
    request_id_context,
)
from app.main import unexpected_error


async def invoke(
    app: RequestObservability | ObservedAPI, path: str, headers: list[tuple[bytes, bytes]]
) -> list[Message]:
    messages: list[Message] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"secret=query-value",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("localhost", 80),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    try:
        await app(scope, receive, send)
    except ValueError:
        assert messages[0]["status"] == 500
    return messages


def test_ids_concurrency_route_templates_and_metrics(caplog: pytest.LogCaptureFixture) -> None:
    counters = RequestMetrics()
    observed: list[str | None] = []
    inflight: list[int] = []

    async def serve(scope: Scope, receive: Receive, send: Send) -> None:
        scope["route"] = SimpleNamespace(path="/assets/{asset_id}")
        await asyncio.sleep(0)
        observed.append(request_id_context.get())
        inflight.append(counters.snapshot().in_flight)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    wrapped = RequestObservability(serve, counters)

    async def parallel() -> list[list[Message]]:
        return await asyncio.gather(
            invoke(wrapped, "/assets/1", [(b"x-request-id", b"one")]),
            invoke(wrapped, "/assets/2", [(b"x-request-id", b"two")]),
        )

    with caplog.at_level(logging.INFO, logger="gridwatch.http"):
        results = asyncio.run(parallel())
    assert observed == ["one", "two"]
    assert max(inflight) == 2
    assert [dict(result[0]["headers"])[b"x-request-id"] for result in results] == [b"one", b"two"]
    snapshot = counters.snapshot()
    assert snapshot.requests == 2 and snapshot.in_flight == 0
    assert len(snapshot.routes) == 1 and snapshot.routes[0].route == "/assets/{asset_id}"
    assert snapshot.routes[0].duration_seconds >= 0
    assert request_id_context.get() is None
    formatted = [JsonFormatter().format(record) for record in caplog.records]
    assert all("secret" not in line and "/assets/1" not in line for line in formatted)
    assert json.loads(formatted[0])["request_id"] == "one"


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"x-request-id", b"bad\r\nvalue")],
        [(b"x-request-id", b"a" * 65)],
        [(b"x-request-id", b"one"), (b"x-request-id", b"two")],
    ],
)
def test_invalid_ids_are_replaced_even_for_unhandled_errors(
    headers: list[tuple[bytes, bytes]],
) -> None:
    local = ObservedAPI()
    local.add_exception_handler(Exception, unexpected_error)

    @local.get("/boom")
    def boom() -> None:
        raise ValueError("sensitive exception contents")

    messages = asyncio.run(invoke(local, "/boom", headers))
    assert messages[0]["status"] == 500
    assert json.loads(messages[1]["body"]) == {"detail": "Internal server error"}
    identifier = dict(messages[0]["headers"])[b"x-request-id"].decode()
    assert len(identifier) == 32 and int(identifier, 16) >= 0
    assert request_id_context.get() is None


def test_exception_logs_include_type_without_exception_message() -> None:
    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "ASGI failure",
        (),
        (ValueError, ValueError("secret"), None),
    )
    rendered = JsonFormatter().format(record)
    assert "secret" not in rendered
    assert json.loads(rendered)["exception_type"] == "ValueError"


def test_arbitrary_missing_paths_share_one_metrics_bucket() -> None:
    counters = RequestMetrics()

    async def missing(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    wrapped = RequestObservability(missing, counters)
    for index in range(30):
        asyncio.run(invoke(wrapped, f"/missing/{index}", []))
    observed = counters.snapshot()
    assert observed.requests == 30 and len(observed.routes) == 1
    assert observed.routes[0].route == "unmatched"


def test_included_router_metrics_keep_the_version_prefix() -> None:
    local = ObservedAPI()
    router = APIRouter()

    @router.get("/probe")
    def probe() -> dict[str, str]:
        return {"status": "ok"}

    local.include_router(router, prefix="/v99")
    messages = asyncio.run(invoke(local, "/v99/probe", []))
    assert messages[0]["status"] == 200
    assert any(row.route == "/v99/probe" for row in metrics.snapshot().routes)
