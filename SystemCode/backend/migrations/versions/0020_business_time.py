"""The store's business clock at a timeline entry, a purchase's submission and its receipt."""

import sqlalchemy as sa
from alembic import op

revision = "0020_business_time"
down_revision = "0019_sourcing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mission_timeline", sa.Column("business_time", sa.DateTime(timezone=True)))
    op.add_column("actions", sa.Column("submitted_business_time", sa.DateTime(timezone=True)))
    op.add_column("actions", sa.Column("receipt_business_time", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("actions", "receipt_business_time")
    op.drop_column("actions", "submitted_business_time")
    op.drop_column("mission_timeline", "business_time")
