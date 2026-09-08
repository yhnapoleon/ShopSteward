"""Lightweight, strict HTTP boundary. Caller owns the client and transaction boundaries."""

from contextlib import asynccontextmanager

import httpx
from pydantic import ValidationError
from shopsteward_knowledge.contracts import IngestionReceipt, RelationPath, SearchResponse

from app.core.errors import AppError


def search_response(data):
    """Keep valid evidence when an optional relation path violates its typed contract."""
    invalid_paths = False
    candidates = data.get("candidates", []) if isinstance(data, dict) else []
    if isinstance(candidates, list) and len(candidates) <= 20:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            paths = candidate.get("relation_paths", [])
            if not isinstance(paths, list) or len(paths) > 20:
                continue  # The strict response contract rejects malformed/over-budget lists.
            valid = []
            for path in paths:
                try:
                    valid.append(RelationPath.model_validate(path).model_dump(mode="json"))
                except ValidationError:
                    invalid_paths = True
            candidate["relation_paths"] = valid
    result = SearchResponse.model_validate(data)
    if invalid_paths:
        result.degraded = True
        result.warnings.append("INVALID_RELATION_PATH_REMOVED")
    return result


class KnowledgeClient:
    def __init__(self, http):
        self.http = http

    async def ingest(self, request, content, key):
        response = await self.http.post(
            "/internal/v1/ingestions",
            headers={"Idempotency-Key": key},
            data={"metadata": request.model_dump_json()},
            files={"file": ("original", content, request.original.mime)},
        )
        response.raise_for_status()
        return IngestionReceipt.model_validate(response.json())

    async def job(self, job_id):
        response = await self.http.get(f"/internal/v1/ingestions/{job_id}")
        response.raise_for_status()
        return IngestionReceipt.model_validate(response.json())

    async def retry(self, job_id, key):
        response = await self.http.post(
            f"/internal/v1/ingestions/{job_id}/retry", headers={"Idempotency-Key": key}
        )
        response.raise_for_status()
        return IngestionReceipt.model_validate(response.json())

    async def project(self, projection, key):
        response = await self.http.post(
            "/internal/v1/projections",
            headers={"Idempotency-Key": key},
            json=projection.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def search(self, request):
        response = await self.http.post("/internal/v1/search", json=request.model_dump(mode="json"))
        response.raise_for_status()
        return search_response(response.json())

    async def evidence(self, request):
        response = await self.http.post(
            "/internal/v1/evidence", json=request.model_dump(mode="json")
        )
        response.raise_for_status()
        return search_response(response.json())


@asynccontextmanager
async def connect(settings):
    if not settings.knowledge_service_enabled or not settings.knowledge_service_key:
        raise AppError(
            503, "KNOWLEDGE_NOT_CONFIGURED", "Knowledge service is not configured", retryable=True
        )
    async with httpx.AsyncClient(
        base_url=settings.knowledge_service_url,
        headers={"Authorization": "Bearer " + settings.knowledge_service_key.get_secret_value()},
        timeout=settings.knowledge_http_timeout_seconds,
        follow_redirects=False,
    ) as http:
        yield KnowledgeClient(http)
