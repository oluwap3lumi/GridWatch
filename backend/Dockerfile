FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout=180 --retries=5 uv==0.13.0
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
ENV UV_HTTP_TIMEOUT=180
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/logging.json ./logging.json
COPY backend/start.sh ./start.sh
COPY data ./data
COPY ml ./ml
ENV PATH="/app/.venv/bin:$PATH"

FROM base AS test
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
COPY backend/tests ./tests
CMD ["pytest", "tests/integration", "-v"]

FROM base AS runtime
EXPOSE 8000
CMD ["sh", "start.sh"]
