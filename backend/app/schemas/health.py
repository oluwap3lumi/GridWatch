"""Health response contract."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """API process liveness; database readiness is checked by Compose."""

    status: Literal["ok"] = "ok"
