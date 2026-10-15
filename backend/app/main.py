"""GridWatch FastAPI entry point."""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.v1.assets import router as assets_router
from app.api.v1.health import health, router
from app.api.v1.model import router as model_router
from app.api.v1.outages import router as outages_router
from app.api.v1.risk import router as risk_router
from app.core.observability import ObservedAPI
from app.schemas.assets import ErrorResponse
from app.schemas.health import HealthResponse

app = ObservedAPI(title="GridWatch", version="0.1.0")


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Return a typed safe error; server logging records exception type only."""
    return JSONResponse(
        status_code=500, content=ErrorResponse(detail="Internal server error").model_dump()
    )


app.include_router(router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(outages_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(model_router, prefix="/api/v1")
app.add_api_route("/health", health, response_model=HealthResponse, include_in_schema=False)
