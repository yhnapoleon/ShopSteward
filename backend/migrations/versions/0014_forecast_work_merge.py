"""Join deployed forecast and work-intake histories without rewriting either branch."""

revision = "0014_forecast_work_merge"
down_revision = ("0012_forecast_v6", "0013_work_intake")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
