from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Job(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_nonnegative"),
        CheckConstraint(
            "status IN ('READY','RUNNING','SUCCEEDED','FAILED','CANCELLED','RETRY_WAIT')",
            name="status",
        ),
        CheckConstraint(
            "status <> 'RUNNING' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="running_lease",
        ),
        Index("ix_job_runs_due", "status", "available_at"),
        Index("ix_job_runs_lease", "status", "lease_until"),
        Index("ix_job_runs_mission", "mission_id", "created_at", "id"),
        Index(
            "uq_job_runs_active_check",
            "mission_id",
            unique=True,
            postgresql_where=text(
                "job_type='check_mission' AND mission_id IS NOT NULL "
                "AND status IN ('READY','RUNNING','RETRY_WAIT')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(256), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    job_type: Mapped[str] = mapped_column(String(64))
    store_id: Mapped[str | None] = mapped_column(String(128))
    mission_id: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="READY")
    trigger_source: Mapped[str] = mapped_column(String(20), default="MANUAL")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(128))
    target_state_version: Mapped[int | None] = mapped_column(Integer)
    target_mission_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    __table_args__ = (CheckConstraint("status IN ('RUNNING','STOPPED')", name="status"),)
    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
