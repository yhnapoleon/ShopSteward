from typing import Literal

from pydantic import Field

from app.api.schemas import DTO, Identifier


class SupplierDocument(DTO):
    doc_id: Identifier
    kind: Literal["quote", "notice", "terms", "history", "other"]
    text: str = Field(min_length=1, max_length=20000)


class SupplierDocuments(DTO):
    supplier_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    documents: list[SupplierDocument]
    # True when a system the store is connected to already supplies this supplier's offer.
    connected: bool = False


class SupplierDocumentSet(DTO):
    store_id: Identifier
    suppliers: list[SupplierDocuments]


class SupplierDocumentsUpdate(DTO):
    """Replaces everything on file for one supplier; an empty list removes the supplier."""

    supplier_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    documents: list[SupplierDocument] = Field(max_length=12)


class SampleDocuments(DTO):
    sku_id: Identifier
    district: str = Field(default="滨江区", min_length=1, max_length=64)


class BundleChange(DTO):
    component: str
    before: str
    after: str


class TextBundleEntry(DTO):
    bundle_id: str
    revision: str
    parent_revision: str | None
    content_hash: str
    origin: str | None
    stage: str | None
    dataset: str | None
    task_model: str | None
    reflection_model: str | None
    seed: int | None
    metric_calls: int | None
    changes: list[BundleChange]
    gate: dict | None
    # Which product steps run on this revision under the current configuration.
    enabled_for: list[str]


class TextBundleList(DTO):
    items: list[TextBundleEntry]
