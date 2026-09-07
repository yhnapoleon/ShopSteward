"""Durable source intervals and source job coalescing (stop old workers before upgrade)."""

import sqlalchemy as sa
from alembic import op

revision = "0006_periodic"
down_revision = "0005_execution"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_schedules",
        sa.Column(
            "scenario_run_id",
            sa.String(128),
            sa.ForeignKey("source_cursors.scenario_run_id"),
            primary_key=True,
        ),
        sa.Column("job_type", sa.String(32), primary_key=True),
        sa.Column("interval_seconds", sa.BigInteger(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rerun_requested", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('sync_events','check_freshness')", name="ck_source_schedules_job_type"
        ),
        sa.CheckConstraint(
            "interval_seconds BETWEEN 5 AND 3600", name="ck_source_schedules_interval"
        ),
    )
    op.create_index("ix_source_schedules_due", "source_schedules", ["next_run_at"])
    op.execute("""
        INSERT INTO source_schedules
        SELECT scenario_run_id, kind, seconds,
          clock_timestamp() + seconds * interval '1 second', false
        FROM source_cursors CROSS JOIN
          (VALUES ('sync_events', 5), ('check_freshness', 60)) AS intervals(kind, seconds)
    """)
    # These are read-only source fetch jobs; keep one and preserve a catch-up request.
    # Do not touch purchases, receipts, events, or lease fences of the retained job.
    op.execute("""
        WITH ranked AS (
          SELECT id, row_number() OVER (
            PARTITION BY store_id, job_type ORDER BY created_at, id) AS n
          FROM job_runs WHERE job_type IN ('sync_events','check_freshness') AND store_id IS NOT NULL
          AND status IN ('READY','RUNNING','RETRY_WAIT')
        )
        UPDATE job_runs SET status='CANCELLED', finished_at=clock_timestamp(),
          lease_token=NULL, lease_until=NULL, error_code='SOURCE_JOB_COALESCED',
          last_error='Merged into the retained source job during B0-06 migration'
        WHERE id IN (SELECT id FROM ranked WHERE n > 1)
    """)
    op.execute("UPDATE source_schedules SET rerun_requested=true WHERE job_type='sync_events'")
    op.create_index(
        "uq_job_runs_active_source",
        "job_runs",
        ["store_id", "job_type"],
        unique=True,
        postgresql_where=sa.text(
            "job_type IN ('sync_events','check_freshness') AND store_id IS NOT NULL "
            "AND status IN ('READY','RUNNING','RETRY_WAIT')"
        ),
    )


def downgrade():
    op.drop_index("uq_job_runs_active_source", table_name="job_runs")
    op.drop_index("ix_source_schedules_due", table_name="source_schedules")
    op.drop_table("source_schedules")
