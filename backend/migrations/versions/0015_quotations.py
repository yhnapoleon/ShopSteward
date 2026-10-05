"""Immutable owner-scoped quotation files and deterministic calculation versions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0015_quotations"
down_revision = "0014_forecast_work_merge"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quotation_files",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("work_id", sa.String(128), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index("ix_quotation_files_work_id", "quotation_files", ["work_id"])
    op.create_table(
        "quotation_results",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("work_id", sa.String(128), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("file_id", sa.String(128), sa.ForeignKey("quotation_files.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.UniqueConstraint("file_id", "version"),
    )
    op.create_index("ix_quotation_results_work_id", "quotation_results", ["work_id"])
    op.create_index("ix_quotation_results_file_id", "quotation_results", ["file_id"])


def downgrade():
    op.drop_table("quotation_results")
    op.drop_table("quotation_files")
