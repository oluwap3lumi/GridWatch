"""GridWatch FastAPI entry point."""

from fastapi import FastAPI

from app.api.v1.health import health, router
from app.schemas.health import HealthResponse

app = FastAPI(title="GridWatch", version="0.1.0")
app.include_router(router, prefix="/api/v1")
app.add_api_route("/health", health, response_model=HealthResponse, include_in_schema=False)
