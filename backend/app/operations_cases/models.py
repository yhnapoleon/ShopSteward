from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CaseRow(Base):
    __tablename__ = "operations_cases"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    sku_id: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    current_revision: Mapped[int] = mapped_column(BigInteger)
    event_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    proposal_id: Mapped[str | None] = mapped_column(String(128))
    plan_id: Mapped[str | None] = mapped_column(String(128))
    missing_inputs: Mapped[list] = mapped_column(JSONB, default=list)
    expert_analysis: Mapped[dict | None] = mapped_column(JSONB)
    followup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_operations_cases_owner", "owner_id", "store_id", "created_at"),)


class CaseRevisionRow(Base):
    __tablename__ = "case_revisions"
    case_id: Mapped[str] = mapped_column(ForeignKey("operations_cases.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inputs: Mapped[dict] = mapped_column(JSONB)
    snapshot: Mapped[dict | None] = mapped_column(JSONB)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecoveryProposalRow(Base):
    __tablename__ = "recovery_proposals"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("operations_cases.id"), index=True)
    revision: Mapped[int] = mapped_column(BigInteger)
    document: Mapped[dict] = mapped_column(JSONB)


class CaseEventRow(Base):
    __tablename__ = "case_events"
    case_id: Mapped[str] = mapped_column(ForeignKey("operations_cases.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
