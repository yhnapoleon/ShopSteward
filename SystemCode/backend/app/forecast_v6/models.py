from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ForecastV6Input(Base):
    __tablename__ = "forecast_v6_inputs"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(String(128))
    sku_id: Mapped[str] = mapped_column(String(128))
    series_id: Mapped[str] = mapped_column(String(128))
    mode: Mapped[str] = mapped_column(String(32))
    document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["store_id", "sku_id"], ["products.store_id", "products.sku_id"]),
    )


class ForecastV6Evidence(Base):
    __tablename__ = "forecast_v6_evidence"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    input_id: Mapped[str] = mapped_column(ForeignKey("forecast_v6_inputs.id"))
    state_version: Mapped[int] = mapped_column(BigInteger)
    document: Mapped[dict] = mapped_column(JSONB)
    model: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ForecastV6Binding(Base):
    __tablename__ = "forecast_v6_bindings"
    store_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger)
    input_id: Mapped[str] = mapped_column(ForeignKey("forecast_v6_inputs.id"))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("forecast_v6_evidence.id"))
    activate_for_planning: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (
        ForeignKeyConstraint(["store_id", "sku_id"], ["products.store_id", "products.sku_id"]),
    )
