"""Preserve scenario mode and synthetic initialization configuration."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "sim_0003_controls"
down_revision = "sim_0002_purchases"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "simulation_runs",
        sa.Column(
            "configuration",
            postgresql.JSONB(),
            nullable=False,
            server_default='{"scenario":"SC01"}',
        ),
    )


def downgrade():
    op.drop_column("simulation_runs", "configuration")
