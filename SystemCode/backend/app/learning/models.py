from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SCHEMA = "agent_data"


class LearningPolicyRow(Base):
    __tablename__ = "learning_policies"
    __table_args__ = (
        UniqueConstraint("principal_id", "store_id", "source_domain"),
        {"schema": SCHEMA},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(128))
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    source_domain: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(16), default="off")
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_concepts: Mapped[list] = mapped_column(JSONB, default=list)
    consumed: Mapped[list] = mapped_column(JSONB, default=list)


class LearningOutbox(Base):
    __tablename__ = "learning_outbox"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(ForeignKey("agent_data.learning_policies.id"), index=True)
    policy_version: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict] = mapped_column(JSONB)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EpisodeRow(Base):
    __tablename__ = "operation_episodes"
    __table_args__ = (UniqueConstraint("scope_id", "intent_key"), {"schema": SCHEMA})
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(ForeignKey("agent_data.learning_policies.id"), index=True)
    intent_key: Mapped[str] = mapped_column(String(256))
    task_family: Mapped[str] = mapped_column(String(80))
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    outcome_revision: Mapped[int] = mapped_column(Integer, default=0)


class EpisodeEventRow(Base):
    __tablename__ = "episode_events"
    __table_args__ = {"schema": SCHEMA}
    event_id: Mapped[str] = mapped_column(
        ForeignKey("agent_data.learning_outbox.id"), primary_key=True
    )
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("agent_data.operation_episodes.id"), index=True
    )


class OutcomeRow(Base):
    __tablename__ = "episode_outcomes"
    __table_args__ = {"schema": SCHEMA}
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("agent_data.operation_episodes.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    document: Mapped[dict] = mapped_column(JSONB)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssetRow(Base):
    __tablename__ = "learning_assets"
    __table_args__ = (UniqueConstraint("scope_id", "concept_key"), {"schema": SCHEMA})
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(ForeignKey("agent_data.learning_policies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    task_family: Mapped[str] = mapped_column(String(80))
    concept_key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    latest_revision: Mapped[int] = mapped_column(Integer, default=1)
    active_revision: Mapped[int | None] = mapped_column(Integer)


class AssetRevisionRow(Base):
    __tablename__ = "learning_asset_revisions"
    __table_args__ = {"schema": SCHEMA}
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("agent_data.learning_assets.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    spec: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    evidence_digest: Mapped[str] = mapped_column(String(64))
    evidence_ids: Mapped[list] = mapped_column(JSONB)
    evaluation_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceLinkRow(Base):
    __tablename__ = "learning_evidence_links"
    __table_args__ = {"schema": SCHEMA}
    event_id: Mapped[str] = mapped_column(
        ForeignKey("agent_data.learning_outbox.id"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("agent_data.learning_assets.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    relation: Mapped[str] = mapped_column(String(24), default="support")


class EvaluationRow(Base):
    __tablename__ = "learning_evaluations"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("agent_data.learning_assets.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict] = mapped_column(JSONB)
    decision: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApplicationRow(Base):
    __tablename__ = "learning_applications"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(ForeignKey("agent_data.learning_policies.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("agent_data.learning_assets.id"))
    revision: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[str] = mapped_column(String(128))
    stage: Mapped[str] = mapped_column(String(24))
    outcome: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BatchRow(Base):
    __tablename__ = "learning_batches"
    __table_args__ = {"schema": SCHEMA}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_id: Mapped[str] = mapped_column(ForeignKey("agent_data.learning_policies.id"), index=True)
    policy_version: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[dict] = mapped_column(JSONB)
    evidence_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED")
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
