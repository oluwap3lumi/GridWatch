"""Health response contract."""

from typing import Literal

from app.schemas.base import ApiModel


class HealthResponse(ApiModel):
    """API process liveness; database readiness is checked by Compose."""

    status: Literal["ok"] = "ok"
