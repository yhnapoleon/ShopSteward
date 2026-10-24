from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertRow(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))
    sku_id: Mapped[str] = mapped_column(String(128))
    scope_key: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(String(2000))
    facts: Mapped[dict] = mapped_column(JSONB)
    state_version: Mapped[int | None] = mapped_column(BigInteger)
    related_plan_id: Mapped[str | None] = mapped_column(String(128))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(128))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def created_at(self):
        return self.first_seen_at

    __table_args__ = (
        CheckConstraint("status IN ('OPEN','ACKNOWLEDGED','RESOLVED')", name="status"),
        CheckConstraint("severity IN ('INFO','WARNING','CRITICAL')", name="severity"),
        CheckConstraint(
            "type IN ('STOCKOUT_RISK','CASH_CONSTRAINT','ACTION_EXCEPTION','DATA_STALE')",
            name="type",
        ),
        CheckConstraint("state_version IS NULL OR state_version >= 1", name="version"),
        CheckConstraint("(status='RESOLVED') = (resolved_at IS NOT NULL)", name="resolution"),
        Index(
            "uq_alerts_active_scope",
            "scope_key",
            unique=True,
            postgresql_where=text("status IN ('OPEN','ACKNOWLEDGED')"),
        ),
        Index("ix_alerts_page", "store_id", "first_seen_at", "id"),
        Index("ix_alerts_status", "store_id", "status", "last_seen_at"),
        Index("ix_alerts_mission", "mission_id"),
    )
