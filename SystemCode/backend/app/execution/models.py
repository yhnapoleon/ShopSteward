from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), unique=True)
    actor_id: Mapped[str] = mapped_column(String(128))
    decision: Mapped[str] = mapped_column(String(16))
    proposal_hash: Mapped[str] = mapped_column(String(71))
    state_version: Mapped[int] = mapped_column(BigInteger)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("decision IN ('approve','reject')", name="decision"),)


class ActionRow(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), unique=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16))
    purchase_snapshot: Mapped[dict] = mapped_column(JSONB)
    request_snapshot: Mapped[dict] = mapped_column(JSONB)
    reserved_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    execution_state_version: Mapped[int | None] = mapped_column(BigInteger)
    external_order_id: Mapped[str | None] = mapped_column(String(128))
    receipt: Mapped[dict | None] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(String(128))
    manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reconcile_count: Mapped[int] = mapped_column(BigInteger, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "assisted": the owner carries the order to the supplier and the reply back.
    channel: Mapped[str] = mapped_column(
        String(16), default="simulator", server_default="simulator"
    )
    order_message: Mapped[dict | None] = mapped_column(JSONB)
    supplier_reply: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The store's simulation_time at approval and when the receipt was applied.
    submitted_business_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_business_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','EXECUTING','SUCCEEDED','FAILED','UNKNOWN','STALE','CANCELLED')",
            name="status",
        ),
        CheckConstraint("channel IN ('simulator','assisted')", name="channel"),
        CheckConstraint("reserved_minor >= 0 AND reconcile_count >= 0", name="nonnegative"),
        Index("ix_actions_recovery", "status", "next_attempt_at"),
        Index("ix_actions_mission", "mission_id"),
    )

    @property
    def quantity(self):
        return self.purchase_snapshot["quantity"]

    @property
    def amount_minor(self):
        return self.purchase_snapshot["total_minor"]

    @property
    def currency(self):
        return self.purchase_snapshot["currency"]


class EvidenceRow(Base):
    __tablename__ = "action_evidence"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), index=True)
    document: Mapped[dict] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
