"""Persistent owner-scoped work intake, independent of replenishment and model runtime."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0013_work_intake"
down_revision = "0012_agent_progress"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_items",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("result", pg.JSONB(), nullable=True),
        sa.Column("mission_id", sa.String(), sa.ForeignKey("missions.id"), nullable=True),
        sa.Column("mission_request", pg.JSONB(), nullable=True),
        sa.Column("canonical_id", sa.String(128), sa.ForeignKey("work_items.id"), nullable=True),
        sa.Column("demonstration", sa.Boolean(), nullable=False),
        sa.Column("processing_hash", sa.String(64), nullable=True),
        sa.Column("processing_owner", sa.String(128), nullable=True),
        sa.Column("processing_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )
    op.create_index("ix_work_items_store_id", "work_items", ["store_id"])
    op.create_index(
        "uq_work_mission_owner", "work_items", ["principal_id", "mission_id"], unique=True
    )
    op.create_table(
        "work_messages",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("item_id", sa.String(128), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("demonstration", sa.Boolean(), nullable=False),
        sa.Column("result", pg.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )
    op.create_index("ix_work_messages_item_id", "work_messages", ["item_id"])


def downgrade():
    op.drop_table("work_messages")
    op.drop_table("work_items")
