"""Persistent, revisioned recovery cases and one-time Mission recovery context."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_operations_cases"
down_revision = "0014_forecast_work_merge"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("missions", sa.Column("planning_context", postgresql.JSONB(), nullable=True))
    op.create_table(
        "operations_cases",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("mission_id", sa.String(128), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("store_id", sa.String(128), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_revision", sa.BigInteger(), nullable=False),
        sa.Column("event_seq", sa.BigInteger(), nullable=False),
        sa.Column("proposal_id", sa.String(128)),
        sa.Column("plan_id", sa.String(128)),
        sa.Column("missing_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("expert_analysis", postgresql.JSONB()),
        sa.Column("followup_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_revision >= 1 AND event_seq >= 0", name="versions"),
    )
    op.create_index(
        "ix_operations_cases_owner", "operations_cases", ["owner_id", "store_id", "created_at"]
    )
    op.create_table(
        "case_revisions",
        sa.Column(
            "case_id", sa.String(128), sa.ForeignKey("operations_cases.id"), primary_key=True
        ),
        sa.Column("revision", sa.BigInteger(), primary_key=True),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB()),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "recovery_proposals",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("case_id", sa.String(128), sa.ForeignKey("operations_cases.id"), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_recovery_proposals_case_id", "recovery_proposals", ["case_id"])
    op.create_table(
        "case_events",
        sa.Column(
            "case_id", sa.String(128), sa.ForeignKey("operations_cases.id"), primary_key=True
        ),
        sa.Column("seq", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for table in ("case_events", "recovery_proposals", "case_revisions", "operations_cases"):
        op.drop_table(table)
    op.drop_column("missions", "planning_context")
