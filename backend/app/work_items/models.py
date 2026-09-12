from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkItem(Base):
    __tablename__ = "work_items"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), index=True)
    principal_id: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default="RECEIVED")
    version: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str] = mapped_column(Text, default="")
    question: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"))
    mission_request: Mapped[dict | None] = mapped_column(JSONB)
    canonical_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id"))
    demonstration: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_hash: Mapped[str | None] = mapped_column(String(64))
    processing_owner: Mapped[str | None] = mapped_column(String(128))
    processing_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    __table_args__ = (Index("uq_work_mission_owner", "principal_id", "mission_id", unique=True),)


class WorkMessageRow(Base):
    __tablename__ = "work_messages"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    demonstration: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
