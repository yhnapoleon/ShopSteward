"""Exercise real repository mutations through an in-memory persistence boundary."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.knowledge import indexing, repository
from app.knowledge.index_models import DeliveryOutbox, Publication
from app.knowledge.models import KnowledgeDocument, KnowledgeVersion
from app.knowledge.schemas import AppendMetadata, Control, MetadataPatch, UploadMetadata


class Persistence:
    def __init__(self):
        now = datetime.now(UTC)
        self.doc = KnowledgeDocument(
            id="D1",
            store_id="S1",
            owner_principal_id="P1",
            title="Policy",
            category="general",
            sku_ids=[],
            supplier_ids=[],
            visibility="store",
            status="active",
            metadata_version=9,
            latest_version_id="V1",
            ingestion_status="UPLOADED",
            indexing_status="READY",
            publication_revision=1,
            created_at=now,
            updated_at=now,
        )
        self.doc.evidence_revision = 7
        self.versions = [
            KnowledgeVersion(
                id="V1",
                document_id="D1",
                version_no=1,
                content_sha256="a" * 64,
                mime_type="text/plain",
                raw_key="a" * 32 + ".raw",
                size_bytes=1,
                valid_from=None,
                valid_until=None,
            )
        ]
        self.outbox = []
        self.added = []

    async def scalar(self, statement):
        entity = (
            statement.column_descriptions[0].get("entity")
            if hasattr(statement, "column_descriptions")
            else None
        )
        if entity is KnowledgeDocument:
            return self.doc
        if entity is KnowledgeVersion:
            return max(v.version_no for v in self.versions)
        if entity is DeliveryOutbox:
            identity = statement.compile().params["idempotency_key_1"]
            return next(row for row in self.outbox if row.idempotency_key == identity)
        raise AssertionError(statement)

    async def scalars(self, statement):
        params = statement.compile().params
        return [v for v in self.versions if params.get("id_1", v.id) == v.id]

    async def execute(self, statement):
        self.outbox.append(DeliveryOutbox(**statement.compile().params))

    async def get(self, model, identity):
        if model is KnowledgeVersion:
            return next(v for v in self.versions if v.id == identity)
        return None

    async def flush(self):
        pass

    def add(self, value):
        self.added.append(value)
        if isinstance(value, KnowledgeVersion):
            self.versions.append(value)
        if isinstance(value, KnowledgeDocument):
            # Emulate the existing insert default applied by a PostgreSQL flush.
            value.publication_revision = 0
            self.doc = value


@pytest.fixture
def boundary(monkeypatch):
    session = Persistence()
    principal = SimpleNamespace(principal_id="P1", store_ids=["S1"], roles=["operator"])
    saved = SimpleNamespace(content_hash="", response={})
    monkeypatch.setattr(repository, "receipt", AsyncMock(return_value=(saved, False)))
    return session, principal, saved


def upload():
    return SimpleNamespace(
        original_name="new.txt",
        content_sha256="b" * 64,
        size_bytes=1,
        mime_type="text/plain",
        raw_key="b" * 32 + ".raw",
    )


async def test_append_keeps_published_revision_and_projects_only_new_original(boundary):
    session, principal, saved = boundary
    result = await repository.append(
        session, principal, "D1", AppendMetadata(expected_metadata_version=9), upload(), "append"
    )
    assert session.doc.metadata_version == 10
    assert session.doc.evidence_revision == 7
    assert len(session.outbox) == 1
    assert session.outbox[0].version_id == result.latest_version_id != "V1"
    assert session.outbox[0].metadata_revision == 7
    assert session.outbox[0].payload["metadata_revision"] == 7
    assert result.evidence_revision == saved.response["evidence_revision"] == 7


@pytest.mark.parametrize("operation", ["patch", "archive", "restore"])
async def test_metadata_and_visibility_changes_increment_both_counters(boundary, operation):
    session, principal, _ = boundary
    if operation == "patch":
        result = await repository.patch(
            session,
            principal,
            "D1",
            MetadataPatch(expected_metadata_version=9, title="New policy"),
            "patch",
        )
    else:
        if operation == "restore":
            session.doc.status = "archived"
        result = await repository.control(
            session,
            principal,
            "D1",
            Control(expected_metadata_version=9, operation=operation),
            operation,
        )
    assert result.metadata_version == 10
    assert session.doc.evidence_revision == result.evidence_revision == 8
    assert (
        session.outbox[0].metadata_revision == session.outbox[0].payload["metadata_revision"] == 8
    )


async def test_new_upload_starts_both_counters_at_one(boundary, monkeypatch):
    session, principal, _ = boundary
    session.versions = []
    monkeypatch.setattr(repository, "store_scope", AsyncMock())
    # This test still calls the real create/add_version logic.
    original_scalar = session.scalar

    async def scalar(statement):
        if statement.column_descriptions[0].get("entity") is KnowledgeVersion:
            return None
        return await original_scalar(statement)

    session.scalar = scalar
    result = await repository.create(
        session, principal, "S1", UploadMetadata(title="New"), upload(), "create"
    )
    assert result.metadata_version == result.evidence_revision == 1


async def test_append_keeps_old_publication_current_in_authority_query(boundary):
    from app.agent_bridge.document_evidence import current_authority

    session, principal, _ = boundary
    await repository.append(
        session, principal, "D1", AppendMetadata(expected_metadata_version=9), upload(), "append"
    )
    publication = Publication(
        version_id="V1", generation_id="G1", metadata_revision=7, valid_from=None, valid_until=None
    )

    class AuthorityPersistence:
        async def execute(self, statement):
            # Evaluate the actual authority revision predicate against persisted state.
            from sqlalchemy.sql import operators, visitors
            from sqlalchemy.sql.elements import BinaryExpression

            matching = [
                node
                for node in visitors.iterate(statement.whereclause)
                if isinstance(node, BinaryExpression)
                and node.operator is operators.eq
                and getattr(node.left, "table", None) is Publication.__table__
                and node.left.name == "metadata_revision"
            ]
            assert len(matching) == 1
            current = publication.metadata_revision == getattr(session.doc, matching[0].right.name)
            return SimpleNamespace(
                all=lambda: (
                    [(publication, session.doc, session.versions[0], None)] if current else []
                )
            )

    authority = await current_authority(AuthorityPersistence(), principal, "S1", datetime.now(UTC))
    assert authority["V1"]["generation_id"] == "G1"
    assert authority["V1"]["metadata_revision"] == 7


async def test_projection_uses_evidence_revision_not_append_cas_counter(boundary):
    session, _, _ = boundary
    projected = await indexing.projection(session, session.doc, session.versions[0])
    assert projected.metadata_revision == 7


def test_legacy_document_receipt_defaults_evidence_to_its_metadata_revision(boundary):
    from app.knowledge.schemas import Document

    session, _, _ = boundary
    legacy = repository.document(session.doc).model_dump(mode="json")
    legacy.pop("evidence_revision", None)
    assert Document.model_validate(legacy).evidence_revision == 9


@pytest.mark.parametrize("revision,expected_status", [(7, "FAILED"), (9, "READY")])
async def test_publisher_acknowledges_only_current_evidence_revision(
    boundary, revision, expected_status
):
    from contextlib import asynccontextmanager

    from shopsteward_knowledge.contracts import IngestionReceipt

    from app.knowledge.publisher import acknowledge

    session, _, _ = boundary
    row = DeliveryOutbox(
        id="R1",
        document_id="D1",
        operation="ingest",
        metadata_revision=revision,
        lease_token="lease",
        job_id=None,
        generation_id=None,
    )

    class AcknowledgementPersistence:
        @asynccontextmanager
        async def session(self):
            yield self

        @asynccontextmanager
        async def begin(self):
            yield self

        async def get(self, model, identity, **kwargs):
            from app.operations.models import Command

            if model is Command:
                return None
            assert model is KnowledgeDocument and identity == "D1"
            return session.doc

        def add(self, value):
            session.add(value)

        async def scalar(self, statement):
            if statement.column_descriptions[0].get("entity") is DeliveryOutbox:
                return row
            return datetime.now(UTC)

        async def flush(self):
            pass

    assert await acknowledge(
        AcknowledgementPersistence(),
        row,
        receipt=IngestionReceipt(job_id="J1", generation_id="G1", state="FAILED", error="parser"),
    )
    assert row.state == "FAILED"
    assert session.doc.indexing_status == expected_status
