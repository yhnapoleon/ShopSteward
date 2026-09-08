"""Versioned service contracts shared without database or parser dependencies."""

import hashlib
import math
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Id = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OriginalRef(DTO):
    version_id: Id
    sha256: Sha
    mime: str = Field(min_length=1, max_length=128)
    storage_key: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=1, le=20 * 1024 * 1024)


class EvidenceLocator(DTO):
    kind: Literal["page", "paragraph", "table", "cells"]
    page: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list, max_length=30)
    paragraph_range: tuple[int, int] | None = None
    table: int | None = Field(default=None, ge=1)
    sheet: str | None = None
    cell_range: str | None = None

    @model_validator(mode="after")
    def location(self):
        if self.kind == "page" and self.page is None:
            raise ValueError("page locator requires page")
        if self.kind == "paragraph" and self.paragraph_range is None:
            raise ValueError("paragraph locator requires range")
        if self.paragraph_range and not 1 <= self.paragraph_range[0] <= self.paragraph_range[1]:
            raise ValueError("invalid paragraph range")
        if self.kind == "cells" and not (self.sheet and self.cell_range):
            raise ValueError("cell locator requires sheet and range")
        if self.kind == "table" and self.table is None:
            raise ValueError("table locator requires table ordinal")
        return self


class AllowedVersion(DTO):
    version_id: Id
    generation_id: Id
    metadata_revision: int = Field(ge=1)


class SearchScope(DTO):
    principal_ref: Id
    store_id: Id
    as_of: AwareDatetime
    expires_at: AwareDatetime
    allowed_versions: list[AllowedVersion] = Field(default_factory=list, max_length=10000)


class SearchRequest(DTO):
    query: str = Field(min_length=1, max_length=4000)
    scope: SearchScope
    profile_id: Id = "lexical-v1"
    deadline_ms: int = Field(default=8000, ge=1, le=8000)
    limit: int = Field(default=6, ge=1, le=6)
    entity_ids: list[Id] = Field(default_factory=list, max_length=100)
    relation_context: dict[str, str | bool | int | float] = Field(
        default_factory=dict, max_length=30
    )


class RelationEdge(DTO):
    id: Id
    subject: str = Field(min_length=1, max_length=256)
    predicate: Id
    object: str = Field(min_length=1, max_length=256)
    confirmed: Literal[True]
    conditions: dict = Field(default_factory=dict, max_length=30)
    evidence_chunk_ids: list[Id] = Field(min_length=1, max_length=20)
    version_id: Id
    generation_id: Id
    metadata_revision: int = Field(ge=1)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None


class RelationPath(DTO):
    edge_ids: list[Id] = Field(min_length=1, max_length=3)
    nodes: list[str] = Field(min_length=2, max_length=4)
    edges: list[RelationEdge] = Field(min_length=1, max_length=3)
    evidence_chunk_ids: list[Id] = Field(min_length=1, max_length=60)
    coverage: Literal["known_paths_only"] = "known_paths_only"
    truncated: bool = False

    @model_validator(mode="after")
    def connected(self):
        if self.edge_ids != [edge.id for edge in self.edges]:
            raise ValueError("relation path edge identities differ")
        if self.nodes != [self.edges[0].subject] + [edge.object for edge in self.edges]:
            raise ValueError("relation path nodes differ")
        if any(a.object != b.subject for a, b in zip(self.edges, self.edges[1:], strict=False)):
            raise ValueError("relation path is not connected")
        if set(self.evidence_chunk_ids) != {c for e in self.edges for c in e.evidence_chunk_ids}:
            raise ValueError("relation path evidence differs")
        return self


class Candidate(DTO):
    document_id: Id
    version_id: Id
    generation_id: Id
    chunk_id: Id
    metadata_revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=24000)
    title: str = Field(min_length=1, max_length=300)
    store_id: Id
    locator: EvidenceLocator
    content_sha256: Sha
    original_sha256: Sha | None = None
    source_url: str | None = None
    source_kind: str = "document"
    synthetic: bool = False
    jurisdiction: str | None = None
    entity_refs: list[str] = Field(default_factory=list)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    section_path: list[str] = Field(default_factory=list)
    retrieval_channels: list[str] = Field(default_factory=list)
    ranks: dict[str, int] = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)
    fusion_score: float | None = None
    rerank_score: float | None = None
    parsing_status: Literal["COMPLETE", "PARTIAL"] = "COMPLETE"
    ocr_status: Literal["NOT_REQUIRED", "REQUIRED", "NOT_RUN", "COMPLETE"] = "NOT_REQUIRED"
    truncated: bool = False
    conflict_group: str | None = None
    relation_paths: list[RelationPath] = Field(default_factory=list, max_length=20)
    context_chunk_ids: list[Id] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def text_identity(self):
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValueError("candidate text hash mismatch")
        return self


class SearchResponse(DTO):
    request_id: Id
    retrieval_profile: str
    embedding_profile: str | None = None
    rerank_profile: str | None = None
    index_watermark: dict[str, int] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list, max_length=20)


class EvidenceRequest(DTO):
    scope: SearchScope
    chunk_ids: list[Id] = Field(min_length=1, max_length=20)


class Provenance(DTO):
    source_kind: str = Field(default="document", max_length=64)
    source_family_id: str | None = Field(default=None, max_length=128)
    scenario_family_id: str | None = Field(default=None, max_length=128)
    source_url: str | None = Field(default=None, max_length=2000)
    publisher: str | None = Field(default=None, max_length=300)
    jurisdiction: str | None = Field(default=None, max_length=100)
    synthetic: bool = False


class Projection(DTO):
    document_id: Id
    version_id: Id
    store_id: Id
    metadata_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    status: Literal["active", "archived"] = "active"
    entity_refs: list[str] = Field(default_factory=list, max_length=200)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def validity(self):
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("invalid validity interval")
        return self


class IngestionRequest(DTO):
    original: OriginalRef
    projection: Projection
    profile_id: Id = "lexical-v1"

    @model_validator(mode="after")
    def same_version(self):
        if self.original.version_id != self.projection.version_id:
            raise ValueError("original and projection version mismatch")
        return self


class IngestionReceipt(DTO):
    job_id: Id
    state: Literal["PENDING", "RUNNING", "RETRY_WAIT", "SUCCEEDED", "FAILED"]
    generation_id: Id
    manifest_hash: Sha | None = None
    attempt: int = 0
    error: str | None = None


class EmbeddingProfile(DTO):
    provider: str
    model: str
    revision: str | None = None
    dimensions: int = Field(ge=1, le=8192)
    query_instruction: str = ""
    document_instruction: str = ""
    normalize: bool = True
    max_input_chars: int = Field(default=12000, ge=1, le=100000)


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int) -> None:
    if len(vectors) != count:
        raise ValueError("embedding count mismatch")
    for vector in vectors:
        if len(vector) != dimensions or not all(math.isfinite(v) for v in vector):
            raise ValueError("embedding dimensions or values invalid")
        if not any(vector):
            raise ValueError("zero embedding vector")
