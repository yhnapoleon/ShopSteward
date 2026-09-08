"""Durable agent progress, independent of model output text."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_agent_progress"
down_revision = "0011_knowledge_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_runs", sa.Column("progress_seq", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.create_table(
        "agent_run_events",
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("seq", sa.BigInteger(), primary_key=True),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("invocation_id", sa.String(256), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_tool_activity",
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("invocation_id", sa.String(256), primary_key=True),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("args_hash", sa.String(64), nullable=False),
        sa.Column("lease_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("references", postgresql.JSONB(), nullable=False),
    )


def downgrade():
    op.drop_table("agent_tool_activity")
    op.drop_table("agent_run_events")
    op.drop_column("agent_runs", "progress_seq")
