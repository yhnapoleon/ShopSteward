from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupplierDocumentRow(Base):
    """What a supplier sent, as text: a quote, a notice, its terms, a delivery record."""

    __tablename__ = "supplier_documents"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    supplier_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourcedOfferRow(Base):
    """Where a structured offer came from when a reviewer read it out of documents.

    The supplier behind it is not connected to any ordering system, so a purchase
    from it is sent by the owner.
    """

    __tablename__ = "sourced_offers"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    supplier_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("operations_cases.id"))
    run_id: Mapped[str] = mapped_column(String(128))
    card: Mapped[dict] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
