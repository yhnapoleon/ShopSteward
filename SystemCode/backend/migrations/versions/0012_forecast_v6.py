"""Saved v6 inputs, immutable prediction evidence and scoped current bindings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_forecast_v6"
down_revision = "0011_knowledge_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "forecast_v6_inputs",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=False),
        sa.Column("series_id", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id", "sku_id"], ["products.store_id", "products.sku_id"]),
        sa.CheckConstraint("mode IN ('observed','historical_demo')", name="mode"),
    )
    op.create_table(
        "forecast_v6_evidence",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "input_id", sa.String(128), sa.ForeignKey("forecast_v6_inputs.id"), nullable=False
        ),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("model", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state_version >= 1", name="state_version"),
    )
    op.create_table(
        "forecast_v6_bindings",
        sa.Column("store_id", sa.String(128), primary_key=True),
        sa.Column("sku_id", sa.String(128), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "input_id", sa.String(128), sa.ForeignKey("forecast_v6_inputs.id"), nullable=False
        ),
        sa.Column(
            "evidence_id", sa.String(128), sa.ForeignKey("forecast_v6_evidence.id"), nullable=False
        ),
        sa.Column("activate_for_planning", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["store_id", "sku_id"], ["products.store_id", "products.sku_id"]),
        sa.CheckConstraint("revision >= 1", name="revision"),
    )
    op.execute("""CREATE FUNCTION forecast_v6_immutable_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Saved forecast inputs and evidence are immutable'
            USING ERRCODE = '23514';
        END; $$""")
    for table in ("forecast_v6_inputs", "forecast_v6_evidence"):
        op.execute(
            f"CREATE TRIGGER forecast_v6_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forecast_v6_immutable_guard()"
        )
    op.execute("""CREATE FUNCTION forecast_v6_binding_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM forecast_v6_inputs i JOIN forecast_v6_evidence e
            ON e.input_id = i.id WHERE i.id = NEW.input_id AND e.id = NEW.evidence_id
            AND i.store_id = NEW.store_id AND i.sku_id = NEW.sku_id
            AND (NOT NEW.activate_for_planning OR i.mode = 'observed')) THEN
            RAISE EXCEPTION 'Invalid forecast scope or demonstration activation'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER forecast_v6_binding BEFORE INSERT OR UPDATE ON forecast_v6_bindings
        FOR EACH ROW EXECUTE FUNCTION forecast_v6_binding_guard()""")


def downgrade():
    op.drop_table("forecast_v6_bindings")
    op.drop_table("forecast_v6_evidence")
    op.drop_table("forecast_v6_inputs")
    op.execute("DROP FUNCTION forecast_v6_binding_guard()")
    op.execute("DROP FUNCTION forecast_v6_immutable_guard()")
