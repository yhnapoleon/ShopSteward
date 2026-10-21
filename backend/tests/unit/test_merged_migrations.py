"""Both previously deployed PR histories must upgrade to the same ready schema."""

from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.session import SCHEMA_REVISION


@pytest.mark.parametrize(
    ("start", "required", "already_present"),
    [
        ("0012_forecast_v6", "CREATE TABLE work_items", "CREATE TABLE forecast_v6_inputs"),
        ("0013_work_intake", "CREATE TABLE forecast_v6_inputs", "CREATE TABLE work_items"),
        ("base", "CREATE TABLE work_items", None),
    ],
)
def test_existing_database_histories_upgrade_to_one_ready_head(
    monkeypatch, start, required, already_present
):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/unused")
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"), output_buffer=output)
    assert ScriptDirectory.from_config(config).get_heads() == [SCHEMA_REVISION]
    command.upgrade(config, f"{start}:head", sql=True)
    sql = output.getvalue()
    assert required in sql
    assert SCHEMA_REVISION in sql
    if already_present:
        assert already_present not in sql
    else:
        assert "CREATE TABLE forecast_v6_inputs" in sql
        assert "CREATE TABLE agent_run_events" in sql


def test_business_times_are_nullable_columns_added_after_sourcing(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/unused")
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "0019_sourcing:0020_business_time", sql=True)
    sql = output.getvalue()
    for table, column in [
        ("mission_timeline", "business_time"),
        ("actions", "submitted_business_time"),
        ("actions", "receipt_business_time"),
    ]:
        assert f"ALTER TABLE {table} ADD COLUMN {column} TIMESTAMP WITH TIME ZONE;" in sql
