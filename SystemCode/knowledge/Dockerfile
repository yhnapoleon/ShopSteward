# syntax=docker/dockerfile:1
# Replace build args with reviewed @sha256 references after the first real build.
ARG PYTHON_IMAGE=python:3.12-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.10
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY agent/pyproject.toml agent/pyproject.toml
COPY ml/pyproject.toml ml/pyproject.toml
COPY simulation/pyproject.toml simulation/pyproject.toml
COPY knowledge/ knowledge/
RUN uv sync --locked --package shopsteward-knowledge --no-dev --no-editable \
    --extra service --extra parsers --extra opensearch

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    KNOWLEDGE_STORAGE_ROOT=/data/knowledge
RUN groupadd --gid 10001 knowledge && useradd --uid 10001 --gid knowledge \
    --no-create-home knowledge && mkdir -p /data/knowledge && chown 10001:10001 /data/knowledge
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --from=builder /app/knowledge/alembic.ini /app/knowledge/alembic.ini
COPY --from=builder /app/knowledge/migrations /app/knowledge/migrations
USER 10001:10001
VOLUME ["/data/knowledge"]
EXPOSE 8020
CMD ["python", "-m", "uvicorn", "shopsteward_knowledge.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8020"]
