"""business state"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_business_state"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "command_receipts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_command_receipts")),
    )
    op.create_table(
        "stores",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("scenario_run_id", sa.String(length=128), nullable=False),
        sa.Column("initial_hash", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("cash_minor", sa.BigInteger(), nullable=False),
        sa.Column("reserved_cash_minor", sa.BigInteger(), nullable=False),
        sa.Column("receivables_minor", sa.BigInteger(), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("simulation_time", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "cash_minor >= reserved_cash_minor AND reserved_cash_minor >= 0 AND "
            "receivables_minor >= 0 AND state_version >= 1 AND currency = 'CNY'",
            name=op.f("ck_stores_state_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stores")),
        sa.UniqueConstraint("scenario_run_id", name=op.f("uq_stores_scenario_run_id")),
    )
    op.create_table(
        "forecasts",
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("sku_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_sequence", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
        ),
        sa.PrimaryKeyConstraint("store_id", "sku_id", "version", name=op.f("pk_forecasts")),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("effect_type", sa.String(length=32), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=True),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
    )
    op.create_index(
        op.f("ix_ledger_entries_store_id"), "ledger_entries", ["store_id"], unique=False
    )
    op.create_table(
        "products",
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("sku_id", sa.String(length=128), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
        ),
        sa.PrimaryKeyConstraint("store_id", "sku_id", name=op.f("pk_products")),
    )
    op.create_table(
        "source_cursors",
        sa.Column("scenario_run_id", sa.String(length=128), nullable=False),
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=128), nullable=True),
        sa.CheckConstraint("last_sequence >= 0", name=op.f("ck_source_cursors_sequence_valid")),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
        ),
        sa.PrimaryKeyConstraint("scenario_run_id", name=op.f("pk_source_cursors")),
        sa.UniqueConstraint("store_id", name=op.f("uq_source_cursors_store_id")),
    )
    op.create_table(
        "stocks",
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("sku_id", sa.String(length=128), nullable=False),
        sa.Column("on_hand", sa.BigInteger(), nullable=False),
        sa.Column("in_transit", sa.BigInteger(), nullable=False),
        sa.Column("remaining_demand", sa.BigInteger(), nullable=True),
        sa.Column("forecast_version", sa.String(), nullable=True),
        sa.CheckConstraint(
            "on_hand >= 0 AND in_transit >= 0 AND remaining_demand >= 0",
            name=op.f("ck_stocks_quantities_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
        ),
        sa.PrimaryKeyConstraint("store_id", "sku_id", name=op.f("pk_stocks")),
    )
    op.create_table(
        "supplier_offers",
        sa.Column("store_id", sa.String(length=128), nullable=False),
        sa.Column("sku_id", sa.String(length=128), nullable=False),
        sa.Column("supplier_id", sa.String(length=128), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
        ),
        sa.PrimaryKeyConstraint(
            "store_id", "sku_id", "supplier_id", name=op.f("pk_supplier_offers")
        ),
    )
    op.create_table(
        "business_events",
        sa.Column("scenario_run_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("sequence >= 1", name=op.f("ck_business_events_sequence_valid")),
        sa.ForeignKeyConstraint(
            ["scenario_run_id"],
            ["source_cursors.scenario_run_id"],
        ),
        sa.PrimaryKeyConstraint("scenario_run_id", "event_id", name=op.f("pk_business_events")),
        sa.UniqueConstraint(
            "scenario_run_id", "sequence", name=op.f("uq_business_events_scenario_run_id")
        ),
    )


def downgrade():
    op.drop_table("business_events")
    op.drop_table("supplier_offers")
    op.drop_table("stocks")
    op.drop_table("source_cursors")
    op.drop_table("products")
    op.drop_index(op.f("ix_ledger_entries_store_id"), table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("forecasts")
    op.drop_table("stores")
    op.drop_table("command_receipts")
