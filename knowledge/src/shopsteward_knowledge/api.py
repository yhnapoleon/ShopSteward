"""Private service API. Only the backend service may supply authorization scopes."""

import asyncio
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import AwareDatetime, Field, ValidationError, model_validator
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings, create_embedding, create_reranker
from .contracts import (
    DTO,
    EvidenceRequest,
    Id,
    IngestionReceipt,
    IngestionRequest,
    Projection,
    SearchRequest,
    SearchResponse,
)
from .db import create_session_factory, database_ready, make_evidence_loader, make_scope_filter
from .ingestion import ConflictError, IngestionService


class RelationInput(DTO):
    subject: str = Field(min_length=1, max_length=256)
    predicate: Id
    object: str = Field(min_length=1, max_length=256)
    confirmed: bool = False
    conditions: dict = Field(default_factory=dict, max_length=30)
    evidence_chunk_ids: list[Id] = Field(min_length=1, max_length=20)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def validity(self):
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("invalid relation validity interval")
        return self


class RelationBatch(DTO):
    generation_id: Id
    metadata_revision: int = Field(ge=1)
    edges: list[RelationInput] = Field(min_length=1, max_length=200)


def create_app(settings=None, *, session_factory=None, blob=None, search_service=None):
    settings = settings or Settings()
    owned_sessions = session_factory is None and settings.database_url is not None
    if owned_sessions:
        session_factory = create_session_factory(settings)

    @asynccontextmanager
    async def lifespan(app):
        client = None
        if (
            app.state.search_service is None
            and session_factory is not None
            and settings.opensearch_url
        ):
            import httpx

            from .retrieval.opensearch import OpenSearchIndex
            from .retrieval.parent import PGParentExpander
            from .retrieval.relations import PGRelationRetriever
            from .retrieval.search import SearchService

            client = httpx.AsyncClient(timeout=8)
            app.state.index = OpenSearchIndex(
                client, settings.opensearch_url, settings.index_prefix
            )
            app.state.search_service = SearchService(
                app.state.index,
                evidence_loader=make_evidence_loader(session_factory),
                scope_filter=make_scope_filter(session_factory),
                relation_loader=PGRelationRetriever(session_factory).relation_paths,
                parent_expander=PGParentExpander(session_factory).expand,
                embedder=create_embedding(settings, client),
                embedding_profile=settings.embedding_profile(),
                reranker=create_reranker(settings, client),
            )
        try:
            yield
        finally:
            if client is not None:
                await client.aclose()
            if owned_sessions:
                await session_factory.kw["bind"].dispose()

    app = FastAPI(title="ShopSteward Knowledge", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.blob = blob
    app.state.search_service = search_service
    app.state.index = getattr(search_service, "index", None)

    async def authenticate(request: Request):
        configured = settings.service_key
        if configured is None:
            raise HTTPException(503, "service identity is not configured")
        value = request.headers.get("Authorization", "")
        scheme, _, token = value.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.encode(), configured.get_secret_value().encode()
        ):
            raise HTTPException(
                401, "invalid service credential", headers={"WWW-Authenticate": "Bearer"}
            )

    def ingestion_service():
        if app.state.session_factory is None:
            raise HTTPException(503, "knowledge database is not configured")
        if app.state.blob is None:
            from .storage.local import LocalBlobStore

            app.state.blob = LocalBlobStore(settings.storage_root)
        return IngestionService(
            app.state.session_factory,
            app.state.blob,
            enabled_profiles=settings.enabled_profiles(),
            max_attempts=settings.max_attempts,
            max_total_attempts=settings.max_total_attempts,
        )

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(OSError)
    async def database_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503, content={"detail": "knowledge persistence unavailable"}
        )

    @app.get("/health/live")
    async def live():
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready():
        try:
            async with asyncio.timeout(5):
                healthy = await database_ready(app.state.session_factory)
                if settings.opensearch_url:
                    healthy = (
                        healthy and app.state.index is not None and await app.state.index.ready()
                    )
        except Exception:
            healthy = False
        if not healthy or settings.service_key is None or app.state.search_service is None:
            raise HTTPException(503, "knowledge service dependencies are not ready")
        return {"status": "ready"}

    private = [Depends(authenticate)]

    @app.post(
        "/internal/v1/ingestions",
        status_code=202,
        response_model=IngestionReceipt,
        dependencies=private,
    )
    async def ingest(
        file: Annotated[UploadFile, File()],
        metadata: Annotated[str, Form()],
        idempotency_key: Annotated[str, Header(min_length=1, max_length=200)],
    ):
        service = ingestion_service()
        try:
            if len(metadata) > 128 * 1024:
                raise HTTPException(413, "metadata is too large")
            request = IngestionRequest.model_validate_json(metadata)
            content = await file.read(settings.max_upload_bytes + 1)
            if len(content) > settings.max_upload_bytes:
                raise HTTPException(413, "original exceeds upload size limit")
            return await service.accept(request, content, idempotency_key)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, "invalid ingestion metadata or original content") from exc
        finally:
            await file.close()

    @app.get("/internal/v1/jobs/{job_id}", response_model=IngestionReceipt, dependencies=private)
    @app.get(
        "/internal/v1/ingestions/{job_id}", response_model=IngestionReceipt, dependencies=private
    )
    async def get_job(job_id: str):
        receipt = await ingestion_service().receipt(job_id)
        if receipt is None:
            raise HTTPException(404, "job not found")
        return receipt

    @app.post(
        "/internal/v1/ingestions/{job_id}/retry",
        status_code=202,
        response_model=IngestionReceipt,
        dependencies=private,
    )
    async def retry_job(
        job_id: str, idempotency_key: Annotated[str, Header(min_length=1, max_length=200)]
    ):
        try:
            receipt = await ingestion_service().retry(job_id, idempotency_key)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, "invalid retry key") from exc
        if receipt is None:
            raise HTTPException(404, "job not found")
        return receipt

    @app.post("/internal/v1/projections", dependencies=private)
    async def project(projection: Projection):
        try:
            return {
                "decision": await ingestion_service().project(projection),
                "version_id": projection.version_id,
                "metadata_revision": projection.metadata_revision,
            }
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/internal/v1/search", response_model=SearchResponse, dependencies=private)
    async def search(request: SearchRequest):
        if request.profile_id not in settings.enabled_profiles():
            raise HTTPException(422, "retrieval profile is unknown or not configured")
        if request.scope.expires_at <= datetime.now(UTC):
            raise HTTPException(422, "search scope expired")
        service = app.state.search_service
        if service is None:
            raise HTTPException(503, "search service is not configured")
        return await service.search(request)

    @app.post("/internal/v1/evidence", response_model=SearchResponse, dependencies=private)
    async def evidence(request: EvidenceRequest):
        if request.scope.expires_at <= datetime.now(UTC):
            raise HTTPException(422, "search scope expired")
        service = app.state.search_service
        if service is None:
            raise HTTPException(503, "search service is not configured")
        return await service.evidence(request)

    @app.post("/internal/v1/relations", dependencies=private)
    async def relations(batch: RelationBatch):
        try:
            return await ingestion_service().add_relations(batch)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc

    return app


app = create_app()
