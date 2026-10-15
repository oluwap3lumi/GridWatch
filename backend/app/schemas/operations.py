"""Typed readiness and bounded, process-local HTTP metrics."""

from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel


class ReadinessResponse(ApiModel):
    status: Literal["ready", "not_ready"]


class RouteMetric(ApiModel):
    method: str
    route: str
    status_code: int
    requests: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)


class MetricsResponse(ApiModel):
    scope: Literal["process"] = "process"
    uptime_seconds: float = Field(ge=0)
    in_flight: int = Field(ge=0)
    requests: int = Field(ge=0)
    routes: list[RouteMetric]
