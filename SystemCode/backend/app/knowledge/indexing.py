"""Local index requests and explicit, CAS protected publication authority."""

from datetime import UTC, datetime
from uuid import uuid4

from shopsteward_knowledge.contracts import IngestionRequest, OriginalRef, Projection, Provenance
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.dependencies import require_role
from app.core.errors import AppError
from app.core.hashing import digest
from app.knowledge import repository as repo
from app.knowledge.index_models import DeliveryOutbox, Publication, VersionProvenance
from app.knowledge.models import KnowledgeVersion as Ver
from app.operations.models import Command


async def provenance(session, version):
    row = await session.get(VersionProvenance, version.id)
    return (
        Provenance(**{k: getattr(row, k) for k in Provenance.model_fields}) if row else Provenance()
    )


async def projection(session, doc, version):
    return Projection(
        document_id=doc.id,
        version_id=version.id,
        store_id=doc.store_id,
        metadata_revision=doc.evidence_revision,
        title=doc.title,
        status=doc.status,
        entity_refs=sorted(set(doc.sku_ids + doc.supplier_ids)),
        valid_from=version.valid_from,
        valid_until=version.valid_until,
        provenance=await provenance(session, version),
    )


def progress(row):
    return {
        "request_id": row.id,
        "document_id": row.document_id,
        "version_id": row.version_id,
        "metadata_revision": row.metadata_revision,
        "state": row.state,
        "attempt": row.attempt,
        "job_id": row.job_id,
        "generation_id": row.generation_id,
        "manifest_hash": row.manifest_hash,
        "error": row.error,
    }


async def enqueue(session, doc, version, operation, payload, identity):
    now = datetime.now(UTC)
    await session.execute(
        insert(DeliveryOutbox)
        .values(
            id=str(uuid4()),
            document_id=doc.id,
            version_id=version.id,
            metadata_revision=doc.evidence_revision,
            operation=operation,
            idempotency_key=identity,
            payload_hash=digest(payload),
            payload=payload,
            state="PENDING",
            attempt=0,
            retry_count=0,
            next_attempt_at=now,
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=[DeliveryOutbox.idempotency_key])
    )
    row = await session.scalar(
        select(DeliveryOutbox).where(DeliveryOutbox.idempotency_key == identity)
    )
    if row.payload_hash != digest(payload):
        raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Key was used for different content")
    return row


async def request_index(session, principal, version_id, profile_id, key):
    require_role(principal, "operator")
    version = await session.get(Ver, version_id)
    if version is None:
        raise repo.missing()
    doc = await repo.visible(session, principal, version.document_id, lock=True, write=True)
    identity = digest(["ingest", principal.principal_id, version_id, key])
    old = await session.scalar(
        select(DeliveryOutbox).where(DeliveryOutbox.idempotency_key == identity)
    )
    if old:
        if old.payload["profile_id"] != profile_id:
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Key was used for different content")
        return progress(old)
    if doc.status != "active":
        raise AppError(409, "DOCUMENT_ARCHIVED", "Restore document before indexing")
    request = IngestionRequest(
        original=OriginalRef(
            version_id=version.id,
            sha256=version.content_sha256,
            mime=version.mime_type,
            storage_key=version.raw_key,
            size_bytes=version.size_bytes,
        ),
        projection=await projection(session, doc, version),
        profile_id=profile_id,
    )
    row = await enqueue(session, doc, version, "ingest", request.model_dump(mode="json"), identity)
    doc.indexing_status = "QUEUED"
    return progress(row)


async def enqueue_projections(session, doc, *, version_id=None):
    # Metadata edits invalidate all versions; append preserves existing evidence.
    if version_id is None:
        doc.indexing_status = "NOT_INDEXED"
    await session.flush()
    versions = select(Ver).where(Ver.document_id == doc.id)
    if version_id is not None:
        versions = versions.where(Ver.id == version_id)
    for version in await session.scalars(versions):
        payload = (await projection(session, doc, version)).model_dump(mode="json")
        await enqueue(
            session,
            doc,
            version,
            "projection",
            payload,
            digest(["projection", version.id, doc.evidence_revision]),
        )
    # Projection acknowledgement does not prove that the searchable index was refreshed.
    # Preserve publication activation revisions; new READY + explicit CAS restores visibility.


async def get_request(session, principal, document_id, request_id, *, write=False):
    await repo.visible(session, principal, document_id, write=write, content=not write)
    row = await session.get(DeliveryOutbox, request_id)
    if row is None or row.document_id != document_id or row.operation != "ingest":
        raise repo.missing()
    return row


async def retry_request(session, principal, document_id, request_id, key):
    require_role(principal, "operator")
    # K1 receipt lock order prevents competing manual retries consuming two attempts.
    saved, replay = await repo.receipt(session, principal, ["retry-index", request_id], key)
    doc = await repo.visible(session, principal, document_id, lock=True, write=True)
    fingerprint = digest([document_id, request_id])
    if replay:
        if saved.content_hash != fingerprint:
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Retry arguments changed")
        return saved.response["result"]
    row = await get_request(session, principal, document_id, request_id, write=True)
    await session.refresh(row, with_for_update=True)
    if row.state != "FAILED" or doc.status != "active":
        raise AppError(409, "INVALID_INDEX_STATE", "Only failed active requests can be retried")
    row.state, row.retry_count, row.error = "PENDING", 0, None
    if row.job_id:
        row.remote_retry_key = digest(["retry", row.id, principal.principal_id, key])
    row.next_attempt_at = datetime.now(UTC)
    # Preserve remote receipt and original identity; retry command has its own durable key.
    doc.indexing_status = "QUEUED"
    result = progress(row)
    saved.content_hash, saved.response = fingerprint, {"id": doc.id, "result": result}
    return result


def overlaps(a_from, a_until, b_from, b_until):
    return (a_until is None or b_from is None or b_from < a_until) and (
        b_until is None or a_from is None or a_from < b_until
    )


def publication_fingerprint(
    version_id,
    generation_id,
    manifest_hash,
    expected_revision,
    replace_version_ids,
    valid_from=None,
    valid_until=None,
):
    values = [
        version_id,
        generation_id,
        manifest_hash,
        expected_revision,
        sorted(set(replace_version_ids)),
    ]
    # Preserve existing receipts for requests that did not specify publication bounds.
    if valid_from is not None or valid_until is not None:
        values.append(
            [
                valid_from.isoformat() if valid_from else None,
                valid_until.isoformat() if valid_until else None,
            ]
        )
    return digest(values)


async def publication_replay(session, principal, document_id, body, key):
    """Reauthorize before exposing either a completed result or its fingerprint conflict."""
    require_role(principal, "operator")
    await repo.visible(session, principal, document_id, lock=True, write=True)
    saved = await session.get(
        Command, digest(["knowledge", ["publish", document_id], principal.principal_id, key])
    )
    if saved is None:
        # Compatibility with receipts written before publication keys were document scoped.
        saved = await session.get(
            Command,
            digest(["knowledge", ["publish", body.version_id], principal.principal_id, key]),
        )
    if saved is None or not saved.response.get("result"):
        return None
    if saved.response["id"] != document_id:
        raise repo.missing()
    fingerprint = publication_fingerprint(
        body.version_id,
        body.generation_id,
        body.manifest_hash,
        body.expected_publication_revision,
        body.replace_version_ids,
        body.valid_from,
        body.valid_until,
    )
    if saved.content_hash != fingerprint:
        raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Publication arguments changed")
    return saved.response["result"]


def publication_interval(version, valid_from, valid_until):
    start = valid_from if valid_from is not None else version.valid_from
    end = valid_until if valid_until is not None else version.valid_until
    if (
        (start is not None and end is not None and start >= end)
        or (version.valid_from is not None and (start is None or start < version.valid_from))
        or (version.valid_until is not None and (end is None or end > version.valid_until))
    ):
        raise AppError(
            422, "INVALID_PUBLICATION_INTERVAL", "Publication must fit original validity"
        )
    return start, end


def residual_intervals(old_from, old_until, start, end):
    """Subtract an overlapping half-open replacement; preserve both unaffected sides."""
    intervals = []
    if start is not None and (old_from is None or old_from < start):
        intervals.append((old_from, start))
    if end is not None and (old_until is None or end < old_until):
        intervals.append((end, old_until))
    return intervals


async def ready_request(session, principal, document_id, version_id, generation_id, manifest_hash):
    await repo.visible(session, principal, document_id, content=True, write=True)
    row = await session.scalar(
        select(DeliveryOutbox).where(
            DeliveryOutbox.document_id == document_id,
            DeliveryOutbox.version_id == version_id,
            DeliveryOutbox.generation_id == generation_id,
            DeliveryOutbox.manifest_hash == manifest_hash,
            DeliveryOutbox.operation == "ingest",
            DeliveryOutbox.state == "SUCCEEDED",
        )
    )
    if row is None:
        raise AppError(
            409, "GENERATION_NOT_READY", "A completed matching index request is required"
        )
    return row


async def activate_generation(
    session,
    principal,
    version_id,
    generation_id,
    manifest_hash,
    expected_publication_revision,
    *,
    proof,
    request_id,
    key,
    replace_version_ids=(),
    valid_from=None,
    valid_until=None,
):
    require_role(principal, "operator")
    version = await session.get(Ver, version_id)
    if version is None:
        raise repo.missing()
    saved, replay = await repo.receipt(session, principal, ["publish", version.document_id], key)
    doc = await repo.visible(session, principal, version.document_id, lock=True, write=True)
    fingerprint = publication_fingerprint(
        version_id,
        generation_id,
        manifest_hash,
        expected_publication_revision,
        replace_version_ids,
        valid_from,
        valid_until,
    )
    if replay:
        if saved.content_hash != fingerprint:
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Publication arguments changed")
        return saved.response["result"]
    row = await session.get(DeliveryOutbox, request_id)
    if (
        doc.status != "active"
        or doc.publication_revision != expected_publication_revision
        or row is None
        or row.version_id != version_id
        or row.state != "SUCCEEDED"
        or row.metadata_revision != doc.evidence_revision
        or row.generation_id != generation_id
        or row.manifest_hash != manifest_hash
        or row.job_id != proof.job_id
        or proof.state != "SUCCEEDED"
        or proof.generation_id != generation_id
        or proof.manifest_hash != manifest_hash
    ):
        raise AppError(
            409, "PUBLICATION_CONFLICT", "READY proof or current metadata/publication changed"
        )
    start, end = publication_interval(version, valid_from, valid_until)
    current = list(
        await session.scalars(
            select(Publication).where(
                Publication.document_id == doc.id, Publication.active.is_(True)
            )
        )
    )
    conflicting = {
        p.version_id
        for p in current
        if p.version_id != version_id and overlaps(p.valid_from, p.valid_until, start, end)
    }
    if conflicting != set(replace_version_ids):
        raise AppError(
            409,
            "PUBLICATION_INTERVAL_CONFLICT",
            "Explicitly name all overlapping versions to replace",
        )
    for pub in current:
        if overlaps(pub.valid_from, pub.valid_until, start, end):
            pub.active = False
            for remaining_from, remaining_until in residual_intervals(
                pub.valid_from, pub.valid_until, start, end
            ):
                doc.publication_revision += 1
                session.add(
                    Publication(
                        id=str(uuid4()),
                        document_id=doc.id,
                        version_id=pub.version_id,
                        generation_id=pub.generation_id,
                        manifest_hash=pub.manifest_hash,
                        metadata_revision=pub.metadata_revision,
                        publication_revision=doc.publication_revision,
                        valid_from=remaining_from,
                        valid_until=remaining_until,
                        active=True,
                        created_at=datetime.now(UTC),
                    )
                )
    doc.publication_revision += 1
    pub = Publication(
        id=str(uuid4()),
        document_id=doc.id,
        version_id=version.id,
        generation_id=generation_id,
        manifest_hash=manifest_hash,
        metadata_revision=doc.evidence_revision,
        publication_revision=doc.publication_revision,
        valid_from=start,
        valid_until=end,
        active=True,
        created_at=datetime.now(UTC),
    )
    session.add(pub)
    result = {
        "document_id": doc.id,
        "version_id": version_id,
        "generation_id": generation_id,
        "manifest_hash": manifest_hash,
        "publication_revision": doc.publication_revision,
        "valid_from": start.isoformat() if start else None,
        "valid_until": end.isoformat() if end else None,
    }
    saved.content_hash, saved.response = fingerprint, {"id": doc.id, "result": result}
    return result


async def detail(session, principal, document_id):
    doc = await repo.visible(session, principal, document_id)
    dto = repo.document(doc)
    # Admin discovery of private metadata must not expose publication identities.
    if doc.visibility == "private" and doc.owner_principal_id != principal.principal_id:
        return dto
    rows = await session.scalars(
        select(Publication).where(Publication.document_id == doc.id, Publication.active.is_(True))
    )
    dto.publications = [
        {
            "version_id": p.version_id,
            "generation_id": p.generation_id,
            "manifest_hash": p.manifest_hash,
            "metadata_revision": p.metadata_revision,
            "valid_from": p.valid_from,
            "valid_until": p.valid_until,
            "requires_republication": p.metadata_revision != doc.evidence_revision,
        }
        for p in rows
    ]
    dto.requires_republication = any(p["requires_republication"] for p in dto.publications)
    return dto
