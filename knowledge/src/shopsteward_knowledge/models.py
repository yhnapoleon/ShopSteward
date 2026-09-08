"""Knowledge-owned PostgreSQL records. No business-database foreign keys."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectionRecord(Base):
    __tablename__ = "knowledge_projections"
    version_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metadata_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("metadata_revision >= 1"),)


class Original(Base):
    __tablename__ = "knowledge_originals"
    version_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (CheckConstraint("size_bytes > 0"),)


class IndexGeneration(Base):
    __tablename__ = "knowledge_index_generations"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("knowledge_originals.version_id"))
    profile_id: Mapped[str] = mapped_column(String(128))
    metadata_revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="BUILDING")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    manifest_hash: Mapped[str | None] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("state IN ('BUILDING', 'READY', 'FAILED')"),
        CheckConstraint("chunk_count >= 0"),
        CheckConstraint("state != 'READY' OR (chunk_count > 0 AND manifest_hash IS NOT NULL)"),
        Index("ix_knowledge_generation_version", "version_id", "metadata_revision"),
    )


class Job(Base):
    __tablename__ = "knowledge_jobs"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generation_id: Mapped[str] = mapped_column(ForeignKey("knowledge_index_generations.id"))
    state: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    attempt_limit: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    total_attempt_limit: Mapped[int] = mapped_column(Integer, default=15, server_default="15")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("state IN ('PENDING', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', 'FAILED')"),
        CheckConstraint("attempt >= 0"),
        CheckConstraint(
            "attempt_limit > 0 AND total_attempt_limit >= attempt_limit",
            name="ck_knowledge_job_attempt_limits",
        ),
        Index("ix_knowledge_jobs_claim", "state", "next_attempt_at", "lease_until"),
    )


class RetryCommand(Base):
    __tablename__ = "knowledge_job_retries"
    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("knowledge_jobs.id"), nullable=False)
    receipt: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "knowledge_chunks"
    generation_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_index_generations.id"), primary_key=True
    )
    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (Index("ix_knowledge_chunks_scope", "store_id", "version_id"),)


class Relation(Base):
    __tablename__ = "knowledge_relations"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    generation_id: Mapped[str] = mapped_column(ForeignKey("knowledge_index_generations.id"))
    version_id: Mapped[str] = mapped_column(String(128))
    store_id: Mapped[str] = mapped_column(String(128))
    metadata_revision: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(256))
    predicate: Mapped[str] = mapped_column(String(128))
    object: Mapped[str] = mapped_column(String(256))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_knowledge_relations_scope", "store_id", "generation_id", "subject", "predicate"),
        CheckConstraint("valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from"),
    )
