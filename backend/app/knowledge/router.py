from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.api.dependencies import Cursor, Id, Key, Limit, User, require_role
from app.api.routing import errors
from app.api.schemas import Error
from app.core.errors import AppError
from app.knowledge import repository as repo
from app.knowledge.schemas import (
    AppendMetadata,
    Control,
    Document,
    DocumentList,
    MetadataPatch,
    Status,
    UploadMetadata,
    Version,
    VersionList,
)
from app.knowledge.storage import original_path, receive_upload


class KnowledgeRouter(APIRouter):
    def add_api_route(self, path, endpoint, *, openapi_extra=None, **kwargs):
        extra = {"x-phase": "K1", "x-implementation-status": "implemented"}
        super().add_api_route(path, endpoint, openapi_extra=extra | (openapi_extra or {}), **kwargs)


router = KnowledgeRouter(tags=["Knowledge"], responses=errors | {413: {"model": Error}})


def upload_contract(model):
    return {
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file", "metadata"],
                        "additionalProperties": False,
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "metadata": {
                                "type": "string",
                                "description": f"JSON-encoded {model.__name__}",
                                "contentMediaType": "application/json",
                                "contentSchema": model.model_json_schema(),
                            },
                        },
                    }
                }
            },
        }
    }


def parse_metadata(model, data):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise AppError(422, "VALIDATION_ERROR", "Invalid upload metadata") from exc


@router.post(
    "/api/v1/stores/{store_id}/documents",
    status_code=201,
    response_model=Document,
    operation_id="create_knowledge_document",
    openapi_extra=upload_contract(UploadMetadata),
)
async def create(request: Request, principal: User, store_id: Id, key: Key):
    """Upload original + UploadMetadata JSON. Returns UPLOADED/NOT_INDEXED; indexing is K2."""
    require_role(principal, "operator")
    async with request.app.state.db.session() as session:
        await repo.store_scope(session, principal, store_id)
    upload = await receive_upload(request)
    body = parse_metadata(UploadMetadata, upload.metadata)
    async with request.app.state.db.session() as session, session.begin():
        return await repo.create(session, principal, store_id, body, upload, key)


@router.get(
    "/api/v1/stores/{store_id}/documents",
    response_model=DocumentList,
    operation_id="list_knowledge_documents",
)
async def listing(
    request: Request,
    principal: User,
    store_id: Id,
    category: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    supplier_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    sku_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    status: Status = "active",
    q: Annotated[str, Query(max_length=300)] = "",
    cursor: Cursor = None,
    limit: Limit = 20,
):
    """Metadata filters only; q matches literal title substrings. Full-text search is K2."""
    async with request.app.state.db.session() as session:
        return await repo.listing(
            session,
            principal,
            store_id,
            category=category,
            supplier_id=supplier_id,
            sku_id=sku_id,
            status=status,
            q=q,
            cursor=cursor,
            limit=limit,
        )


@router.get(
    "/api/v1/documents/{document_id}",
    response_model=Document,
    operation_id="get_knowledge_document",
)
async def detail(request: Request, principal: User, document_id: Id):
    async with request.app.state.db.session() as session:
        return repo.document(await repo.visible(session, principal, document_id))


@router.patch(
    "/api/v1/documents/{document_id}",
    response_model=Document,
    operation_id="patch_knowledge_document",
)
async def patch(request: Request, principal: User, document_id: Id, body: MetadataPatch, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        return await repo.patch(session, principal, document_id, body, key)


@router.post(
    "/api/v1/documents/{document_id}/versions",
    status_code=201,
    response_model=Document,
    operation_id="append_knowledge_version",
    openapi_extra=upload_contract(AppendMetadata),
)
async def append(request: Request, principal: User, document_id: Id, key: Key):
    """Upload original + AppendMetadata JSON (expected_metadata_version and validity)."""
    require_role(principal, "operator")
    async with request.app.state.db.session() as session:
        await repo.visible(session, principal, document_id, write=True)
    upload = await receive_upload(request)
    body = parse_metadata(AppendMetadata, upload.metadata)
    async with request.app.state.db.session() as session, session.begin():
        return await repo.append(session, principal, document_id, body, upload, key)


@router.get(
    "/api/v1/documents/{document_id}/versions",
    response_model=VersionList,
    operation_id="list_knowledge_versions",
)
async def versions(
    request: Request, principal: User, document_id: Id, cursor: Cursor = None, limit: Limit = 20
):
    async with request.app.state.db.session() as session:
        return await repo.versions(session, principal, document_id, cursor, limit)


@router.get(
    "/api/v1/documents/{document_id}/versions/{version_id}",
    response_model=Version,
    operation_id="get_knowledge_version",
)
async def version(request: Request, principal: User, document_id: Id, version_id: Id):
    async with request.app.state.db.session() as session:
        return Version.model_validate(
            await repo.version(session, principal, document_id, version_id)
        )


@router.get(
    "/api/v1/documents/{document_id}/versions/{version_id}/content",
    response_class=FileResponse,
    operation_id="download_knowledge_original",
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
async def content(
    request: Request,
    principal: User,
    document_id: Id,
    version_id: Id,
    representation: Literal["original"] = "original",
):
    """Authenticated attachment only. Parsed representations and activation are K2."""
    async with request.app.state.db.session() as session:
        row = await repo.version(session, principal, document_id, version_id)
    path = original_path(request.app.state.settings.knowledge_storage_root, row.raw_key)
    if not path.is_file():
        raise AppError(
            503, "ORIGINAL_UNAVAILABLE", "Original storage is unavailable", retryable=True
        )
    return FileResponse(
        path,
        media_type=row.mime_type,
        filename=row.original_name,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.post(
    "/api/v1/documents/{document_id}/control",
    response_model=Document,
    operation_id="control_knowledge_document",
)
async def control(request: Request, principal: User, document_id: Id, body: Control, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        return await repo.control(session, principal, document_id, body, key)
