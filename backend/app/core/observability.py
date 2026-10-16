"""ASGI request correlation, bounded metrics and privacy-preserving JSON logs."""

import json
import logging
import re
from collections.abc import Iterable
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI
from starlette.routing import compile_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.import_logging import ImportError, ImportEvent
from app.schemas.operations import MetricsResponse, RouteMetric

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("gridwatch.http")
METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


class JsonFormatter(logging.Formatter):
    """Never include request bodies, query strings, headers, or exception text."""

    def format(self, record: logging.LogRecord) -> str:
        # Never interpolate import messages, exceptions, filenames, or arbitrary extras.
        if record.name.startswith(
            (
                "gridwatch.import",
                "shapefile",
                "shapely",
                "pyproj",
                "python_multipart",
                "multipart",
                "sqlalchemy",
            )
        ):
            safe: dict[str, str | int] = {"event": "IMPORT_EVENT"}
            if (
                isinstance(record.msg, str)
                and record.msg in {event.value for event in ImportEvent}
                and not record.args
            ):
                safe["event"] = str(record.msg)
            batch_id = getattr(record, "batch_id", None)
            if isinstance(batch_id, UUID):
                safe["batch_id"] = str(batch_id)
            count = getattr(record, "count", None)
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                safe["count"] = count
            error_code = getattr(record, "error_code", None)
            if isinstance(error_code, ImportError):
                safe["error_code"] = error_code.value
            return json.dumps(safe)
        event: dict[str, str | int | float | None] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for key in ("method", "route", "status_code", "duration_seconds", "request_id"):
            value: object = getattr(record, key, None)
            if isinstance(value, str | int | float):
                event[key] = value
        if record.exc_info and record.exc_info[0]:
            event["exception_type"] = record.exc_info[0].__name__
        return json.dumps(event, ensure_ascii=True)


class RequestMetrics:
    """Counters use fixed HTTP methods and matched route templates, not caller paths."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.started = perf_counter()
        self.in_flight = 0
        self.rows: dict[tuple[str, str, int], tuple[int, float]] = {}

    def begin(self) -> None:
        with self.lock:
            self.in_flight += 1

    def finish(self, method: str, route: str, status: int, duration: float) -> None:
        with self.lock:
            self.in_flight -= 1
            key = (method, route, status)
            count, elapsed = self.rows.get(key, (0, 0.0))
            self.rows[key] = (count + 1, elapsed + duration)

    def snapshot(self) -> MetricsResponse:
        with self.lock:
            routes = [
                RouteMetric(
                    method=method,
                    route=route,
                    status_code=status,
                    requests=count,
                    duration_seconds=elapsed,
                )
                for (method, route, status), (count, elapsed) in sorted(self.rows.items())
            ]
            return MetricsResponse(
                uptime_seconds=perf_counter() - self.started,
                in_flight=self.in_flight,
                requests=sum(row.requests for row in routes),
                routes=routes,
            )


metrics = RequestMetrics()


class RequestObservability:
    """Wrap the complete FastAPI stack so even generated 500 responses receive an ID."""

    def __init__(
        self, app: ASGIApp, counters: RequestMetrics, templates: Iterable[str] = ()
    ) -> None:
        self.app = app
        self.counters = counters
        self.templates = [(compile_path(path)[0], path) for path in sorted(set(templates))]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = [
            value for key, value in scope.get("headers", []) if key.lower() == b"x-request-id"
        ]
        candidate = supplied[0].decode("latin-1") if len(supplied) == 1 else ""
        request_id = candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate) else uuid4().hex
        token = request_id_context.set(request_id)
        started = perf_counter()
        status = 500
        self.counters.begin()

        async def correlated_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = dict(message)
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ] + [(b"x-request-id", request_id.encode("ascii"))]
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        finally:
            elapsed = perf_counter() - started
            method = scope.get("method", "OTHER")
            method = method if method in METHODS else "OTHER"
            path: object = getattr(scope.get("route"), "path", None)
            route = path if isinstance(path, str) else "unmatched"
            # Included routers may expose their original unprefixed route in scope.
            # Match only the fixed registered templates; never record a raw URL.
            route = next(
                (
                    template
                    for pattern, template in self.templates
                    if pattern.fullmatch(scope["path"])
                ),
                route,
            )
            self.counters.finish(method, route, status, elapsed)
            logger.info(
                "http_request",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "route": route,
                    "status_code": status,
                    "duration_seconds": round(elapsed, 6),
                },
            )
            request_id_context.reset(token)


class ObservedAPI(FastAPI):
    """Keep FastAPI/OpenAPI interfaces while observing the outermost error stack."""

    def build_middleware_stack(self) -> ASGIApp:
        templates = set(self.openapi()["paths"])
        for route in self.routes:
            path: object = getattr(route, "path", None)
            if isinstance(path, str):
                templates.add(path)
        return RequestObservability(super().build_middleware_stack(), metrics, templates)
