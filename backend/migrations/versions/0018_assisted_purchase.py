"""Purchases the owner sends to the supplier by hand: the order message and the pasted reply."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0018_assisted_purchase"
down_revision = "0017_cases_quotations_merge"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "actions",
        sa.Column("channel", sa.String(16), nullable=False, server_default="simulator"),
    )
    op.add_column("actions", sa.Column("order_message", pg.JSONB()))
    op.add_column("actions", sa.Column("supplier_reply", pg.JSONB()))
    op.create_check_constraint(
        op.f("ck_actions_channel"), "actions", "channel IN ('simulator','assisted')"
    )


def downgrade():
    op.drop_constraint(op.f("ck_actions_channel"), "actions")
    op.drop_column("actions", "supplier_reply")
    op.drop_column("actions", "order_message")
    op.drop_column("actions", "channel")
