"""Persist purchase receipts and operation-scoped command responses."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "sim_0002_purchases"
down_revision = "sim_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "simulation_purchases",
        sa.Column("action_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("receipt", postgresql.JSONB(), nullable=False),
        sa.Column("accepted_quantity", sa.BigInteger(), nullable=False),
        sa.Column("received_quantity", sa.BigInteger(), nullable=False),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "accepted_quantity >= 0 AND received_quantity >= 0 "
            "AND received_quantity <= accepted_quantity"
        ),
    )
    op.create_index("ix_simulation_purchases_run_id", "simulation_purchases", ["run_id"])
    op.create_table(
        "simulation_commands",
        sa.Column("principal", sa.String(128), primary_key=True),
        sa.Column("operation", sa.String(128), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(128), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
    )
    # Preserve every pre-migration create key and its original response.
    op.execute(
        sa.text("""
        INSERT INTO simulation_commands (principal, operation, key, content_hash, run_id, response)
        SELECT 'backend-service', 'simulation_create_run', command_key, content_hash,
               id, initial_snapshot FROM simulation_runs
    """)
    )


def downgrade():
    op.drop_table("simulation_commands")
    op.drop_table("simulation_purchases")
