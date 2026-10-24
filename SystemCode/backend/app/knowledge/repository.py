"""Short PostgreSQL transactions; file I/O is deliberately outside this module."""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.core.hashing import digest
from app.core.pagination import decode_cursor, encode_cursor
from app.knowledge.models import KnowledgeDocument as Doc
from app.knowledge.models import KnowledgeVersion as Ver
from app.knowledge.schemas import Document, Metadata, Version
from app.operations.models import Command, OfferRow, ProductRow, Store


def missing():
    return AppError(
        404, "RESOURCE_NOT_FOUND", "Document or entity is not visible or does not exist"
    )


async def store_scope(session, principal, store_id):
    authorize_store(principal, store_id)
    if await session.get(Store, store_id) is None:
        raise missing()


async def entities(session, store_id, sku_ids, supplier_ids):
    for model, column, values in (
        (ProductRow, ProductRow.sku_id, sku_ids),
        (OfferRow, OfferRow.supplier_id, supplier_ids),
    ):
        if values:
            existing = set(
                await session.scalars(
                    select(column).where(model.store_id == store_id, column.in_(values))
                )
            )
            if existing != set(values):
                raise missing()


async def visible(session, principal, document_id, *, lock=False, content=False, write=False):
    statement = select(Doc).where(Doc.id == document_id).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    row = await session.scalar(statement)
    if row is None:
        raise missing()
    authorize_store(principal, row.store_id)
    if row.visibility == "private" and row.owner_principal_id != principal.principal_id:
        # Admin can discover metadata across stores, but cannot read or declassify private files.
        if content or write or "admin" not in principal.roles:
            raise missing()
    if content and row.status == "archived":
        raise missing()
    return row


def document(row):
    return Document.model_validate(row)


def cas(row, expected):
    if row.metadata_version != expected:
        raise AppError(409, "METADATA_VERSION_CONFLICT", "Document changed; refresh its metadata")


async def receipt(session, principal, operation, key):
    identifier = digest(["knowledge", operation, principal.principal_id, key])
    fresh = await session.scalar(
        insert(Command)
        .values(id=identifier, content_hash="", response={})
        .on_conflict_do_nothing()
        .returning(Command.id)
    )
    result = await session.get(Command, identifier)
    if fresh is None:
        # Reauthorize before revealing the saved result OR its fingerprint mismatch.
        await visible(session, principal, result.response["id"], lock=True, write=True)
    return result, fresh is None


def replay_or_set(row, replay, content):
    fingerprint = digest(content)
    if replay:
        if row.content_hash != fingerprint:
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Key was used for different content")
        return Document.model_validate(row.response)
    row.content_hash = fingerprint
    return None


def upload_fingerprint(upload, body):
    # K1 receipts predate provenance. Both omission and null mean no supplied
    # provenance; keep all other defaults (including validity nulls) unchanged.
    metadata = body.model_dump(mode="json")
    if metadata.get("provenance") is None:
        metadata.pop("provenance", None)
    return {
        "metadata": metadata,
        "original_name": upload.original_name,
        "content_sha256": upload.content_sha256,
        "size_bytes": upload.size_bytes,
        "mime_type": upload.mime_type,
    }


def replay_upload_or_set(row, replay, content):
    # Also recognize receipts written after provenance was added but before null
    # was omitted from the fingerprint. Explicit provenance never uses this alias.
    if replay and "provenance" not in content["metadata"]:
        with_null = {**content, "metadata": {**content["metadata"], "provenance": None}}
        if row.content_hash == digest(with_null):
            return replay_or_set(row, replay, with_null)
    return replay_or_set(row, replay, content)


async def add_version(session, row, body, upload, principal):
    number = (
        await session.scalar(select(func.max(Ver.version_no)).where(Ver.document_id == row.id)) or 0
    ) + 1
    version = Ver(
        id=str(uuid4()),
        document_id=row.id,
        version_no=number,
        original_name=upload.original_name,
        mime_type=upload.mime_type,
        content_sha256=upload.content_sha256,
        size_bytes=upload.size_bytes,
        raw_key=upload.raw_key,
        created_by=principal.principal_id,
        created_at=datetime.now(UTC),
        valid_from=body.valid_from,
        valid_until=body.valid_until,
    )
    session.add(version)
    await session.flush()
    from shopsteward_knowledge.contracts import Provenance

    from app.knowledge.index_models import VersionProvenance

    session.add(
        VersionProvenance(
            version_id=version.id,
            original_sha256=version.content_sha256,
            **(body.provenance or Provenance()).model_dump(),
        )
    )
    await session.flush()
    row.latest_version_id = version.id


async def create(session, principal, store_id, body, upload, key):
    await store_scope(session, principal, store_id)
    saved, replay = await receipt(session, principal, "create", key)
    previous = replay_upload_or_set(
        saved, replay, {"store_id": store_id, **upload_fingerprint(upload, body)}
    )
    if previous:
        return previous
    await entities(session, store_id, body.sku_ids, body.supplier_ids)
    now = datetime.now(UTC)
    row = Doc(
        id=str(uuid4()),
        store_id=store_id,
        owner_principal_id=principal.principal_id,
        **body.model_dump(exclude={"valid_from", "valid_until", "provenance"}),
        status="active",
        metadata_version=1,
        evidence_revision=1,
        latest_version_id=None,
        ingestion_status="UPLOADED",
        indexing_status="NOT_INDEXED",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    await add_version(session, row, body, upload, principal)
    saved.response = document(row).model_dump(mode="json")
    return document(row)


async def append(session, principal, document_id, body, upload, key):
    # All idempotent mutations acquire receipt then document locks, in that order.
    saved, replay = await receipt(session, principal, ["append", document_id], key)
    row = await visible(session, principal, document_id, lock=True, write=True)
    previous = replay_upload_or_set(saved, replay, upload_fingerprint(upload, body))
    if previous:
        return previous
    cas(row, body.expected_metadata_version)
    if row.status != "active":
        raise AppError(409, "DOCUMENT_ARCHIVED", "Restore document before appending a version")
    await add_version(session, row, body, upload, principal)
    row.metadata_version += 1
    row.updated_at = datetime.now(UTC)
    from app.knowledge.indexing import enqueue_projections

    await enqueue_projections(session, row, version_id=row.latest_version_id)
    saved.response = document(row).model_dump(mode="json")
    return document(row)


async def patch(session, principal, document_id, body, key):
    saved, replay = await receipt(session, principal, ["patch", document_id], key)
    row = await visible(session, principal, document_id, lock=True, write=True)
    previous = replay_or_set(saved, replay, body.model_dump(exclude_unset=True))
    if previous:
        return previous
    cas(row, body.expected_metadata_version)
    try:
        metadata = Metadata.model_validate(
            {field: getattr(row, field) for field in Metadata.model_fields}
            | body.model_dump(exclude_unset=True, exclude={"expected_metadata_version"})
        )
    except ValidationError as exc:
        raise AppError(422, "VALIDATION_ERROR", "Invalid document metadata") from exc
    await entities(session, row.store_id, metadata.sku_ids, metadata.supplier_ids)
    for field, value in metadata.model_dump().items():
        setattr(row, field, value)
    row.metadata_version += 1
    row.evidence_revision += 1
    row.updated_at = datetime.now(UTC)
    from app.knowledge.indexing import enqueue_projections

    await enqueue_projections(session, row)
    saved.response = document(row).model_dump(mode="json")
    return document(row)


async def control(session, principal, document_id, body, key):
    saved, replay = await receipt(session, principal, ["control", document_id], key)
    row = await visible(session, principal, document_id, lock=True, write=True)
    previous = replay_or_set(saved, replay, body.model_dump())
    if previous:
        return previous
    cas(row, body.expected_metadata_version)
    target = "archived" if body.operation == "archive" else "active"
    if target == row.status:
        raise AppError(409, "INVALID_DOCUMENT_STATE", "Document already has the requested status")
    row.status = target
    row.metadata_version += 1
    row.evidence_revision += 1
    row.updated_at = datetime.now(UTC)
    from app.knowledge.indexing import enqueue_projections

    await enqueue_projections(session, row)
    saved.response = document(row).model_dump(mode="json")
    return document(row)


async def listing(
    session, principal, store_id, *, category, supplier_id, sku_id, status, q, cursor, limit
):
    await store_scope(session, principal, store_id)
    await entities(
        session, store_id, [sku_id] if sku_id else [], [supplier_id] if supplier_id else []
    )
    scope = [
        "knowledge-documents",
        principal.principal_id,
        sorted(principal.roles),
        sorted(principal.store_ids),
        store_id,
        category,
        supplier_id,
        sku_id,
        status,
        q,
    ]
    after = decode_cursor(cursor, scope)
    statement = select(Doc).where(Doc.store_id == store_id, Doc.status == status)
    if "admin" not in principal.roles:
        statement = statement.where(
            or_(Doc.visibility == "store", Doc.owner_principal_id == principal.principal_id)
        )
    if category:
        statement = statement.where(Doc.category == category)
    if sku_id:
        statement = statement.where(Doc.sku_ids.contains([sku_id]))
    if supplier_id:
        statement = statement.where(Doc.supplier_ids.contains([supplier_id]))
    if q:
        statement = statement.where(Doc.title.icontains(q, autoescape=True))
    if after:
        statement = statement.where(tuple_(Doc.created_at, Doc.id) < after)
    rows = list(
        await session.scalars(
            statement.order_by(Doc.created_at.desc(), Doc.id.desc()).limit(limit + 1)
        )
    )
    return {
        "items": [document(row) for row in rows[:limit]],
        "next_cursor": encode_cursor(scope, rows[limit - 1]) if len(rows) > limit else None,
    }


async def versions(session, principal, document_id, cursor, limit):
    await visible(session, principal, document_id, content=True)
    scope = digest(["knowledge-versions", document_id, principal.principal_id])
    statement = select(Ver).where(Ver.document_id == document_id)
    if cursor:
        try:
            decoded = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            number = decoded["version_no"]
            if decoded["scope"] != scope or type(number) is not int or not 1 <= number <= 2**63 - 1:
                raise ValueError()
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise AppError(422, "INVALID_CURSOR", "Invalid version cursor") from exc
        statement = statement.where(Ver.version_no < number)
    rows = list(await session.scalars(statement.order_by(Ver.version_no.desc()).limit(limit + 1)))
    following = None
    if len(rows) > limit:
        following = base64.urlsafe_b64encode(
            json.dumps({"scope": scope, "version_no": rows[limit - 1].version_no}).encode()
        ).decode()
    return {
        "items": [await version_dto(session, row) for row in rows[:limit]],
        "next_cursor": following,
    }


async def version(session, principal, document_id, version_id):
    await visible(session, principal, document_id, content=True)
    row = await session.scalar(
        select(Ver).where(Ver.id == version_id, Ver.document_id == document_id)
    )
    if row is None:
        raise missing()
    return row


async def version_dto(session, row):
    from app.knowledge.indexing import provenance

    dto = Version.model_validate(row)
    dto.provenance = await provenance(session, row)
    return dto
