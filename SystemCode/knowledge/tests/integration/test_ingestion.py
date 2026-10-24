import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from shopsteward_knowledge.config import Settings
from shopsteward_knowledge.contracts import IngestionRequest, Projection
from shopsteward_knowledge.ingestion import ConflictError, IngestionService
from shopsteward_knowledge.models import Chunk, IndexGeneration, Job, ProjectionRecord
from shopsteward_knowledge.worker import claim_job, complete_job, ingest_once

pytestmark = pytest.mark.integration


class Blobs:
    def __init__(self):
        self.data = {}

    async def put(self, key, data, sha256):
        if key in self.data and self.data[key] != data:
            raise ValueError("immutable blob")
        self.data[key] = data

    async def get(self, key):
        return self.data[key]


def request(revision=1, title="Terms", content=b"return policy"):
    return IngestionRequest.model_validate(
        {
            "original": {
                "version_id": "v1",
                "sha256": hashlib.sha256(content).hexdigest(),
                "mime": "text/plain",
                "storage_key": "originals/v1",
                "size_bytes": len(content),
            },
            "projection": {
                "document_id": "doc1",
                "version_id": "v1",
                "store_id": "store1",
                "title": title,
                "metadata_revision": revision,
            },
        }
    )


class SearchIndex:
    def __init__(self, visible=True, fail=False):
        self.visible = visible
        self.fail = fail
        self.generations = {}

    async def upsert(self, generation_id, chunks):
        if self.fail:
            raise ConnectionError("offline")
        self.generations[generation_id] = chunks

    async def verify_generation(self, generation_id, chunks):
        return self.visible and self.generations.get(generation_id) == chunks


def parse(ref, content):
    return SimpleNamespace(
        blocks=[{"text": content.decode()}], status="COMPLETE", warnings=[], coverage={"blocks": 1}
    )


def chunk(blocks, profile):
    return [
        {
            "chunk_id": "chunk1",
            "text": blocks[0]["text"],
            "parent_id": "parent1",
            "ordinal": 0,
            "locator": {"kind": "paragraph", "paragraph_range": [1, 1]},
        }
    ]


async def test_ingestion_replay_conflict_and_revision_order(pg_sessions):
    service = IngestionService(pg_sessions, Blobs())
    receipts = await asyncio.gather(
        *[service.accept(request(), b"return policy", "key1") for _ in range(2)]
    )
    assert receipts[0].job_id == receipts[1].job_id
    with pytest.raises(ConflictError):
        await service.accept(request(title="different"), b"return policy", "key1")
    assert await service.project(request(3, "Archived").projection) == "apply"
    assert await service.project(request(2).projection) == "stale"
    with pytest.raises(ConflictError):
        await service.project(request(3, "changed").projection)
    await service.accept(request(), b"return policy", "key2")
    async with pg_sessions() as session:
        projection = await session.get(ProjectionRecord, "v1")
        assert projection.metadata_revision == 3
        assert projection.payload["title"] == "Archived"


async def test_version_bytes_are_immutable_and_mismatch_never_accepted(pg_sessions):
    service = IngestionService(pg_sessions, Blobs())
    with pytest.raises(ValueError):
        await service.accept(request(), b"forged bytes!", "bad")
    await service.accept(request(), b"return policy", "key1")
    with pytest.raises(ConflictError):
        await service.accept(request(content=b"replacement"), b"replacement", "key2")


async def test_worker_durable_manifest_and_index_candidate(pg_sessions):
    blobs = Blobs()
    service = IngestionService(pg_sessions, blobs)
    receipt = await service.accept(request(), b"return policy", "key1")
    index = SearchIndex()
    assert await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=index,
        parser=parse,
        chunker=chunk,
    )
    done = await IngestionService(pg_sessions, blobs).receipt(receipt.job_id)
    assert done.state == "SUCCEEDED" and len(done.manifest_hash) == 64
    async with pg_sessions() as session:
        generation = await session.get(IndexGeneration, done.generation_id)
        chunks = (await session.scalars(select(Chunk))).all()
        assert generation.state == "READY" and generation.chunk_count == len(chunks) == 1
        assert generation.manifest_hash == done.manifest_hash
        assert chunks[0].payload["title"] == "Terms"
        assert chunks[0].payload["original_sha256"] == request().original.sha256
        assert chunks[0].payload["locator"]["paragraph_range"] == [1, 1]
    assert not await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=index,
        parser=parse,
        chunker=chunk,
    )


@pytest.mark.parametrize("index", [SearchIndex(visible=False), SearchIndex(fail=True)])
async def test_invisible_or_failed_index_never_succeeds(pg_sessions, index):
    blobs = Blobs()
    service = IngestionService(pg_sessions, blobs)
    receipt = await service.accept(request(), b"return policy", "key1")
    await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=index,
        parser=parse,
        chunker=chunk,
    )
    done = await service.receipt(receipt.job_id)
    assert done.state == "RETRY_WAIT" and done.manifest_hash is None
    async with pg_sessions() as session:
        assert (await session.get(IndexGeneration, done.generation_id)).state != "READY"


async def test_expired_worker_is_fenced_from_ready_and_retry_generation(pg_sessions):
    blobs = Blobs()
    await IngestionService(pg_sessions, blobs).accept(request(), b"return policy", "key1")
    first = await claim_job(pg_sessions, lease_seconds=30)
    async with pg_sessions.begin() as session:
        await session.execute(
            update(Job)
            .where(Job.id == first.id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    second = await claim_job(pg_sessions, lease_seconds=30)
    assert second.lease_token != first.lease_token
    assert second.generation_id != first.generation_id
    assert not await complete_job(pg_sessions, first, [], "a" * 64, {})
    async with pg_sessions() as session:
        assert (await session.get(Job, first.id)).state == "RUNNING"
        assert (await session.get(IndexGeneration, first.generation_id)).state == "FAILED"


async def test_evidence_scope_and_explicit_relation_intake(pg_sessions):
    from shopsteward_knowledge.api import RelationBatch
    from shopsteward_knowledge.contracts import SearchScope
    from shopsteward_knowledge.db import make_evidence_loader, make_scope_filter
    from shopsteward_knowledge.models import Relation

    blobs = Blobs()
    service = IngestionService(pg_sessions, blobs)
    receipt = await service.accept(request(), b"return policy", "key1")
    await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=SearchIndex(),
        parser=parse,
        chunker=chunk,
    )
    scope = SearchScope(
        principal_ref="user1",
        store_id="store1",
        as_of=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        allowed_versions=[
            {"version_id": "v1", "generation_id": receipt.generation_id, "metadata_revision": 1}
        ],
    )
    loader = make_evidence_loader(pg_sessions)
    assert [c.chunk_id for c in await loader(scope, ["chunk1", "missing"])] == ["chunk1"]
    batch = RelationBatch(
        generation_id=receipt.generation_id,
        metadata_revision=1,
        edges=[
            {
                "subject": "policy",
                "predicate": "APPLIES_TO",
                "object": "product1",
                "confirmed": True,
                "evidence_chunk_ids": ["chunk1"],
            }
        ],
    )
    first = await service.add_relations(batch)
    assert await service.add_relations(batch) == first
    async with pg_sessions() as session:
        edges = (await session.scalars(select(Relation))).all()
        assert len(edges) == 1 and edges[0].object == "product1"
    bad = batch.model_copy(
        update={"edges": [batch.edges[0].model_copy(update={"evidence_chunk_ids": ["missing"]})]}
    )
    with pytest.raises(ConflictError):
        await service.add_relations(bad)
    await service.project(
        Projection(**{**request(2).projection.model_dump(), "status": "archived"})
    )
    assert not (await make_scope_filter(pg_sessions)(scope)).allowed_versions
    assert await loader(scope, ["chunk1"]) == []


async def test_metadata_change_requires_new_generation_and_preserves_old_manifest(pg_sessions):
    from shopsteward_knowledge.contracts import SearchScope
    from shopsteward_knowledge.db import make_scope_filter

    blobs = Blobs()
    service = IngestionService(pg_sessions, blobs)
    receipt = await service.accept(request(), b"return policy", "key1")
    index = SearchIndex()
    await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=index,
        parser=parse,
        chunker=chunk,
    )
    before = await service.receipt(receipt.job_id)
    await service.project(request(2, "Updated title").projection)
    old_scope = SearchScope(
        principal_ref="user1",
        store_id="store1",
        as_of=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        allowed_versions=[
            {"version_id": "v1", "generation_id": before.generation_id, "metadata_revision": 1}
        ],
    )
    filter_scope = make_scope_filter(pg_sessions)
    assert not (await filter_scope(old_scope)).allowed_versions
    # Merely relabelling an old generation with the new revision cannot authorize it.
    relabelled = old_scope.model_copy(
        update={
            "allowed_versions": [
                old_scope.allowed_versions[0].model_copy(update={"metadata_revision": 2})
            ]
        }
    )
    assert not (await filter_scope(relabelled)).allowed_versions
    assert not await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=index,
        parser=parse,
        chunker=chunk,
    )
    next_receipt = await service.accept(request(2, "Updated title"), b"return policy", "key2")
    assert next_receipt.generation_id != receipt.generation_id
    await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=index,
        parser=parse,
        chunker=chunk,
    )
    assert (await service.receipt(next_receipt.job_id)).state == "SUCCEEDED"
    after = await service.receipt(receipt.job_id)
    assert after.manifest_hash == before.manifest_hash and after.state == "SUCCEEDED"
    async with pg_sessions() as session:
        old = await session.get(IndexGeneration, receipt.generation_id)
        assert old.state == "READY" and old.metadata_revision == 1


async def test_multipart_api_receipt_survives_app_recreation(pg_sessions):
    import httpx

    from shopsteward_knowledge.api import create_app

    blobs = Blobs()
    settings = Settings(database_url=None, service_key="test-secret")
    headers = {"Authorization": "Bearer test-secret", "Idempotency-Key": "delivery1"}
    app = create_app(settings, session_factory=pg_sessions, blob=blobs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        accepted = await client.post(
            "/internal/v1/ingestions",
            headers=headers,
            data={"metadata": request().model_dump_json()},
            files={"file": ("original.txt", b"return policy", "text/plain")},
        )
        assert accepted.status_code == 202
        receipt = accepted.json()
        bad = await client.post(
            "/internal/v1/ingestions",
            headers=headers,
            data={"metadata": request(title="changed").model_dump_json()},
            files={"file": ("original.txt", b"return policy", "text/plain")},
        )
        assert bad.status_code == 409
    replacement = create_app(settings, session_factory=pg_sessions, blob=blobs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=replacement), base_url="http://test"
    ) as client:
        response = await client.get("/internal/v1/ingestions/" + receipt["job_id"], headers=headers)
        assert response.status_code == 200 and response.json() == receipt


async def test_failed_attempt_retries_new_generation_and_old_worker_cannot_fail_it(pg_sessions):
    from shopsteward_knowledge.worker import fail_job

    blobs = Blobs()
    service = IngestionService(pg_sessions, blobs)
    initial = await service.accept(request(), b"return policy", "key1")
    first = await claim_job(pg_sessions)
    assert await fail_job(pg_sessions, first, ConnectionError("offline"))
    async with pg_sessions.begin() as session:
        await session.execute(
            update(Job)
            .where(Job.id == first.id)
            .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    index = SearchIndex()
    await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=index,
        parser=parse,
        chunker=chunk,
    )
    done = await service.receipt(initial.job_id)
    assert done.state == "SUCCEEDED" and done.attempt == 2
    assert done.generation_id != initial.generation_id
    assert not await fail_job(pg_sessions, first, ValueError("late failure"))
    assert (await service.receipt(initial.job_id)).state == "SUCCEEDED"


async def test_retry_asgi_replay_fencing_and_total_budget_are_durable(pg_sessions):
    import httpx

    from shopsteward_knowledge.api import create_app
    from shopsteward_knowledge.worker import fail_job

    blobs = Blobs()
    service = IngestionService(pg_sessions, blobs, max_attempts=1, max_total_attempts=2)
    receipt = await service.accept(request(), b"return policy", "original-key")
    first = await claim_job(pg_sessions)
    assert await fail_job(pg_sessions, first, ConnectionError("temporary"))
    assert (await service.receipt(receipt.job_id)).state == "FAILED"
    settings = Settings(
        database_url=None, service_key="retry-secret", max_attempts=1, max_total_attempts=2
    )
    app = create_app(settings, session_factory=pg_sessions, blob=blobs)
    path = f"/internal/v1/ingestions/{receipt.job_id}/retry"
    headers = {"Authorization": "Bearer retry-secret", "Idempotency-Key": "retry-key"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        replies = await asyncio.gather(*[client.post(path, headers=headers) for _ in range(2)])
        assert [r.status_code for r in replies] == [202, 202]
        assert replies[0].json() == replies[1].json()
        saved = replies[0].json()
        assert saved["attempt"] == 1 and saved["state"] == "PENDING"
        assert not await fail_job(pg_sessions, first, ValueError("stale worker"))
        second = await claim_job(pg_sessions)
        assert second.attempt == 2 and second.generation_id != first.generation_id
        assert (
            await client.post(path, headers={**headers, "Idempotency-Key": "another"})
        ).status_code == 409
        assert (await client.post(path, headers=headers)).json() == saved
        await fail_job(pg_sessions, second, ConnectionError("still down"))
        assert (
            await client.post(path, headers={**headers, "Idempotency-Key": "third"})
        ).status_code == 409
    # An ACK gap/restart does not grant a second attempt window for the same command.
    replay = await IngestionService(pg_sessions, blobs).retry(receipt.job_id, "retry-key")
    assert replay.model_dump(mode="json") == saved
    async with pg_sessions() as session:
        job = await session.get(Job, receipt.job_id)
        assert job.attempt == job.attempt_limit == job.total_attempt_limit == 2
        assert job.idempotency_key == "original-key" and job.state == "FAILED"


async def test_retry_rejects_superseded_projection_and_ready_generation(pg_sessions):
    from shopsteward_knowledge.worker import fail_job

    blobs = Blobs()
    service = IngestionService(pg_sessions, blobs)
    receipt = await service.accept(request(), b"return policy", "original-key")
    claim = await claim_job(pg_sessions)
    with pytest.raises(ConflictError):
        await service.retry(receipt.job_id, "active")
    await fail_job(pg_sessions, claim, ValueError("permanent"))
    await service.project(request(2, "updated").projection)
    with pytest.raises(ConflictError, match="projection"):
        await service.retry(receipt.job_id, "stale")
    new = await service.accept(request(2, "updated"), b"return policy", "new-key")
    await ingest_once(
        Settings(),
        session_factory=pg_sessions,
        blob=blobs,
        index=SearchIndex(),
        parser=parse,
        chunker=chunk,
    )
    before = await service.receipt(new.job_id)
    assert before.state == "SUCCEEDED"
    with pytest.raises(ConflictError):
        await service.retry(new.job_id, "cannot-mutate-ready")
    assert (await service.receipt(new.job_id)) == before


async def test_database_original_identity_cannot_be_mutated(pg_sessions):
    from sqlalchemy.exc import DBAPIError

    from shopsteward_knowledge.models import Original

    await IngestionService(pg_sessions, Blobs()).accept(request(), b"return policy", "key1")
    with pytest.raises(DBAPIError, match="immutable"):
        async with pg_sessions.begin() as session:
            await session.execute(
                update(Original).where(Original.version_id == "v1").values(sha256="f" * 64)
            )
