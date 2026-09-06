from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scenario_run_id: Mapped[str] = mapped_column(String(128), unique=True)
    initial_hash: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3))
    cash_minor: Mapped[int] = mapped_column(BigInteger)
    reserved_cash_minor: Mapped[int] = mapped_column(BigInteger)
    receivables_minor: Mapped[int] = mapped_column(BigInteger)
    state_version: Mapped[int] = mapped_column(BigInteger)
    active_action_id: Mapped[str | None] = mapped_column(String(128))
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    simulation_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "cash_minor >= reserved_cash_minor AND reserved_cash_minor >= 0 AND "
            "receivables_minor >= 0 AND state_version >= 1 AND currency = 'CNY'",
            name="state_valid",
        ),
    )


class ProductRow(Base):
    __tablename__ = "products"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document: Mapped[dict] = mapped_column(JSONB)


class OfferRow(Base):
    __tablename__ = "supplier_offers"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    supplier_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document: Mapped[dict] = mapped_column(JSONB)


class StockRow(Base):
    __tablename__ = "stocks"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    on_hand: Mapped[int] = mapped_column(BigInteger)
    in_transit: Mapped[int] = mapped_column(BigInteger)
    remaining_demand: Mapped[int | None] = mapped_column(BigInteger)
    forecast_version: Mapped[str | None] = mapped_column(String)
    __table_args__ = (
        CheckConstraint(
            "on_hand >= 0 AND in_transit >= 0 AND remaining_demand >= 0", name="quantities_valid"
        ),
    )


class ForecastRow(Base):
    __tablename__ = "forecasts"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String, primary_key=True)
    document: Mapped[dict] = mapped_column(JSONB)
    source_sequence: Mapped[int] = mapped_column(BigInteger)


class SourceCursor(Base):
    __tablename__ = "source_cursors"
    scenario_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), unique=True)
    source: Mapped[str] = mapped_column(String(64))
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (CheckConstraint("last_sequence >= 0", name="sequence_valid"),)


class EventRow(Base):
    __tablename__ = "business_events"
    scenario_run_id: Mapped[str] = mapped_column(
        ForeignKey("source_cursors.scenario_run_id"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("scenario_run_id", "sequence"),
        CheckConstraint("sequence >= 1", name="sequence_valid"),
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), index=True)
    effect_type: Mapped[str] = mapped_column(String(32))
    source_event_id: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(BigInteger)
    document: Mapped[dict] = mapped_column(JSONB)


class Command(Base):
    __tablename__ = "command_receipts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
