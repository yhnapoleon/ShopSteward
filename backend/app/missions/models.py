from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MissionRow(Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    sku_id: Mapped[str] = mapped_column(String(128))
    objective: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20))
    mission_version: Mapped[int] = mapped_column(BigInteger)
    policy: Mapped[dict] = mapped_column(JSONB)
    policy_version: Mapped[str] = mapped_column(String(128))
    current_plan_id: Mapped[str | None] = mapped_column(String(128))
    current_action_id: Mapped[str | None] = mapped_column(String(128))
    completion_criteria: Mapped[str] = mapped_column(String(256))
    plan_counter: Mapped[int] = mapped_column(BigInteger, default=0)
    recheck_required: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_check_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','PAUSED','COMPLETED','CANCELLED')", name="status"),
        CheckConstraint("mission_version >= 1 AND plan_counter >= 0", name="versions"),
        Index(
            "uq_missions_open_scope",
            "store_id",
            "sku_id",
            unique=True,
            postgresql_where=text("status IN ('ACTIVE','PAUSED')"),
        ),
        Index("ix_missions_page", "store_id", "created_at", "id"),
    )


class ScheduleRow(Base):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), unique=True)
    job_type: Mapped[str] = mapped_column(String(32))
    trigger: Mapped[str] = mapped_column(String(20))
    interval_seconds: Mapped[int] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(BigInteger)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "interval_seconds BETWEEN 5 AND 3600 AND version >= 1", name="valid_schedule"
        ),
    )


class PlanRow(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))
    plan_version: Mapped[int] = mapped_column(BigInteger)
    state_version: Mapped[int] = mapped_column(BigInteger)
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("mission_id", "plan_version"),
        CheckConstraint(
            "status IN ('PENDING_APPROVAL','APPROVED','REJECTED','SUPERSEDED','EXPIRED')",
            name="status",
        ),
        CheckConstraint("plan_version >= 1 AND state_version >= 1", name="versions"),
        Index("ix_plans_page", "mission_id", "created_at", "id"),
    )


class TimelineRow(Base):
    __tablename__ = "mission_timeline"
    __table_args__ = (Index("ix_mission_timeline_page", "mission_id", "created_at", "id"),)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(String(2000))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(String(128))
    references: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InboundRow(Base):
    __tablename__ = "inbound_items"
    action_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), index=True)
    ordered_qty: Mapped[int] = mapped_column(BigInteger)
    received_qty: Mapped[int] = mapped_column(BigInteger)
    expected_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "ordered_qty > 0 AND received_qty >= 0 AND received_qty <= ordered_qty",
            name="quantities",
        ),
    )
