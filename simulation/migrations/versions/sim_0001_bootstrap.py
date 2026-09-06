import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "sim_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("command_key", sa.String(128), nullable=False, unique=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("initial_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("world", postgresql.JSONB(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("step_index", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("last_sequence >= 0 AND step_index >= 0"),
    )
    op.create_table(
        "simulation_events",
        sa.Column("run_id", sa.String(128), sa.ForeignKey("simulation_runs.id"), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), primary_key=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("run_id", "event_id"),
        sa.CheckConstraint("sequence >= 1"),
    )


def downgrade():
    op.drop_table("simulation_events")
    op.drop_table("simulation_runs")
