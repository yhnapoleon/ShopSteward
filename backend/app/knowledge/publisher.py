"""Run separately with python -m app.knowledge.publisher; never a business job handler."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from uuid import uuid4

import httpx
from pydantic import ValidationError
from shopsteward_knowledge.contracts import IngestionRequest, Projection
from sqlalchemy import func, or_, select

from app.core.config import Settings
from app.core.errors import AppError
from app.core.hashing import digest
from app.db.session import Database
from app.knowledge.index_models import DeliveryOutbox
from app.knowledge.models import KnowledgeDocument
from app.knowledge.service_client import connect
from app.knowledge.storage import original_path
from app.operations.models import Command

log = logging.getLogger(__name__)


def retry_delay(status, attempt, retry_after=None):
    if attempt >= 5 or (400 <= status < 500 and status not in {408, 429}):
        return None
    delay = min(60, 2 ** max(0, attempt - 1))
    if status == 429 and retry_after:
        try:
            value = float(retry_after)
        except ValueError:
            try:
                value = (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                value = delay
        delay = max(delay, min(60, max(0, value)))
    return delay


async def claim(db, settings, owner):
    async with db.session() as session, session.begin():
        row = await session.scalar(
            select(DeliveryOutbox)
            .where(
                or_(
                    (DeliveryOutbox.state.in_(["PENDING", "RETRY_WAIT"]))
                    & (DeliveryOutbox.next_attempt_at <= func.now()),
                    (DeliveryOutbox.state == "RUNNING")
                    & (DeliveryOutbox.lease_until <= func.now()),
                )
            )
            .order_by(DeliveryOutbox.next_attempt_at, DeliveryOutbox.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None
        now = await session.scalar(select(func.clock_timestamp()))
        row.state, row.lease_owner, row.lease_token = "RUNNING", owner, str(uuid4())
        row.lease_until = now + timedelta(seconds=settings.knowledge_delivery_lease_seconds)
        row.attempt += 1
        await session.flush()
        return row


async def acknowledge(db, claimed, *, receipt=None, status=200, error=None, retry_after=None):
    async with db.session() as session, session.begin():
        # Lock order is document then outbox, consistent with request/retry/metadata writes.
        doc = await session.get(KnowledgeDocument, claimed.document_id, with_for_update=True)
        row = await session.scalar(
            select(DeliveryOutbox)
            .where(
                DeliveryOutbox.id == claimed.id,
                DeliveryOutbox.state == "RUNNING",
                DeliveryOutbox.lease_token == claimed.lease_token,
                DeliveryOutbox.lease_until > func.clock_timestamp(),
            )
            .with_for_update()
        )
        if row is None:
            return False
        now = await session.scalar(select(func.clock_timestamp()))
        if error:
            row.retry_count += 1
            delay = retry_delay(status, row.retry_count, retry_after)
            row.state = "FAILED" if delay is None else "RETRY_WAIT"
            row.next_attempt_at = now + timedelta(seconds=delay or 0)
            row.error = error
        elif receipt is None:  # Projection receipt; revision/hash conflicts are HTTP failures.
            row.state, row.error = "SUCCEEDED", None
        else:
            # Local delivery attempts count polls/HTTP failures, not remote builds.
            # Keep the remote watermark durably in the existing receipt store. The
            # outbox lock serializes these writes; never modify the ingestion payload.
            receipt_key = digest(["knowledge-delivery-receipt", row.id])
            saved = await session.get(Command, receipt_key)
            previous = saved.response if saved else None
            if (
                (row.job_id and row.job_id != receipt.job_id)
                or receipt.attempt < 0
                or (previous and receipt.attempt < previous["attempt"])
                or (
                    row.generation_id
                    and row.generation_id != receipt.generation_id
                    # Legacy rows have no known remote attempt. First establish a
                    # matching-generation baseline; do not guess an ordering.
                    and (previous is None or receipt.attempt <= previous["attempt"])
                )
                or (receipt.state == "SUCCEEDED" and not receipt.manifest_hash)
            ):
                row.state, row.error = "FAILED", "INVALID_RECEIPT"
            else:
                accepted = receipt.model_dump(mode="json")
                if saved is None:
                    session.add(
                        Command(id=receipt_key, content_hash=digest(accepted), response=accepted)
                    )
                else:
                    saved.content_hash, saved.response = digest(accepted), accepted
                row.job_id, row.generation_id = receipt.job_id, receipt.generation_id
                row.remote_retry_key = None
                row.manifest_hash = receipt.manifest_hash
                row.state = receipt.state if receipt.state in {"SUCCEEDED", "FAILED"} else "PENDING"
                row.error = "REMOTE_INGESTION_FAILED" if receipt.state == "FAILED" else None
                row.next_attempt_at = now + timedelta(seconds=1)
        row.lease_token = row.lease_owner = row.lease_until = None
        if row.operation == "ingest" and doc.evidence_revision == row.metadata_revision:
            doc.indexing_status = {"SUCCEEDED": "READY", "FAILED": "FAILED"}.get(
                row.state, "INDEXING"
            )
        await session.flush()
        return True


async def deliver_once(settings, *, db=None, client=None, owner=None):
    if not settings.knowledge_service_enabled:
        return False
    own_db = db is None
    if db is None:
        db = Database(settings.database_url.get_secret_value() if settings.database_url else None)
    try:
        row = await claim(db, settings, owner or str(uuid4()))
        if row is None:
            return False

        async def deliver(remote):
            if row.operation == "projection":
                await remote.project(Projection.model_validate(row.payload), row.idempotency_key)
                return None
            if row.job_id and row.remote_retry_key:
                return await remote.retry(row.job_id, row.remote_retry_key)
            if row.job_id:
                return await remote.job(row.job_id)
            payload = IngestionRequest.model_validate(row.payload)
            path = original_path(settings.knowledge_storage_root, payload.original.storage_key)
            content = await asyncio.to_thread(path.read_bytes)
            if (
                len(content) != payload.original.size_bytes
                or hashlib.sha256(content).hexdigest() != payload.original.sha256
            ):
                raise ValueError("original identity mismatch")
            return await remote.ingest(payload, content, row.idempotency_key)

        try:
            # A whole-attempt timeout also bounds injected transports and slow files.
            async with asyncio.timeout(settings.knowledge_http_timeout_seconds):
                if client is None:
                    async with connect(settings) as remote:
                        receipt = await deliver(remote)
                else:
                    receipt = await deliver(client)
            await acknowledge(db, row, receipt=receipt)
        except httpx.HTTPStatusError as exc:
            await acknowledge(
                db,
                row,
                status=exc.response.status_code,
                error=f"HTTP_{exc.response.status_code}",
                retry_after=exc.response.headers.get("Retry-After"),
            )
        except (httpx.RequestError, TimeoutError, OSError, AppError):
            await acknowledge(db, row, status=503, error="KNOWLEDGE_UNAVAILABLE")
        except (ValueError, ValidationError):
            await acknowledge(db, row, status=422, error="INVALID_PAYLOAD_OR_RECEIPT")
        return True
    finally:
        if own_db:
            await db.dispose()


async def main():
    settings = Settings()
    if not settings.knowledge_service_enabled or not settings.knowledge_service_key:
        raise SystemExit("Knowledge service must be enabled and configured")
    db = Database(settings.database_url.get_secret_value() if settings.database_url else None)
    owner = str(uuid4())
    try:
        if not await db.ready():
            raise SystemExit("Apply backend migrations before starting publisher")
        while True:
            if not await deliver_once(settings, db=db, owner=owner):
                await asyncio.sleep(1)
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
