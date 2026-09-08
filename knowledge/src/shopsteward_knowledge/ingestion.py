"""Durable, idempotent ingestion acceptance and monotonic metadata projections."""

from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from .contracts import IngestionReceipt, IngestionRequest, Projection
from .models import Chunk, IndexGeneration, Job, Original, ProjectionRecord, Relation, RetryCommand
from .publication import payload_hash, projection_decision, retry_attempt_limit, verify_original


class ConflictError(ValueError):
    pass


async def lock_key(session, key: str) -> None:
    # Advisory transaction locks also serialize first inserts (there is no row to lock yet).
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
    )


async def apply_projection(session, projection: Projection) -> str:
    await lock_key(session, "projection:" + projection.version_id)
    existing = await session.get(ProjectionRecord, projection.version_id, with_for_update=True)
    payload = projection.model_dump(mode="json")
    incoming = {
        "metadata_revision": projection.metadata_revision,
        "payload_hash": payload_hash(payload),
    }
    if existing and (
        existing.document_id != projection.document_id or existing.store_id != projection.store_id
    ):
        raise ConflictError("projection version ownership is immutable")
    try:
        decision = projection_decision(
            {"metadata_revision": existing.metadata_revision, "payload_hash": existing.payload_hash}
            if existing
            else None,
            incoming,
        )
    except ValueError as exc:
        raise ConflictError(str(exc)) from exc
    if decision == "apply":
        if existing is None:
            existing = ProjectionRecord(
                version_id=projection.version_id,
                document_id=projection.document_id,
                store_id=projection.store_id,
            )
            session.add(existing)
        existing.metadata_revision = projection.metadata_revision
        existing.payload_hash = incoming["payload_hash"]
        existing.payload = payload
        await session.flush()
    return decision


def job_receipt(job: Job, generation: IndexGeneration) -> IngestionReceipt:
    return IngestionReceipt(
        job_id=job.id,
        generation_id=job.generation_id,
        state=job.state,
        attempt=job.attempt,
        error=job.error,
        manifest_hash=generation.manifest_hash if job.state == "SUCCEEDED" else None,
    )


class IngestionService:
    def __init__(
        self, session_factory, blob, *, enabled_profiles=None, max_attempts=5, max_total_attempts=15
    ):
        if not 1 <= max_attempts <= max_total_attempts <= 100:
            raise ValueError("invalid total attempt budget")
        self.session_factory = session_factory
        self.blob = blob
        self.enabled_profiles = enabled_profiles if enabled_profiles is not None else {"lexical-v1"}
        self.max_attempts, self.max_total_attempts = max_attempts, max_total_attempts

    async def project(self, projection: Projection) -> str:
        async with self.session_factory.begin() as session:
            return await apply_projection(session, projection)

    async def accept(self, request: IngestionRequest, content: bytes, key: str) -> IngestionReceipt:
        if request.profile_id not in self.enabled_profiles:
            raise ValueError("ingestion profile is unknown or not configured")
        if not key or len(key) > 200 or not key.strip():
            raise ValueError("Idempotency-Key must contain 1 to 200 characters")
        verify_original(request.original, content)
        payload = request.model_dump(mode="json")
        digest = payload_hash(payload)
        try:
            async with self.session_factory.begin() as session:
                await lock_key(session, "ingestion:" + key)
                job = await session.scalar(select(Job).where(Job.idempotency_key == key))
                if job:
                    if job.payload_hash != digest:
                        raise ConflictError("Idempotency-Key already used with different payload")
                    generation = await session.get(IndexGeneration, job.generation_id)
                    return job_receipt(job, generation)
                await apply_projection(session, request.projection)
                ref = request.original
                original = await session.get(Original, ref.version_id)
                if original:
                    if any(
                        getattr(original, name) != getattr(ref, name)
                        for name in ("sha256", "storage_key", "size_bytes", "mime")
                    ):
                        raise ConflictError("original version bytes and reference are immutable")
                else:
                    session.add(Original(**ref.model_dump()))
                    await session.flush()
                await self.blob.put(ref.storage_key, content, ref.sha256)
                generation = IndexGeneration(
                    id=uuid4().hex,
                    version_id=ref.version_id,
                    profile_id=request.profile_id,
                    metadata_revision=request.projection.metadata_revision,
                )
                session.add(generation)
                await session.flush()
                job = Job(
                    id=uuid4().hex,
                    idempotency_key=key,
                    payload_hash=digest,
                    request=payload,
                    generation_id=generation.id,
                    attempt_limit=self.max_attempts,
                    total_attempt_limit=self.max_total_attempts,
                )
                session.add(job)
                await session.flush()
                return job_receipt(job, generation)
        except (IntegrityError, FileExistsError) as exc:
            raise ConflictError(
                "original storage identity conflicts with an existing version"
            ) from exc

    async def retry(self, job_id: str, key: str) -> IngestionReceipt | None:
        if not key or len(key) > 200 or not key.strip():
            raise ValueError("Idempotency-Key must contain 1 to 200 characters")
        async with self.session_factory.begin() as session:
            await lock_key(session, "retry:" + key)
            saved = await session.get(RetryCommand, key)
            if saved:
                if saved.job_id != job_id:
                    raise ConflictError("retry key already belongs to a different job")
                return IngestionReceipt.model_validate(saved.receipt)
            # Same lock order as completion: job, projection, then generation.
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None:
                return None
            now = await session.scalar(select(func.clock_timestamp()))
            if job.state != "FAILED" or (job.lease_until and job.lease_until > now):
                raise ConflictError("retry requires terminal FAILED with no active lease")
            request = IngestionRequest.model_validate(job.request)
            projection = await session.get(
                ProjectionRecord, request.original.version_id, with_for_update=True
            )
            if (
                projection is None
                or projection.metadata_revision != request.projection.metadata_revision
                or projection.payload_hash
                != payload_hash(request.projection.model_dump(mode="json"))
                or projection.payload.get("status") != "active"
            ):
                raise ConflictError(
                    "retry projection is superseded or archived; request a new ingestion"
                )
            if request.profile_id not in self.enabled_profiles:
                raise ConflictError("retry profile is not configured")
            generation = await session.get(IndexGeneration, job.generation_id, with_for_update=True)
            if generation.state == "READY":
                raise ConflictError("retry cannot mutate a READY generation")
            try:
                ceiling = retry_attempt_limit(
                    job.attempt, self.max_attempts, job.total_attempt_limit
                )
            except ValueError as exc:
                raise ConflictError(str(exc)) from exc
            job.attempt_limit = ceiling
            job.state, job.error = "PENDING", None
            job.next_attempt_at = now
            job.lease_token = job.lease_owner = job.lease_until = None
            # Keep the old failed generation unchanged. claim_job creates the new one.
            receipt = job_receipt(job, generation)
            session.add(
                RetryCommand(
                    idempotency_key=key, job_id=job.id, receipt=receipt.model_dump(mode="json")
                )
            )
            await session.flush()
            return receipt

    async def receipt(self, job_id: str) -> IngestionReceipt | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(Job, IndexGeneration)
                    .join(IndexGeneration, Job.generation_id == IndexGeneration.id)
                    .where(Job.id == job_id)
                )
            ).first()
            return job_receipt(*row) if row else None

    async def add_relations(self, batch):
        async with self.session_factory.begin() as session:
            await lock_key(session, "relations:" + batch.generation_id)
            generation = await session.get(IndexGeneration, batch.generation_id)
            if generation is None or generation.state != "READY":
                raise ConflictError("relation generation is not READY")
            projection = await session.get(
                ProjectionRecord, generation.version_id, with_for_update=True
            )
            if (
                projection.metadata_revision != batch.metadata_revision
                or generation.metadata_revision != batch.metadata_revision
            ):
                raise ConflictError("relation metadata revision is stale")
            snapshot = Projection.model_validate(projection.payload)
            if snapshot.status != "active":
                raise ConflictError("relation projection is archived")
            existing_chunks = set(
                (
                    await session.scalars(
                        select(Chunk.chunk_id).where(
                            Chunk.generation_id == generation.id,
                            Chunk.version_id == projection.version_id,
                            Chunk.store_id == projection.store_id,
                        )
                    )
                ).all()
            )
            identifiers = []
            for edge in batch.edges:
                if not set(edge.evidence_chunk_ids) <= existing_chunks:
                    raise ConflictError("relation evidence must belong to the specified generation")
                start = edge.valid_from or snapshot.valid_from
                end = edge.valid_until or snapshot.valid_until
                if (
                    (snapshot.valid_from and (start is None or start < snapshot.valid_from))
                    or (snapshot.valid_until and (end is None or end > snapshot.valid_until))
                    or (start and end and end <= start)
                ):
                    raise ConflictError("relation validity exceeds its source projection")
                data = edge.model_dump(mode="json")
                data["evidence_chunk_ids"] = sorted(set(data["evidence_chunk_ids"]))
                identifier = payload_hash(
                    {
                        "generation_id": generation.id,
                        "metadata_revision": batch.metadata_revision,
                        "edge": data,
                    }
                )
                identifiers.append(identifier)
                if await session.get(Relation, identifier):
                    continue
                session.add(
                    Relation(
                        id=identifier,
                        generation_id=generation.id,
                        version_id=projection.version_id,
                        store_id=projection.store_id,
                        metadata_revision=batch.metadata_revision,
                        subject=edge.subject,
                        predicate=edge.predicate,
                        object=edge.object,
                        confirmed=edge.confirmed,
                        conditions=edge.conditions,
                        evidence_chunk_ids=data["evidence_chunk_ids"],
                        valid_from=start,
                        valid_until=end,
                    )
                )
            return {"generation_id": generation.id, "relation_ids": identifiers}
