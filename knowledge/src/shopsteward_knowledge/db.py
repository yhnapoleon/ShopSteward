from datetime import UTC, datetime

from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import Settings
from .contracts import Candidate, Projection
from .models import Chunk, IndexGeneration, ProjectionRecord


def create_session_factory(settings: Settings):
    if not settings.database_url:
        raise RuntimeError("KNOWLEDGE_DATABASE_URL is not configured")
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"timeout": 5, "command_timeout": 15},
    )
    return async_sessionmaker(engine, expire_on_commit=False)


async def database_ready(session_factory) -> bool:
    if session_factory is None:
        return False
    try:
        async with session_factory() as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != "knowledge_0002":
                return False
            for table in (
                "knowledge_projections",
                "knowledge_originals",
                "knowledge_jobs",
                "knowledge_index_generations",
                "knowledge_chunks",
                "knowledge_relations",
                "knowledge_job_retries",
            ):
                await session.execute(text(f"SELECT 1 FROM {table} LIMIT 0"))
            return True
    except Exception:
        return False


def visible_projection(payload, scope):
    projection = Projection.model_validate(payload)
    return (
        scope.expires_at > datetime.now(UTC)
        and projection.status == "active"
        and projection.store_id == scope.store_id
        and (projection.valid_from is None or projection.valid_from <= scope.as_of)
        and (projection.valid_until is None or scope.as_of < projection.valid_until)
    )


def scope_query(scope):
    triples = [(v.version_id, v.generation_id, v.metadata_revision) for v in scope.allowed_versions]
    return (
        select(ProjectionRecord, IndexGeneration)
        .join(IndexGeneration, IndexGeneration.version_id == ProjectionRecord.version_id)
        .where(
            ProjectionRecord.store_id == scope.store_id,
            IndexGeneration.state == "READY",
            # B3 MVP: changed metadata needs a new immutable generation and backend CAS republish.
            IndexGeneration.metadata_revision == ProjectionRecord.metadata_revision,
            tuple_(
                ProjectionRecord.version_id, IndexGeneration.id, ProjectionRecord.metadata_revision
            ).in_(triples),
        )
    )


def make_scope_filter(session_factory):
    async def filter_scope(scope):
        if not scope.allowed_versions or scope.expires_at <= datetime.now(UTC):
            return scope.model_copy(update={"allowed_versions": []})
        async with session_factory() as session:
            rows = (await session.execute(scope_query(scope))).all()
            valid = {
                (p.version_id, g.id, p.metadata_revision)
                for p, g in rows
                if visible_projection(p.payload, scope)
            }
        return scope.model_copy(
            update={
                "allowed_versions": [
                    v
                    for v in scope.allowed_versions
                    if (v.version_id, v.generation_id, v.metadata_revision) in valid
                ]
            }
        )

    return filter_scope


def overlay_candidate(payload, projection_payload):
    projection = Projection.model_validate(projection_payload)
    values = {k: v for k, v in payload.items() if k in Candidate.model_fields}
    values.update(
        title=projection.title,
        document_id=projection.document_id,
        store_id=projection.store_id,
        metadata_revision=projection.metadata_revision,
        entity_refs=projection.entity_refs,
        valid_from=projection.valid_from,
        valid_until=projection.valid_until,
        source_kind=projection.provenance.source_kind,
        source_url=projection.provenance.source_url,
        synthetic=projection.provenance.synthetic,
        jurisdiction=projection.provenance.jurisdiction,
    )
    return Candidate.model_validate(values)


def make_evidence_loader(session_factory):
    async def evidence(scope, chunk_ids):
        if not chunk_ids or not scope.allowed_versions or scope.expires_at <= datetime.now(UTC):
            return []
        if len(chunk_ids) > 20:
            raise ValueError("evidence accepts at most 20 chunk IDs")
        async with session_factory() as session:
            query = (
                scope_query(scope)
                .add_columns(Chunk)
                .join(Chunk, Chunk.generation_id == IndexGeneration.id)
                .where(Chunk.store_id == scope.store_id, Chunk.chunk_id.in_(chunk_ids))
            )
            rows = (await session.execute(query)).all()
            values = [
                overlay_candidate(c.payload, p.payload)
                for p, g, c in rows
                if c.version_id == p.version_id and visible_projection(p.payload, scope)
            ]
        order = {identifier: ordinal for ordinal, identifier in enumerate(chunk_ids)}
        return sorted(
            values, key=lambda candidate: (order[candidate.chunk_id], candidate.generation_id)
        )

    return evidence
