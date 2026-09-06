"""Durable technical job queue and worker heartbeat; no business tables yet."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("dedup_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("store_id", sa.String(128)),
        sa.Column("mission_id", sa.String(128)),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger_source", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.String(128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error_code", sa.String(128)),
        sa.Column("last_error", sa.String(512)),
        sa.Column("request_id", sa.String(128)),
        sa.Column("target_state_version", sa.Integer()),
        sa.Column("target_mission_version", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("dedup_key", name="uq_job_runs_dedup_key"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_nonnegative"),
        sa.CheckConstraint(
            "status IN ('READY','RUNNING','SUCCEEDED','FAILED','CANCELLED','RETRY_WAIT')",
            name="status",
        ),
        sa.CheckConstraint(
            "status <> 'RUNNING' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="running_lease",
        ),
    )
    op.create_index("ix_job_runs_due", "job_runs", ["status", "available_at"])
    op.create_index("ix_job_runs_lease", "job_runs", ["status", "lease_until"])
    op.create_index("ix_job_runs_mission", "job_runs", ["mission_id", "created_at", "id"])
    op.create_index(
        "uq_job_runs_active_check",
        "job_runs",
        ["mission_id"],
        unique=True,
        postgresql_where=sa.text(
            "job_type='check_mission' AND mission_id IS NOT NULL "
            "AND status IN ('READY','RUNNING','RETRY_WAIT')"
        ),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(128), primary_key=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("status IN ('RUNNING','STOPPED')", name="status"),
    )


def downgrade():
    op.drop_table("worker_heartbeats")
    op.drop_table("job_runs")
