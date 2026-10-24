"""Real acknowledgements with a persistence double; no PostgreSQL locking claims."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from shopsteward_knowledge.contracts import IngestionReceipt
from sqlalchemy.orm.evaluator import _EvaluatorCompiler
from sqlalchemy.sql.functions import Function

from app.knowledge.index_models import DeliveryOutbox
from app.knowledge.models import KnowledgeDocument
from app.knowledge.publisher import acknowledge
from app.operations.models import Command


class Persistence:
    def __init__(self):
        self.now = datetime.now(UTC)
        self.doc = KnowledgeDocument(id="D1", evidence_revision=1, indexing_status="INDEXING")
        self.row = DeliveryOutbox(
            id="R1",
            document_id="D1",
            version_id="V1",
            operation="ingest",
            metadata_revision=1,
            state="PENDING",
            attempt=0,
            retry_count=0,
            payload={"profile_id": "lexical-v1"},
            payload_hash="a" * 64,
            idempotency_key="original-key",
        )
        self.commands = {}

    @asynccontextmanager
    async def session(self):
        yield self

    @asynccontextmanager
    async def begin(self):
        yield self

    async def get(self, model, identity, **kwargs):
        if model is KnowledgeDocument:
            assert identity == self.doc.id and kwargs["with_for_update"]
            return self.doc
        assert model is Command
        return self.commands.get(identity)

    async def scalar(self, statement):
        if statement.column_descriptions[0].get("entity") is DeliveryOutbox:
            now = self.now

            class Evaluator(_EvaluatorCompiler):
                def visit_function(self, clause):
                    assert isinstance(clause, Function) and clause.name == "clock_timestamp"
                    return lambda obj: now

            return self.row if Evaluator().process(statement.whereclause)(self.row) else None
        return self.now

    def add(self, command):
        assert isinstance(command, Command)
        self.commands[command.id] = command

    async def flush(self):
        pass

    def claim(self):
        self.row.attempt += 1
        self.row.state = "RUNNING"
        self.row.lease_token = f"lease-{self.row.attempt}"
        self.row.lease_owner = "publisher"
        self.row.lease_until = self.now + timedelta(seconds=60)
        return SimpleNamespace(
            id=self.row.id, document_id=self.row.document_id, lease_token=self.row.lease_token
        )


def receipt(generation="G1", attempt=1, state="RUNNING", job="J1"):
    return IngestionReceipt(
        job_id=job,
        generation_id=generation,
        attempt=attempt,
        state=state,
        manifest_hash="b" * 64 if state == "SUCCEEDED" else None,
    )


@pytest.mark.parametrize("manual", [False, True])
async def test_same_job_retry_can_finish_a_fresh_generation(manual):
    db = Persistence()
    assert await acknowledge(
        db, db.claim(), receipt=receipt(state="FAILED" if manual else "RUNNING")
    )
    if manual:
        db.row.remote_retry_key = "manual-retry-key"
        assert await acknowledge(db, db.claim(), receipt=receipt(state="PENDING"))
    assert await acknowledge(db, db.claim(), receipt=receipt("G2", 2, "SUCCEEDED"))
    assert (db.row.state, db.row.error, db.row.generation_id) == ("SUCCEEDED", None, "G2")
    assert db.doc.indexing_status == "READY"
    assert db.row.remote_retry_key is None
    assert db.row.payload == {"profile_id": "lexical-v1"}
    assert db.row.payload_hash == "a" * 64 and db.row.idempotency_key == "original-key"


@pytest.mark.parametrize(
    "incoming",
    [
        receipt("G2", 1, "SUCCEEDED"),  # Generation switch without a new attempt.
        receipt("G1", 0, "SUCCEEDED"),  # Older attempt, even with the same generation.
        receipt("G2", 2, "SUCCEEDED", job="J2"),
        receipt("G1", -1),
        IngestionReceipt(job_id="J1", generation_id="G1", attempt=1, state="SUCCEEDED"),
    ],
)
async def test_invalid_receipts_cannot_replace_accepted_identity(incoming):
    db = Persistence()
    await acknowledge(db, db.claim(), receipt=receipt())
    await acknowledge(db, db.claim(), receipt=incoming)
    assert (db.row.state, db.row.error) == ("FAILED", "INVALID_RECEIPT")
    assert (db.row.job_id, db.row.generation_id, db.row.manifest_hash) == ("J1", "G1", None)


async def test_remote_attempt_order_survives_session_reload_and_transport_failure():
    db = Persistence()
    await acknowledge(db, db.claim(), receipt=receipt("G2", 2))
    await acknowledge(db, db.claim(), status=503, error="NETWORK")
    # Detached ORM instances and JSON round trips prevent an in-process watermark passing.
    db.row = DeliveryOutbox(
        **{
            column.name: deepcopy(getattr(db.row, column.name))
            for column in DeliveryOutbox.__table__.columns
        }
    )
    db.commands = {
        key: Command(
            id=value.id, content_hash=value.content_hash, response=deepcopy(value.response)
        )
        for key, value in db.commands.items()
    }
    await acknowledge(db, db.claim(), receipt=receipt("G2", 1, "SUCCEEDED"))
    assert (db.row.state, db.row.error) == ("FAILED", "INVALID_RECEIPT")


@pytest.mark.parametrize("fence", ["expired", "reclaimed", "succeeded", "wrong-row"])
async def test_stale_acknowledgement_cannot_replace_ready(fence):
    db = Persistence()
    old = db.claim()
    if fence == "expired":
        db.row.lease_until = db.now
    elif fence == "reclaimed":
        db.claim()
    elif fence == "succeeded":
        db.row.state = "SUCCEEDED"
    else:
        old.id = "another-request"
    db.doc.indexing_status = "READY"
    db.row.job_id, db.row.generation_id, db.row.manifest_hash = "J0", "G0", "c" * 64
    assert not await acknowledge(db, old, receipt=receipt("G2", 2, "FAILED"))
    assert db.doc.indexing_status == "READY"
    assert (db.row.job_id, db.row.generation_id, db.row.manifest_hash) == ("J0", "G0", "c" * 64)
    assert db.commands == {}


async def test_current_receipt_does_not_change_ready_from_newer_metadata():
    db = Persistence()
    db.doc.evidence_revision, db.doc.indexing_status = 2, "READY"
    await acknowledge(db, db.claim(), receipt=receipt(state="FAILED"))
    assert db.doc.indexing_status == "READY"


async def test_polling_initial_generation_and_duplicate_receipts_remains_valid():
    db = Persistence()
    for proof in [
        receipt(attempt=0, state="PENDING"),
        receipt(),
        receipt(),
        receipt(state="SUCCEEDED"),
    ]:
        await acknowledge(db, db.claim(), receipt=proof)
        assert db.row.error is None
    assert db.row.state == "SUCCEEDED"


async def test_legacy_row_establishes_remote_attempt_before_changing_generation():
    db = Persistence()
    db.row.job_id, db.row.generation_id = "J1", "G1"
    await acknowledge(db, db.claim(), receipt=receipt(attempt=4))
    await acknowledge(db, db.claim(), receipt=receipt("G2", 5, "SUCCEEDED"))
    assert (db.row.state, db.row.generation_id) == ("SUCCEEDED", "G2")


async def test_legacy_row_cannot_guess_order_of_an_unknown_generation():
    db = Persistence()
    db.row.job_id, db.row.generation_id = "J1", "G1"
    await acknowledge(db, db.claim(), receipt=receipt("G2", 2, "SUCCEEDED"))
    assert (db.row.state, db.row.error, db.row.generation_id) == ("FAILED", "INVALID_RECEIPT", "G1")
