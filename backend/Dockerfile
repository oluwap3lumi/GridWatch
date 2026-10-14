FROM python:3.12-slim
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout=180 --retries=5 uv==0.13.0
WORKDIR /app
COPY pyproject.toml uv.lock ./
ENV UV_HTTP_TIMEOUT=180
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
