"""Delivery protocol tests plus dedicated-PostgreSQL lifecycle tests."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from test_knowledge_documents import environment, upload
from test_missions import headers


async def publication_boundary(
    monkeypatch, *, old_from=None, old_until=None, new_from=None, new_until=None, **overrides
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.core.config import TokenGrant
    from app.knowledge import indexing
    from app.knowledge.index_models import Publication

    doc = SimpleNamespace(
        id="D1", status="active", metadata_version=3, evidence_revision=2, publication_revision=1
    )
    version = SimpleNamespace(id="V2", document_id="D1", valid_from=new_from, valid_until=new_until)
    request = SimpleNamespace(
        version_id="V2",
        state="SUCCEEDED",
        metadata_revision=2,
        generation_id="G2",
        manifest_hash="a" * 64,
        job_id="J2",
    )
    proof = SimpleNamespace(
        job_id="J2", state="SUCCEEDED", generation_id="G2", manifest_hash="a" * 64
    )
    old = Publication(
        id="old",
        document_id="D1",
        version_id="V1",
        generation_id="G1",
        manifest_hash="b" * 64,
        metadata_revision=2,
        publication_revision=1,
        valid_from=old_from,
        valid_until=old_until,
        active=True,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    rows = [old]

    async def get(model, identifier):
        return version if identifier == "V2" else request

    session = SimpleNamespace(get=get, scalars=AsyncMock(return_value=[old]), add=rows.append)
    monkeypatch.setattr(
        indexing.repo, "receipt", AsyncMock(return_value=(SimpleNamespace(), False))
    )
    monkeypatch.setattr(indexing.repo, "visible", AsyncMock(return_value=doc))
    principal = TokenGrant(token="x" * 24, principal_id="operator", roles=["operator"])
    result = await indexing.activate_generation(
        session,
        principal,
        "V2",
        "G2",
        "a" * 64,
        1,
        proof=proof,
        request_id="R2",
        key="publish",
        replace_version_ids=["V1"],
        **overrides,
    )
    return rows, result, doc


@pytest.mark.parametrize("until", [None, datetime(2026, 11, 1, tzinfo=UTC)])
async def test_future_publication_preserves_old_evidence_before_start(monkeypatch, until):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    rows, result, doc = await publication_boundary(monkeypatch, new_from=start, new_until=until)

    def selected(at):
        return [
            p.version_id
            for p in rows
            if p.active
            and (p.valid_from is None or p.valid_from <= at)
            and (p.valid_until is None or at < p.valid_until)
        ]

    assert selected(datetime(2026, 9, 8, tzinfo=UTC)) == ["V1"]
    assert selected(start) == ["V2"]
    if until:
        assert selected(until) == ["V1"]
    assert len({p.publication_revision for p in rows}) == len(rows)
    assert result["publication_revision"] == doc.publication_revision


async def test_explicit_bounded_publication_preserves_both_old_residual_intervals(monkeypatch):
    start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
    rows, result, _ = await publication_boundary(monkeypatch, valid_from=start, valid_until=end)
    assert {(p.version_id, p.valid_from, p.valid_until) for p in rows if p.active} == {
        ("V1", None, start),
        ("V2", start, end),
        ("V1", end, None),
    }
    assert result["valid_from"] == start.isoformat() and result["valid_until"] == end.isoformat()


@pytest.mark.parametrize(
    "overrides",
    [
        {"valid_from": datetime(2026, 9, 1, tzinfo=UTC)},
        {"valid_until": datetime(2026, 12, 1, tzinfo=UTC)},
        {
            "valid_from": datetime(2026, 10, 20, tzinfo=UTC),
            "valid_until": datetime(2026, 10, 10, tzinfo=UTC),
        },
    ],
)
async def test_publication_interval_cannot_expand_original_or_invert(monkeypatch, overrides):
    from app.core.errors import AppError

    with pytest.raises(AppError) as error:
        await publication_boundary(
            monkeypatch,
            new_from=datetime(2026, 10, 1, tzinfo=UTC),
            new_until=datetime(2026, 11, 1, tzinfo=UTC),
            **overrides,
        )
    assert error.value.code == "INVALID_PUBLICATION_INTERVAL"


@pytest.mark.parametrize("legacy_key", [False, True])
async def test_completed_publication_route_replays_before_cloud_io(monkeypatch, legacy_key):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from app.core.config import TokenGrant
    from app.core.errors import AppError
    from app.core.hashing import digest
    from app.knowledge import router as routes
    from app.knowledge.schemas import Activation
    from app.operations.models import Command

    body = Activation(
        version_id="V1", generation_id="G1", manifest_hash="a" * 64, expected_publication_revision=0
    )
    saved_result = {
        "document_id": "D1",
        "version_id": "V1",
        "generation_id": "G1",
        "manifest_hash": "a" * 64,
        "publication_revision": 1,
    }
    saved = Command(
        id=digest(["knowledge", ["publish", "V1" if legacy_key else "D1"], "operator", "key"]),
        content_hash=digest(["V1", "G1", "a" * 64, 0, []]),
        response={"id": "D1", "result": saved_result},
    )
    authorized = True

    async def visible(session, principal, document_id, **kwargs):
        if not authorized:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Not visible")
        return SimpleNamespace(id="D1")

    class DatabaseBoundary:
        @asynccontextmanager
        async def session(self):
            yield self

        async def get(self, model, identifier):
            return saved if model is Command and identifier == saved.id else None

    async def ready(*args):
        return SimpleNamespace(job_id="J1")

    @asynccontextmanager
    async def offline(settings):
        raise httpx.ConnectError("Cloud down")
        yield  # pragma: no cover

    monkeypatch.setattr(routes.indexing.repo, "visible", visible)
    monkeypatch.setattr(routes.indexing, "ready_request", ready)
    monkeypatch.setattr(routes, "connect", offline)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db=DatabaseBoundary(), settings=None))
    )
    principal = TokenGrant(token="x" * 24, principal_id="operator", roles=["operator"])
    assert await routes.publish(request, principal, "D1", body, "key") == saved_result
    with pytest.raises(AppError) as conflict:
        await routes.publish(
            request, principal, "D1", body.model_copy(update={"generation_id": "G2"}), "key"
        )
    assert conflict.value.code == "IDEMPOTENCY_KEY_REUSED"
    if not legacy_key:
        with pytest.raises(AppError) as conflict:
            await routes.publish(
                request, principal, "D1", body.model_copy(update={"version_id": "V2"}), "key"
            )
        assert conflict.value.code == "IDEMPOTENCY_KEY_REUSED"
    authorized = False
    with pytest.raises(AppError) as denied:
        await routes.publish(request, principal, "D1", body, "key")
    assert denied.value.status == 404


@pytest.mark.parametrize(
    "bounds",
    [
        (None, datetime(2026, 10, 1, tzinfo=UTC)),
        (datetime(2026, 11, 1, tzinfo=UTC), None),
    ],
)
async def test_adjacent_publications_reject_spurious_replacement_without_changes(
    monkeypatch, bounds
):
    from app.core.errors import AppError

    with pytest.raises(AppError) as error:
        await publication_boundary(
            monkeypatch,
            old_from=bounds[0],
            old_until=bounds[1],
            new_from=datetime(2026, 10, 1, tzinfo=UTC),
            new_until=datetime(2026, 11, 1, tzinfo=UTC),
        )
    assert error.value.code == "PUBLICATION_INTERVAL_CONFLICT"


@pytest_asyncio.fixture
async def delivery_db(db):
    from sqlalchemy import text

    async with db.session() as session, session.begin():
        await session.execute(text("TRUNCATE knowledge_delivery_outbox, knowledge_publications"))
    return db


def test_provenance_is_an_accepted_optional_upload_contract():
    from app.knowledge.schemas import AppendMetadata, UploadMetadata

    data = {"source_kind": "regulation", "synthetic": True, "publisher": "Fixture"}
    assert UploadMetadata(title="Policy", provenance=data).provenance.synthetic is True
    assert AppendMetadata(expected_metadata_version=1, provenance=data).provenance == (
        UploadMetadata(title="Policy", provenance=data).provenance
    )


def test_index_and_publication_runtime_responses_have_typed_contracts():
    from openapi_spec_validator import validate

    from app.core.config import Settings
    from app.main import create_app

    schema = create_app(Settings(_env_file=None)).openapi()
    validate(schema)
    path = "/api/v1/documents/{document_id}/versions/{version_id}/index-jobs"
    operation = schema["paths"][path]["post"]
    assert operation["x-phase"] == "K2"
    response = operation["responses"]["202"]["content"]["application/json"]["schema"]
    assert "$ref" in response
    fields = schema["components"]["schemas"][response["$ref"].split("/")[-1]]["properties"]
    assert {
        "request_id",
        "state",
        "generation_id",
        "manifest_hash",
        "metadata_revision",
    } <= fields.keys()
    response = schema["paths"]["/api/v1/documents/{document_id}/publications"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert "$ref" in response


async def test_http_client_sends_exact_multipart_and_receipt_contract():
    from shopsteward_knowledge.contracts import IngestionRequest

    from app.knowledge.service_client import KnowledgeClient

    received = []

    async def server(request):
        received.append(request)
        return httpx.Response(
            202,
            json={
                "job_id": "J1",
                "state": "PENDING",
                "generation_id": "G1",
                "manifest_hash": None,
                "attempt": 0,
                "error": None,
            },
        )

    payload = IngestionRequest.model_validate(
        {
            "original": {
                "version_id": "V1",
                "sha256": hashlib.sha256(b"policy").hexdigest(),
                "mime": "text/plain",
                "storage_key": "a.raw",
                "size_bytes": 6,
            },
            "projection": {
                "document_id": "D1",
                "version_id": "V1",
                "store_id": "S1",
                "metadata_revision": 1,
                "title": "Policy",
            },
            "profile_id": "lexical-v1",
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(server), base_url="http://knowledge"
    ) as http:
        result = await KnowledgeClient(http).ingest(payload, b"policy", "K1")
    assert result.job_id == "J1"
    request = received[0]
    assert request.url.path == "/internal/v1/ingestions"
    assert request.headers["Idempotency-Key"] == "K1"
    assert b'name="file"' in request.content and b'name="metadata"' in request.content
    assert b'"profile_id":"lexical-v1"' in request.content


async def test_remote_retry_uses_durable_attempt_key_and_existing_receipt_contract():
    from app.knowledge.service_client import KnowledgeClient

    seen = []

    async def remote(request):
        seen.append(request)
        return httpx.Response(
            202,
            json={
                "job_id": "J1",
                "state": "PENDING",
                "generation_id": "G1",
                "manifest_hash": None,
                "attempt": 5,
                "error": None,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(remote), base_url="http://knowledge"
    ) as http:
        receipt = await KnowledgeClient(http).retry("J1", "retry-attempt-1")
    assert receipt.generation_id == "G1" and receipt.state == "PENDING"
    assert seen[0].url.path == "/internal/v1/ingestions/J1/retry"
    assert seen[0].headers["Idempotency-Key"] == "retry-attempt-1"
    assert seen[0].content == b""


@pytest.mark.parametrize(
    "status,attempt,retry_after,expected",
    [
        (503, 1, None, 1),
        (503, 4, None, 8),
        (429, 2, "120", 60),
        (429, 1, "bad", 1),
        (400, 1, None, None),
        (503, 5, None, None),
    ],
)
def test_retry_policy_is_bounded(status, attempt, retry_after, expected):
    from app.knowledge.publisher import retry_delay

    assert retry_delay(status, attempt, retry_after) == expected


@pytest.mark.integration
async def test_index_idempotency_provenance_and_projection_outbox(db, tmp_path):
    from sqlalchemy import select, text
    from sqlalchemy.exc import IntegrityError

    from app.knowledge.index_models import DeliveryOutbox

    async with environment(db, tmp_path) as (seed, client, app):
        result = await upload(
            client,
            seed["store_id"],
            metadata={
                "title": "Policy",
                "provenance": {"source_kind": "regulation", "synthetic": True},
            },
        )
        assert result.status_code == 201, result.text
        doc = result.json()
        base = f"/api/v1/documents/{doc['id']}"
        version = doc["latest_version_id"]
        info = await client.get(base + f"/versions/{version}", headers=headers())
        assert info.json()["provenance"]["synthetic"] is True
        key = str(uuid4())
        url = base + f"/versions/{version}/index-jobs"
        body = {"profile_id": "lexical-v1"}
        first = await client.post(url, headers=headers(key=key), json=body)
        assert first.status_code == 202, first.text
        replay = await client.post(url, headers=headers(key=key), json=body)
        assert replay.json() == first.json()
        assert (
            await client.post(url, headers=headers(key=key), json={"profile_id": "other"})
        ).status_code == 409
        changed = await client.patch(
            base, headers=headers(), json={"expected_metadata_version": 1, "visibility": "private"}
        )
        assert changed.status_code == 200
        async with db.session() as session:
            rows = list(
                await session.scalars(
                    select(DeliveryOutbox).where(DeliveryOutbox.document_id == doc["id"])
                )
            )
            assert len([r for r in rows if r.operation == "ingest"]) == 1
            assert any(r.operation == "projection" and r.metadata_revision == 2 for r in rows)
        async with db.session() as session, session.begin():
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        text(
                            "UPDATE knowledge_version_provenance SET synthetic=false "
                            "WHERE version_id=:id"
                        ),
                        {"id": version},
                    )


async def requested(client, seed, *, metadata=None):
    response = await upload(client, seed["store_id"], metadata=metadata or {"title": "Policy"})
    assert response.status_code == 201, response.text
    doc = response.json()
    path = f"/api/v1/documents/{doc['id']}"
    response = await client.post(
        path + f"/versions/{doc['latest_version_id']}/index-jobs",
        headers=headers(),
        json={"profile_id": "lexical-v1"},
    )
    assert response.status_code == 202, response.text
    return doc, response.json(), path


async def mark_ready(db, request_id):
    from shopsteward_knowledge.contracts import IngestionReceipt

    from app.knowledge.index_models import DeliveryOutbox

    proof = IngestionReceipt(
        job_id="j-" + request_id,
        generation_id="g-" + request_id,
        state="SUCCEEDED",
        manifest_hash="a" * 64,
        attempt=1,
    )
    async with db.session() as session, session.begin():
        row = await session.get(DeliveryOutbox, request_id)
        row.state, row.job_id = "SUCCEEDED", proof.job_id
        row.generation_id, row.manifest_hash = proof.generation_id, proof.manifest_hash
    return proof


async def activate(db, config, doc, job, proof, *, expected=0, replace=(), key=None, **interval):
    from app.knowledge.indexing import activate_generation

    principal = next(g for g in config.auth_tokens if "operator" in g.roles)
    async with db.session() as session, session.begin():
        return await activate_generation(
            session,
            principal,
            doc["latest_version_id"],
            proof.generation_id,
            proof.manifest_hash,
            expected,
            proof=proof,
            request_id=job["request_id"],
            key=key or str(uuid4()),
            replace_version_ids=replace,
            **interval,
        )


@pytest.mark.integration
async def test_pg_future_publication_preserves_september_then_reverts_after_bounded_override(
    delivery_db, tmp_path
):
    from app.agent_bridge.document_evidence import current_authority

    db = delivery_db
    start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
    async with environment(db, tmp_path) as (seed, client, app):
        first = (await upload(client, seed["store_id"], metadata={"title": "Policy"})).json()
        base = f"/api/v1/documents/{first['id']}"
        job1 = (
            await client.post(
                base + f"/versions/{first['latest_version_id']}/index-jobs",
                headers=headers(),
                json={"profile_id": "lexical-v1"},
            )
        ).json()
        proof1 = await mark_ready(db, job1["request_id"])
        await activate(db, app.state.settings, first, job1, proof1)
        second = await upload(
            client,
            seed["store_id"],
            url=base + "/versions",
            content=b"October policy",
            metadata={"expected_metadata_version": 1, "valid_from": start.isoformat()},
        )
        assert second.status_code == 201, second.text
        newer = second.json()
        assert newer["metadata_version"] == 2 and newer["evidence_revision"] == 1
        job2 = (
            await client.post(
                base + f"/versions/{newer['latest_version_id']}/index-jobs",
                headers=headers(),
                json={"profile_id": "lexical-v1"},
            )
        ).json()
        proof2 = await mark_ready(db, job2["request_id"])
        result = await activate(
            db,
            app.state.settings,
            newer,
            job2,
            proof2,
            expected=1,
            replace=[first["latest_version_id"]],
            valid_from=start,
            valid_until=end,
        )
        principal = next(g for g in app.state.settings.auth_tokens if "operator" in g.roles)
        for at, expected in [
            (datetime(2026, 9, 8, tzinfo=UTC), first["latest_version_id"]),
            (start, newer["latest_version_id"]),
            (end, first["latest_version_id"]),
        ]:
            async with db.session() as session:
                authority = await current_authority(session, principal, seed["store_id"], at)
            assert list(authority) == [expected]
        detail = (await client.get(base, headers=headers())).json()
        assert len(detail["publications"]) == 3
        assert detail["publication_revision"] == result["publication_revision"]


@pytest.mark.integration
async def test_pg_publication_replay_survives_cloud_outage_and_reauthorizes(
    delivery_db, tmp_path, monkeypatch
):
    from contextlib import asynccontextmanager

    from app.knowledge import router as routes

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, base = await requested(client, seed)
        proof = await mark_ready(db, job["request_id"])

        class Remote:
            async def job(self, job_id):
                return proof

        @asynccontextmanager
        async def connected(settings):
            yield Remote()

        monkeypatch.setattr(routes, "connect", connected)
        key = str(uuid4())
        body = {
            "version_id": doc["latest_version_id"],
            "generation_id": proof.generation_id,
            "manifest_hash": proof.manifest_hash,
            "expected_publication_revision": 0,
        }
        initial = await client.post(base + "/publications", headers=headers(key=key), json=body)
        assert initial.status_code == 200, initial.text

        @asynccontextmanager
        async def offline(settings):
            raise httpx.ConnectError("Offline")
            yield  # pragma: no cover

        monkeypatch.setattr(routes, "connect", offline)
        replay = await client.post(base + "/publications", headers=headers(key=key), json=body)
        assert replay.status_code == 200 and replay.json() == initial.json()
        changed = await client.post(
            base + "/publications",
            headers=headers(key=key),
            json={**body, "generation_id": "different"},
        )
        assert (
            changed.status_code == 409
            and changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        )
        await client.patch(
            base, headers=headers(), json={"expected_metadata_version": 1, "visibility": "private"}
        )
        # An admin can discover private metadata but cannot replay another owner's publication.
        denied = await client.post(base + "/publications", headers=headers("admin", key), json=body)
        assert denied.status_code == 404


@pytest.mark.integration
async def test_publisher_http_runs_after_claim_commit_and_stale_lease_cannot_ack(
    delivery_db, tmp_path
):
    from shopsteward_knowledge.contracts import IngestionReceipt
    from sqlalchemy import text

    from app.knowledge.index_models import DeliveryOutbox
    from app.knowledge.publisher import acknowledge, claim, deliver_once

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        config = app.state.settings.model_copy(update={"knowledge_service_enabled": True})
        old = await claim(db, config, "old")
        async with db.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE knowledge_delivery_outbox SET lease_until=now()-interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": old.id},
            )
        new = await claim(db, config, "new")
        proof = IngestionReceipt(
            job_id="j", generation_id="g", state="SUCCEEDED", manifest_hash="a" * 64
        )
        assert await acknowledge(db, old, receipt=proof) is False
        assert await acknowledge(db, new, status=503, error="NETWORK") is True
        async with db.session() as session, session.begin():
            row = await session.get(DeliveryOutbox, old.id)
            assert row.state == "RETRY_WAIT" and row.retry_count == 1
            row.next_attempt_at = datetime.now(UTC)

        class Remote:
            async def ingest(self, request, content, key):
                # A separate connection can acquire this row now: claim is committed.
                async with db.session() as session, session.begin():
                    await session.execute(text("SET LOCAL lock_timeout='500ms'"))
                    row = await session.get(DeliveryOutbox, job["request_id"], with_for_update=True)
                    assert row.state == "RUNNING"
                assert (
                    content == b"original"
                    and request.original.version_id == doc["latest_version_id"]
                )
                return proof

        assert await deliver_once(config, db=db, client=Remote()) is True
        response = await client.get(path + "/index-jobs/" + job["request_id"], headers=headers())
        assert response.json()["state"] == "SUCCEEDED"
        assert (await client.get(path, headers=headers())).json()["publication_revision"] == 0


@pytest.mark.integration
async def test_interrupted_http_replays_same_remote_identity(delivery_db, tmp_path):
    import asyncio

    from shopsteward_knowledge.contracts import IngestionReceipt
    from sqlalchemy import text

    from app.knowledge.index_models import DeliveryOutbox
    from app.knowledge.publisher import deliver_once

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        config = app.state.settings.model_copy(update={"knowledge_service_enabled": True})
        remote_jobs = {}

        class Remote:
            crash = True

            async def ingest(self, request, content, key):
                remote_jobs.setdefault(
                    key,
                    IngestionReceipt(
                        job_id="persisted",
                        state="SUCCEEDED",
                        generation_id="one-generation",
                        manifest_hash="b" * 64,
                    ),
                )
                if self.crash:
                    self.crash = False
                    raise asyncio.CancelledError()
                return remote_jobs[key]

        remote = Remote()
        with pytest.raises(asyncio.CancelledError):
            await deliver_once(config, db=db, client=remote)
        async with db.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE knowledge_delivery_outbox SET lease_until=now()-interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": job["request_id"]},
            )
        await deliver_once(config, db=db, client=remote)
        assert len(remote_jobs) == 1
        async with db.session() as session:
            row = await session.get(DeliveryOutbox, job["request_id"])
            assert row.state == "SUCCEEDED" and row.generation_id == "one-generation"


@pytest.mark.integration
@pytest.mark.parametrize("change", ["archive", "private", "title"])
async def test_ready_proof_cannot_publish_after_metadata_changes(delivery_db, tmp_path, change):
    from app.core.errors import AppError

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        proof = await mark_ready(db, job["request_id"])
        if change == "archive":
            response = await client.post(
                path + "/control",
                headers=headers(),
                json={"operation": "archive", "expected_metadata_version": 1},
            )
        else:
            response = await client.patch(
                path,
                headers=headers(),
                json={
                    "expected_metadata_version": 1,
                    **({"visibility": "private"} if change == "private" else {"title": "Changed"}),
                },
            )
        assert response.status_code == 200, response.text
        with pytest.raises(AppError) as error:
            await activate(db, app.state.settings, doc, job, proof)
        assert error.value.code == "PUBLICATION_CONFLICT"


@pytest.mark.integration
async def test_publication_cas_overlap_and_latest_upload_not_authority(delivery_db, tmp_path):
    from app.agent_bridge.document_evidence import current_authority
    from app.core.errors import AppError

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        config = app.state.settings
        proof = await mark_ready(db, job["request_id"])
        key = str(uuid4())
        first = await activate(db, config, doc, job, proof, key=key)
        assert (await activate(db, config, doc, job, proof, key=key)) == first
        later = await upload(
            client,
            seed["store_id"],
            url=path + "/versions",
            content=b"replacement",
            metadata={"expected_metadata_version": 1},
        )
        assert later.status_code == 201, later.text
        newdoc = later.json()
        principal = next(g for g in config.auth_tokens if "operator" in g.roles)
        async with db.session() as session:
            scope = await current_authority(session, principal, seed["store_id"], datetime.now(UTC))
        # Append advances CAS only; the old publication remains authoritative.
        assert newdoc["metadata_version"] == 2 and newdoc["evidence_revision"] == 1
        assert doc["latest_version_id"] in scope and newdoc["latest_version_id"] not in scope
        detail = (await client.get(path, headers=headers())).json()
        assert detail["requires_republication"] is False
        assert detail["publications"][0]["metadata_revision"] == 1
        response = await client.post(
            path + f"/versions/{newdoc['latest_version_id']}/index-jobs",
            headers=headers(),
            json={"profile_id": "lexical-v1"},
        )
        newjob = response.json()
        newproof = await mark_ready(db, newjob["request_id"])
        with pytest.raises(AppError) as error:
            await activate(db, config, newdoc, newjob, newproof, expected=1)
        assert error.value.code == "PUBLICATION_INTERVAL_CONFLICT"
        with pytest.raises(AppError) as error:
            await activate(
                db, config, newdoc, newjob, newproof, expected=0, replace=[doc["latest_version_id"]]
            )
        assert error.value.code == "PUBLICATION_CONFLICT"
        await activate(
            db, config, newdoc, newjob, newproof, expected=1, replace=[doc["latest_version_id"]]
        )
        async with db.session() as session:
            scope = await current_authority(session, principal, seed["store_id"], datetime.now(UTC))
        assert doc["latest_version_id"] not in scope and newdoc["latest_version_id"] in scope


@pytest.mark.integration
async def test_failed_reindex_preserves_published_generation(delivery_db, tmp_path):
    from shopsteward_knowledge.contracts import IngestionReceipt

    from app.agent_bridge.document_evidence import current_authority
    from app.knowledge.publisher import acknowledge, claim

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        proof = await mark_ready(db, job["request_id"])
        await activate(db, app.state.settings, doc, job, proof)
        response = await client.post(
            path + f"/versions/{doc['latest_version_id']}/index-jobs",
            headers=headers(),
            json={"profile_id": "new-profile"},
        )
        assert response.status_code == 202
        row = await claim(db, app.state.settings, "worker")
        await acknowledge(
            db,
            row,
            receipt=IngestionReceipt(
                job_id="bad", generation_id="bad", state="FAILED", error="parser"
            ),
        )
        principal = next(g for g in app.state.settings.auth_tokens if "operator" in g.roles)
        async with db.session() as session:
            scope = await current_authority(session, principal, seed["store_id"], datetime.now(UTC))
        assert scope[doc["latest_version_id"]]["generation_id"] == proof.generation_id


@pytest.mark.integration
async def test_append_then_failed_new_version_index_preserves_published_v1(delivery_db, tmp_path):
    from shopsteward_knowledge.contracts import IngestionReceipt

    from app.agent_bridge.document_evidence import current_authority
    from app.knowledge.publisher import acknowledge, claim

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        proof = await mark_ready(db, job["request_id"])
        await activate(db, app.state.settings, doc, job, proof)
        response = await upload(
            client,
            seed["store_id"],
            url=path + "/versions",
            content=b"new version whose indexing fails",
            metadata={"expected_metadata_version": 1},
        )
        assert response.status_code == 201, response.text
        newer = response.json()
        assert newer["metadata_version"] == 2 and newer["evidence_revision"] == 1
        principal = next(g for g in app.state.settings.auth_tokens if "operator" in g.roles)

        async def old_is_current():
            async with db.session() as session:
                authority = await current_authority(
                    session, principal, seed["store_id"], datetime.now(UTC)
                )
            assert list(authority) == [doc["latest_version_id"]]
            assert authority[doc["latest_version_id"]]["generation_id"] == proof.generation_id
            detail = (await client.get(path, headers=headers())).json()
            assert detail["requires_republication"] is False

        await old_is_current()
        requested_new = await client.post(
            path + f"/versions/{newer['latest_version_id']}/index-jobs",
            headers=headers(),
            json={"profile_id": "lexical-v1"},
        )
        assert requested_new.status_code == 202, requested_new.text
        assert requested_new.json()["metadata_revision"] == 1
        claimed = await claim(db, app.state.settings, "review-failure")
        while claimed.operation == "projection":
            assert claimed.version_id == newer["latest_version_id"]
            await acknowledge(db, claimed)
            claimed = await claim(db, app.state.settings, "review-failure")
        await acknowledge(
            db,
            claimed,
            receipt=IngestionReceipt(
                job_id="failed-v2", generation_id="failed-v2", state="FAILED", error="parser"
            ),
        )
        await old_is_current()


@pytest.mark.integration
async def test_metadata_change_reindex_same_original_and_republish_restores_visibility(
    delivery_db, tmp_path
):
    from shopsteward_knowledge.contracts import IngestionReceipt

    from app.agent_bridge.document_evidence import current_authority
    from app.knowledge.publisher import acknowledge, claim

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        proof = await mark_ready(db, job["request_id"])
        await activate(db, app.state.settings, doc, job, proof)
        changed = await client.patch(
            path,
            headers=headers(),
            json={"expected_metadata_version": 1, "title": "New policy title"},
        )
        assert changed.status_code == 200
        assert changed.json()["indexing_status"] == "NOT_INDEXED"
        principal = next(g for g in app.state.settings.auth_tokens if "operator" in g.roles)
        async with db.session() as session:
            assert not await current_authority(
                session, principal, seed["store_id"], datetime.now(UTC)
            )
        # Delivering projection alone is not READY and cannot advance publication revision.
        projection = await claim(db, app.state.settings, "projector")
        assert projection.operation == "projection"
        await acknowledge(db, projection)
        detail = (await client.get(path, headers=headers())).json()
        assert detail["publication_revision"] == 1 and detail["requires_republication"]
        assert detail["indexing_status"] == "NOT_INDEXED"
        response = await client.post(
            path + f"/versions/{doc['latest_version_id']}/index-jobs",
            headers=headers(),
            json={"profile_id": "lexical-v1"},
        )
        newjob = response.json()
        assert newjob["metadata_revision"] == 2
        row = await claim(db, app.state.settings, "indexer")
        proof2 = IngestionReceipt(
            job_id="new-job",
            generation_id="new-generation",
            manifest_hash="c" * 64,
            state="SUCCEEDED",
        )
        await acknowledge(db, row, receipt=proof2)
        detail = (await client.get(path, headers=headers())).json()
        assert detail["indexing_status"] == "READY" and detail["requires_republication"]
        await activate(db, app.state.settings, doc, newjob, proof2, expected=1)
        async with db.session() as session:
            current = await current_authority(
                session, principal, seed["store_id"], datetime.now(UTC)
            )
        assert current[doc["latest_version_id"]]["metadata_revision"] == 2
        assert current[doc["latest_version_id"]]["generation_id"] == "new-generation"
        assert not (await client.get(path, headers=headers())).json()["requires_republication"]


@pytest.mark.integration
async def test_transient_retry_exhaustion_and_manual_retry_preserve_business_key(
    delivery_db, tmp_path
):
    from app.knowledge.index_models import DeliveryOutbox
    from app.knowledge.publisher import acknowledge, claim

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        identity = None
        for attempt in range(1, 6):
            async with db.session() as session, session.begin():
                row = await session.get(DeliveryOutbox, job["request_id"])
                row.next_attempt_at = datetime.now(UTC)
                identity = row.idempotency_key
            claimed = await claim(db, app.state.settings, "publisher")
            await acknowledge(db, claimed, status=503, error="NETWORK")
            async with db.session() as session:
                row = await session.get(DeliveryOutbox, job["request_id"])
                assert row.state == ("FAILED" if attempt == 5 else "RETRY_WAIT")
        assert await claim(db, app.state.settings, "publisher") is None
        key = str(uuid4())
        retry = await client.post(
            path + "/index-jobs/" + job["request_id"] + "/retry", headers=headers(key=key)
        )
        assert retry.status_code == 202, retry.text
        again = await client.post(
            path + "/index-jobs/" + job["request_id"] + "/retry", headers=headers(key=key)
        )
        assert again.json() == retry.json()
        claimed = await claim(db, app.state.settings, "publisher")
        assert claimed.attempt == 6 and claimed.idempotency_key == identity


@pytest.mark.integration
async def test_concurrent_index_replay_and_publication_cas_have_one_winner(delivery_db, tmp_path):
    import asyncio

    from sqlalchemy import func, select

    from app.core.errors import AppError
    from app.knowledge.index_models import DeliveryOutbox, Publication

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        key = str(uuid4())
        url = path + f"/versions/{doc['latest_version_id']}/index-jobs"
        responses = await asyncio.gather(
            *[
                client.post(url, headers=headers(key=key), json={"profile_id": "lexical-v1"})
                for _ in range(2)
            ]
        )
        assert all(r.status_code == 202 for r in responses)
        assert responses[0].json() == responses[1].json()
        proof = await mark_ready(db, job["request_id"])
        results = await asyncio.gather(
            *[activate(db, app.state.settings, doc, job, proof) for _ in range(2)],
            return_exceptions=True,
        )
        assert sum(isinstance(r, dict) for r in results) == 1
        errors = [r for r in results if isinstance(r, AppError)]
        assert len(errors) == 1 and errors[0].code == "PUBLICATION_CONFLICT"
        async with db.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(DeliveryOutbox)
                    .where(DeliveryOutbox.document_id == doc["id"])
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Publication)
                    .where(Publication.document_id == doc["id"], Publication.active.is_(True))
                )
                == 1
            )


@pytest.mark.integration
async def test_manual_remote_retry_survives_http_ack_gap_with_same_key(delivery_db, tmp_path):
    import asyncio

    from shopsteward_knowledge.contracts import IngestionReceipt
    from sqlalchemy import text

    from app.knowledge.index_models import DeliveryOutbox
    from app.knowledge.publisher import deliver_once

    db = delivery_db
    async with environment(db, tmp_path) as (seed, client, app):
        doc, job, path = await requested(client, seed)
        proof = await mark_ready(db, job["request_id"])
        async with db.session() as session, session.begin():
            row = await session.get(DeliveryOutbox, job["request_id"])
            row.state = "FAILED"
            identity = row.idempotency_key
        response = await client.post(
            path + "/index-jobs/" + job["request_id"] + "/retry", headers=headers()
        )
        assert response.status_code == 202
        commands = set()

        class Remote:
            crash = True

            async def retry(self, job_id, key):
                assert job_id == proof.job_id
                commands.add(key)
                if self.crash:
                    self.crash = False
                    raise asyncio.CancelledError()
                return IngestionReceipt(
                    job_id=job_id, generation_id=proof.generation_id, state="RUNNING"
                )

        remote = Remote()
        config = app.state.settings.model_copy(update={"knowledge_service_enabled": True})
        with pytest.raises(asyncio.CancelledError):
            await deliver_once(config, db=db, client=remote)
        async with db.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE knowledge_delivery_outbox "
                    "SET lease_until=now()-interval '1 second' WHERE id=:id"
                ),
                {"id": job["request_id"]},
            )
        await deliver_once(config, db=db, client=remote)
        assert len(commands) == 1
        async with db.session() as session:
            row = await session.get(DeliveryOutbox, job["request_id"])
            assert row.remote_retry_key is None and row.idempotency_key == identity
            assert row.state == "PENDING" and row.generation_id == proof.generation_id
