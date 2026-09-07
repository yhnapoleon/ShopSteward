from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

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
    pass


class AppendMetadata(Validity):
    expected_metadata_version: int = Field(ge=1)


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
    status: Status
    latest_version_id: Identifier | None
    ingestion_status: Literal["UPLOADED"]
    indexing_status: Literal["NOT_INDEXED"]
    created_at: datetime
    updated_at: datetime


class Version(Validity):
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
