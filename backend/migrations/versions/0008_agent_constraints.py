"""Separate temporary planning constraints from authoritative cash policy."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_agent_constraints"
down_revision = "0007_agent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "missions",
        sa.Column("task_constraints", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade():
    op.drop_column("missions", "task_constraints")
