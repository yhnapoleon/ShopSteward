"""Supplier documents, the offers read out of them, and the sourcing run kept on a Case."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0019_sourcing"
down_revision = "0018_assisted_purchase"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_documents",
        sa.Column("store_id", sa.String(128), sa.ForeignKey("stores.id"), primary_key=True),
        sa.Column("supplier_id", sa.String(128), primary_key=True),
        sa.Column("doc_id", sa.String(128), primary_key=True),
        sa.Column("supplier_name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sourced_offers",
        sa.Column("store_id", sa.String(128), sa.ForeignKey("stores.id"), primary_key=True),
        sa.Column("sku_id", sa.String(128), primary_key=True),
        sa.Column("supplier_id", sa.String(128), primary_key=True),
        sa.Column("case_id", sa.String(128), sa.ForeignKey("operations_cases.id"), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("card", pg.JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("operations_cases", sa.Column("sourcing", pg.JSONB()))


def downgrade():
    op.drop_column("operations_cases", "sourcing")
    op.drop_table("sourced_offers")
    op.drop_table("supplier_documents")
