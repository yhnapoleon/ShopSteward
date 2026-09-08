"""Independent worker process: claim, parse, index, verify, then fenced READY."""

import asyncio
import hashlib
import inspect
import logging
import socket
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update

from .config import Settings, create_embedding
from .contracts import Candidate, EmbeddingProfile, IngestionRequest, Projection, validate_vectors
from .db import create_session_factory
from .models import Chunk, IndexGeneration, Job, ProjectionRecord
from .publication import manifest_hash, retry_delay, verify_original

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Claim:
    id: str
    generation_id: str
    lease_token: str
    attempt: int
    request: dict
    projection: dict


async def claim_job(session_factory, *, lease_seconds=120, owner=None):
    async with session_factory.begin() as session:
        due = or_(
            and_(Job.state.in_(["PENDING", "RETRY_WAIT"]), Job.next_attempt_at <= func.now()),
            and_(Job.state == "RUNNING", Job.lease_until <= func.now()),
        )
        job = await session.scalar(
            select(Job)
            .where(due)
            .order_by(Job.next_attempt_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        generation = await session.get(IndexGeneration, job.generation_id)
        if job.attempt >= min(job.attempt_limit, job.total_attempt_limit):
            job.state, job.error = "FAILED", "attempt_limit"
            generation.state = "FAILED"
            job.lease_until = None
            return None
        projection = await session.get(ProjectionRecord, generation.version_id)
        if job.attempt:
            # Every attempt writes a separate physical generation. A stale external
            # upsert cannot corrupt the replacement even after losing its DB lease.
            generation.state = "FAILED"
            generation = IndexGeneration(
                id=uuid4().hex,
                version_id=generation.version_id,
                profile_id=generation.profile_id,
                metadata_revision=projection.metadata_revision,
            )
            session.add(generation)
            await session.flush()
            job.generation_id = generation.id
        generation.metadata_revision = projection.metadata_revision
        now = await session.scalar(select(func.clock_timestamp()))
        job.state, job.error = "RUNNING", None
        job.attempt += 1
        job.lease_token = uuid4().hex
        job.lease_owner = owner or socket.gethostname()
        job.lease_until = now + timedelta(seconds=lease_seconds)
        return Claim(
            job.id, job.generation_id, job.lease_token, job.attempt, job.request, projection.payload
        )


def lease_predicate(claim):
    return (
        Job.id == claim.id,
        Job.state == "RUNNING",
        Job.lease_token == claim.lease_token,
        Job.generation_id == claim.generation_id,
        Job.lease_until > func.clock_timestamp(),
    )


async def renew_lease(session_factory, claim, lease_seconds):
    async with session_factory.begin() as session:
        result = await session.execute(
            update(Job)
            .where(*lease_predicate(claim))
            .values(lease_until=func.clock_timestamp() + timedelta(seconds=lease_seconds))
        )
        return result.rowcount == 1


async def complete_job(session_factory, claim, chunks, digest, parse_manifest):
    async with session_factory.begin() as session:
        job = await session.scalar(select(Job).where(*lease_predicate(claim)).with_for_update())
        if job is None:
            return False
        if manifest_hash(chunks) != digest:
            raise ValueError("manifest hash mismatch")
        projection = await session.get(
            ProjectionRecord, claim.projection["version_id"], with_for_update=True
        )
        if projection.metadata_revision != claim.projection["metadata_revision"]:
            raise RuntimeError("projection_changed_during_ingestion")
        generation = await session.get(IndexGeneration, claim.generation_id, with_for_update=True)
        if generation.state != "BUILDING":
            return False
        for chunk in chunks:
            session.add(
                Chunk(
                    generation_id=claim.generation_id,
                    chunk_id=chunk["chunk_id"],
                    version_id=chunk["version_id"],
                    store_id=chunk["store_id"],
                    metadata_revision=chunk["metadata_revision"],
                    content_sha256=chunk["content_sha256"],
                    payload=chunk,
                )
            )
        await session.flush()
        persisted = (
            await session.scalars(
                select(Chunk.payload).where(Chunk.generation_id == claim.generation_id)
            )
        ).all()
        if len(persisted) != len(chunks) or manifest_hash(persisted) != digest:
            raise RuntimeError("durable_chunk_manifest_mismatch")
        # Recheck real DB time after flushing; a lease may expire within this transaction.
        if not await session.scalar(select(Job.id).where(*lease_predicate(claim))):
            raise RuntimeError("lease_expired_before_ready")
        generation.state, generation.chunk_count = "READY", len(chunks)
        generation.manifest_hash = digest
        generation.manifest = {
            **parse_manifest,
            "chunk_ids": [c["chunk_id"] for c in chunks],
            "chunk_hashes": {c["chunk_id"]: c["content_sha256"] for c in chunks},
        }
        generation.ready_at = await session.scalar(select(func.clock_timestamp()))
        job.state, job.error, job.lease_until = "SUCCEEDED", None, None
        return True


async def fail_job(session_factory, claim, error):
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    permanent = isinstance(error, (ValueError, FileNotFoundError)) or (
        status is not None and 400 <= status < 500 and status not in (408, 429)
    )
    retry_after = None
    if status == 429:
        with suppress(ValueError, TypeError):
            retry_after = float(response.headers.get("Retry-After"))
    async with session_factory.begin() as session:
        job = await session.scalar(select(Job).where(*lease_predicate(claim)).with_for_update())
        if job is None:
            return False
        limit = min(job.attempt_limit, job.total_attempt_limit)
        job.state = "FAILED" if permanent or job.attempt >= limit else "RETRY_WAIT"
        # Never persist external exception text that may contain original content or credentials.
        job.error = type(error).__name__ + (f":http_{status}" if status else "")
        now = await session.scalar(select(func.clock_timestamp()))
        job.next_attempt_at = now + timedelta(seconds=retry_delay(job.attempt, retry_after))
        job.lease_until = None
        generation = await session.get(IndexGeneration, job.generation_id)
        generation.state = "FAILED"
        return True


def candidate_chunks(claim, parsed, raw_chunks):
    projection = Projection.model_validate(claim.projection)
    ref = IngestionRequest.model_validate(claim.request).original
    result = []
    needs_ocr = any("OCR_REQUIRED" in warning for warning in parsed.warnings) or any(
        item.get("reason") == "OCR_REQUIRED" for item in parsed.coverage.get("items", [])
    )
    for raw in raw_chunks:
        text = raw["text"]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if raw.get("content_sha256", digest) != digest:
            raise ValueError("parser chunk text hash mismatch")
        candidate = Candidate(
            document_id=projection.document_id,
            version_id=ref.version_id,
            generation_id=claim.generation_id,
            chunk_id=raw.get("chunk_id", raw.get("id")),
            metadata_revision=projection.metadata_revision,
            text=text,
            title=projection.title,
            store_id=projection.store_id,
            locator=raw["locator"],
            content_sha256=digest,
            original_sha256=ref.sha256,
            source_url=projection.provenance.source_url,
            source_kind=projection.provenance.source_kind,
            synthetic=projection.provenance.synthetic,
            jurisdiction=projection.provenance.jurisdiction,
            entity_refs=projection.entity_refs,
            valid_from=projection.valid_from,
            valid_until=projection.valid_until,
            section_path=raw["locator"].get("section_path", []),
            parsing_status=parsed.status,
            ocr_status="NOT_RUN" if needs_ocr else "NOT_REQUIRED",
        )
        # Keep parser manifests for parent reconstruction, but send only Candidate fields to index.
        result.append({**raw, **candidate.model_dump(mode="json")})
    manifest_hash(result)
    return result


async def invoke_parser(function, *args):
    if inspect.iscoroutinefunction(function):
        return await function(*args)
    result = await asyncio.to_thread(function, *args)
    return await result if inspect.isawaitable(result) else result


async def index_rows(
    chunks, profile_id, embedder=None, embedding_profile=None, *, deadline_ms=8000
):
    """Build actual IndexPort payloads; synthetic vectors belong only in protocol tests."""
    candidates = [{k: v for k, v in c.items() if k in Candidate.model_fields} for c in chunks]
    if profile_id == "lexical-v1":
        return candidates
    if profile_id != "hybrid-v1" or embedder is None or not embedding_profile:
        raise ValueError("ingestion profile is unknown or not configured")
    from .retrieval.search import profile_key

    profile = EmbeddingProfile.model_validate(embedding_profile).model_dump()
    identifier = profile_key(profile)
    rows = []
    for offset in range(0, len(chunks), 64):
        batch = chunks[offset : offset + 64]
        vectors = await embedder.embed(
            [chunk["text"] for chunk in batch],
            input_type="document",
            profile=profile,
            deadline_ms=deadline_ms,
        )
        validate_vectors(vectors, len(batch), profile["dimensions"])
        for ordinal, (chunk, vector) in enumerate(zip(batch, vectors, strict=True), start=offset):
            chunk.update(
                vector=vector,
                embedding_profile=identifier,
                embedding_profile_config=profile,
                embedding_input_type="document",
            )
            rows.append(
                {
                    "candidate": candidates[ordinal],
                    "vector": vector,
                    "embedding_profile": identifier,
                }
            )
    return rows


async def ingest_once(
    settings=None,
    *,
    session_factory=None,
    blob=None,
    index=None,
    parser=None,
    chunker=None,
    embedder=None,
    embedding_profile=None,
):
    settings = settings or Settings()
    owned = session_factory is None
    session_factory = session_factory or create_session_factory(settings)
    client = None
    try:
        if blob is None:
            from .storage.local import LocalBlobStore

            blob = LocalBlobStore(settings.storage_root)
        if parser is None:
            from .parsing import parse_original

            parser = parse_original
        if chunker is None:
            from .parsing.chunking import chunk_blocks

            chunker = chunk_blocks
        if index is None:
            if not settings.opensearch_url:
                raise RuntimeError("KNOWLEDGE_OPENSEARCH_URL is not configured")
            import httpx

            from .retrieval.opensearch import OpenSearchIndex

            client = httpx.AsyncClient(timeout=30)
            index = OpenSearchIndex(client, settings.opensearch_url, settings.index_prefix)
        if not callable(getattr(index, "verify_generation", None)):
            raise RuntimeError("IndexPort requires verify_generation before READY can be proven")
        claim = await claim_job(
            session_factory,
            lease_seconds=settings.lease_seconds,
        )
        if claim is None:
            return False

        async def heartbeat():
            while True:
                await asyncio.sleep(settings.lease_seconds / 3)
                if not await renew_lease(session_factory, claim, settings.lease_seconds):
                    return

        renewal = asyncio.create_task(heartbeat())
        try:
            request = IngestionRequest.model_validate(claim.request)
            if request.profile_id not in settings.enabled_profiles() and not (
                request.profile_id == "hybrid-v1" and embedder is not None and embedding_profile
            ):
                raise ValueError("ingestion profile is unknown or not configured")
            content = await blob.get(request.original.storage_key)
            verify_original(request.original, content)
            parsed = await invoke_parser(parser, request.original, content)
            if parsed.status not in ("COMPLETE", "PARTIAL"):
                raise ValueError("original has no supported searchable text: " + parsed.status)
            raw = await invoke_parser(chunker, parsed.blocks, {"id": request.profile_id})
            chunks = candidate_chunks(claim, parsed, raw)
            if request.profile_id == "hybrid-v1" and embedder is None:
                if client is None:
                    import httpx

                    client = httpx.AsyncClient(timeout=30)
                embedder = create_embedding(settings, client)
            indexed = await index_rows(
                chunks,
                request.profile_id,
                embedder,
                embedding_profile or settings.embedding_profile(),
                deadline_ms=settings.embedding_deadline_ms,
            )
            await index.upsert(claim.generation_id, indexed)
            if not await index.verify_generation(claim.generation_id, indexed):
                raise RuntimeError("index_count_hash_or_search_visibility_mismatch")
            parse_manifest = {
                "status": parsed.status,
                "coverage": parsed.coverage,
                "warnings": parsed.warnings,
                "parser_profile": getattr(parsed, "parser_profile", {}),
            }
            await complete_job(
                session_factory, claim, chunks, manifest_hash(chunks), parse_manifest
            )
        except Exception as exc:
            await fail_job(session_factory, claim, exc)
            logger.warning(
                "knowledge ingestion attempt failed job=%s category=%s",
                claim.id,
                type(exc).__name__,
            )
        finally:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
        return True
    finally:
        if client is not None:
            await client.aclose()
        if owned:
            await session_factory.kw["bind"].dispose()


async def main():
    settings = Settings()
    sessions = create_session_factory(settings)
    try:
        while True:
            try:
                worked = await ingest_once(settings, session_factory=sessions)
            except Exception as exc:
                logger.error("knowledge worker unavailable category=%s", type(exc).__name__)
                worked = False
            if not worked:
                await asyncio.sleep(settings.poll_seconds)
    finally:
        await sessions.kw["bind"].dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
