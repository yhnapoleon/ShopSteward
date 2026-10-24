"""Durable manual retry command receipts and bounded lifetime attempt windows."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "knowledge_0002"
down_revision = "knowledge_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_jobs",
        sa.Column("attempt_limit", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "knowledge_jobs",
        sa.Column("total_attempt_limit", sa.Integer(), nullable=False, server_default="15"),
    )
    # Existing installations may have configured a larger initial worker window.
    op.execute(
        "UPDATE knowledge_jobs SET attempt_limit = GREATEST(5, attempt), "
        "total_attempt_limit = GREATEST(15, attempt)"
    )
    op.create_check_constraint(
        "ck_knowledge_job_attempt_limits",
        "knowledge_jobs",
        "attempt_limit > 0 AND total_attempt_limit >= attempt_limit",
    )
    op.create_table(
        "knowledge_job_retries",
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("job_id", sa.String(128), sa.ForeignKey("knowledge_jobs.id"), nullable=False),
        sa.Column("receipt", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("knowledge_job_retries")
    op.drop_constraint("ck_knowledge_job_attempt_limits", "knowledge_jobs", type_="check")
    op.drop_column("knowledge_jobs", "total_attempt_limit")
    op.drop_column("knowledge_jobs", "attempt_limit")
