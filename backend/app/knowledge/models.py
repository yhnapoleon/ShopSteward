from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    owner_principal_id: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(64))
    sku_ids: Mapped[list] = mapped_column(JSONB)
    supplier_ids: Mapped[list] = mapped_column(JSONB)
    visibility: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    metadata_version: Mapped[int] = mapped_column(BigInteger)
    latest_version_id: Mapped[str | None] = mapped_column(String(128))
    ingestion_status: Mapped[str] = mapped_column(String(16))
    indexing_status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("visibility IN ('store','private')", name="visibility"),
        CheckConstraint("status IN ('active','archived')", name="status"),
        CheckConstraint("metadata_version >= 1", name="metadata_version"),
        CheckConstraint("ingestion_status = 'UPLOADED'", name="ingestion_status"),
        CheckConstraint("indexing_status = 'NOT_INDEXED'", name="indexing_status"),
        ForeignKeyConstraint(
            ["id", "latest_version_id"],
            ["knowledge_versions.document_id", "knowledge_versions.id"],
            name="fk_knowledge_latest_version",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_knowledge_documents_page", "store_id", "status", "created_at", "id"),
        Index("ix_knowledge_documents_skus", "sku_ids", postgresql_using="gin"),
        Index("ix_knowledge_documents_suppliers", "supplier_ids", postgresql_using="gin"),
    )


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"))
    version_no: Mapped[int] = mapped_column(BigInteger)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    content_sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    raw_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_knowledge_version_number"),
        UniqueConstraint("document_id", "id", name="uq_knowledge_version_document_id"),
        CheckConstraint("version_no >= 1", name="version_no"),
        CheckConstraint("size_bytes BETWEEN 1 AND 20971520", name="size_bytes"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        CheckConstraint("raw_key ~ '^[0-9a-f]{32}[.]raw$'", name="raw_key"),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from", name="validity"
        ),
    )
