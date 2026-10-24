"""Business authority and durable transport state; no derived chunk storage."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class VersionProvenance(Base):
    __tablename__ = "knowledge_version_provenance"
    version_id: Mapped[str] = mapped_column(ForeignKey("knowledge_versions.id"), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(64))
    source_family_id: Mapped[str | None] = mapped_column(String(128))
    scenario_family_id: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    publisher: Mapped[str | None] = mapped_column(String(300))
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    synthetic: Mapped[bool] = mapped_column(Boolean)
    original_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint("original_sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),)


class DeliveryOutbox(Base):
    __tablename__ = "knowledge_delivery_outbox"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128))
    version_id: Mapped[str] = mapped_column(String(128))
    metadata_revision: Mapped[int] = mapped_column(BigInteger)
    operation: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(BigInteger, default=0)
    retry_count: Mapped[int] = mapped_column(BigInteger, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[str | None] = mapped_column(String(128))
    remote_retry_key: Mapped[str | None] = mapped_column(String(64))
    generation_id: Mapped[str | None] = mapped_column(String(128))
    manifest_hash: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "version_id"],
            ["knowledge_versions.document_id", "knowledge_versions.id"],
        ),
        CheckConstraint("operation IN ('ingest','projection')", name="operation"),
        CheckConstraint(
            "state IN ('PENDING','RUNNING','RETRY_WAIT','SUCCEEDED','FAILED')", name="state"
        ),
        CheckConstraint(
            "metadata_revision >= 1 AND attempt >= 0 AND retry_count >= 0", name="counters"
        ),
        CheckConstraint(
            "(state = 'RUNNING') = (lease_token IS NOT NULL "
            "AND lease_until IS NOT NULL AND lease_owner IS NOT NULL)",
            name="lease",
        ),
        Index("ix_knowledge_delivery_claim", "state", "next_attempt_at"),
    )


class Publication(Base):
    __tablename__ = "knowledge_publications"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128))
    version_id: Mapped[str] = mapped_column(String(128))
    generation_id: Mapped[str] = mapped_column(String(128))
    manifest_hash: Mapped[str] = mapped_column(String(64))
    metadata_revision: Mapped[int] = mapped_column(BigInteger)
    publication_revision: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "version_id"],
            ["knowledge_versions.document_id", "knowledge_versions.id"],
        ),
        UniqueConstraint(
            "document_id", "publication_revision", name="uq_knowledge_publication_revision"
        ),
        CheckConstraint("metadata_revision >= 1 AND publication_revision >= 1", name="revisions"),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from", name="validity"
        ),
        CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="manifest"),
        Index("ix_knowledge_publications_current", "document_id", "active"),
    )
