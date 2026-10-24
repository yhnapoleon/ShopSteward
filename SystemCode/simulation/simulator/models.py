from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    command_key: Mapped[str] = mapped_column(String(128), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    initial_snapshot: Mapped[dict] = mapped_column(JSONB)
    configuration: Mapped[dict] = mapped_column(JSONB, server_default='{"scenario":"SC01"}')
    world: Mapped[dict] = mapped_column(JSONB)
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    step_index: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (CheckConstraint("last_sequence >= 0 AND step_index >= 0"),)


class EventRow(Base):
    __tablename__ = "simulation_events"
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128))
    document: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("run_id", "event_id"), CheckConstraint("sequence >= 1"))


class Purchase(Base):
    __tablename__ = "simulation_purchases"
    action_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict] = mapped_column(JSONB)
    receipt: Mapped[dict] = mapped_column(JSONB)
    accepted_quantity: Mapped[int] = mapped_column(BigInteger)
    received_quantity: Mapped[int] = mapped_column(BigInteger)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "accepted_quantity >= 0 AND received_quantity >= 0 "
            "AND received_quantity <= accepted_quantity"
        ),
    )


class CommandRecord(Base):
    __tablename__ = "simulation_commands"
    principal: Mapped[str] = mapped_column(String(128), primary_key=True)
    operation: Mapped[str] = mapped_column(String(128), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"))
    response: Mapped[dict] = mapped_column(JSONB)
