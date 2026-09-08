from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator
from shopsteward_knowledge.contracts import Provenance

from app.api.schemas import DTO, Identifier

Visibility = Literal["store", "private"]
Status = Literal["active", "archived"]
EntityIds = Annotated[list[Identifier], Field(max_length=100)]


class Metadata(DTO):
    title: str = Field(min_length=1, max_length=300)
    category: str = Field(default="general", min_length=1, max_length=64)
    sku_ids: EntityIds = Field(default_factory=list)
    supplier_ids: EntityIds = Field(default_factory=list)
    visibility: Visibility = "store"

    @field_validator("title", "category")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Text must be nonblank and contain no NUL")
        return value.strip()

    @field_validator("sku_ids", "supplier_ids")
    @classmethod
    def canonical_ids(cls, value):
        if any("\x00" in identifier for identifier in value):
            raise ValueError("Invalid identifier")
        return sorted(set(value))


class Validity(DTO):
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def interval(self):
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        return self


class UploadMetadata(Metadata, Validity):
    provenance: Provenance | None = None


class AppendMetadata(Validity):
    expected_metadata_version: int = Field(ge=1)
    provenance: Provenance | None = None


class MetadataPatch(DTO):
    expected_metadata_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    sku_ids: EntityIds | None = None
    supplier_ids: EntityIds | None = None
    visibility: Visibility | None = None

    @model_validator(mode="after")
    def fields(self):
        changes = self.model_fields_set - {"expected_metadata_version"}
        if not changes or any(getattr(self, field) is None for field in changes):
            raise ValueError("Provide at least one non-null metadata field")
        return self


class Control(DTO):
    operation: Literal["archive", "restore"]
    expected_metadata_version: int = Field(ge=1)


class Document(Metadata):
    id: Identifier
    store_id: Identifier
    owner_principal_id: Identifier
    metadata_version: int
    evidence_revision: int = Field(ge=1)
    status: Status
    latest_version_id: Identifier | None
    ingestion_status: Literal["UPLOADED"]
    indexing_status: Literal["NOT_INDEXED", "QUEUED", "INDEXING", "READY", "PARTIAL", "FAILED"]
    publication_revision: int = 0
    requires_republication: bool = False
    publications: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def legacy_receipt_revision(cls, value):
        # Persisted K1 command receipts predate the separate evidence counter.
        if isinstance(value, dict) and "evidence_revision" not in value:
            return {**value, "evidence_revision": value.get("metadata_version")}
        return value


class Version(Validity):
    provenance: Provenance | None = None
    id: Identifier
    document_id: Identifier
    version_no: int
    original_name: str
    mime_type: str
    content_sha256: str
    size_bytes: int
    created_by: Identifier
    created_at: datetime
    ingestion_status: Literal["UPLOADED"] = "UPLOADED"
    indexing_status: Literal["NOT_INDEXED"] = "NOT_INDEXED"


class DocumentList(DTO):
    items: list[Document]
    next_cursor: str | None


class VersionList(DTO):
    items: list[Version]
    next_cursor: str | None


class IndexRequest(DTO):
    profile_id: Identifier = "lexical-v1"


class IndexProgress(DTO):
    request_id: Identifier
    document_id: Identifier
    version_id: Identifier
    metadata_revision: int = Field(ge=1)
    state: Literal["PENDING", "RUNNING", "RETRY_WAIT", "SUCCEEDED", "FAILED"]
    attempt: int = Field(ge=0)
    job_id: Identifier | None
    generation_id: Identifier | None
    manifest_hash: str | None
    error: str | None


class PublicationResult(DTO):
    document_id: Identifier
    version_id: Identifier
    generation_id: Identifier
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_revision: int = Field(ge=1)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None


class Activation(Validity):
    version_id: Identifier
    generation_id: Identifier
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_revision: int = Field(ge=0)
    replace_version_ids: list[Identifier] = Field(default_factory=list, max_length=100)
