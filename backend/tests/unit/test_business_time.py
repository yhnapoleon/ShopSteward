"""Business time (the store's simulation clock) beside the wall-clock times the API returns."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.missions.repository import timeline
from app.reporting.schemas import TimelineEntry

WALL = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
CLOCK = datetime(2026, 9, 9, 18, tzinfo=UTC)


class Session:
    info = {}

    def __init__(self, store):
        self.store, self.added = store, []

    async def get(self, model, key):
        assert key == self.store.id
        return self.store

    def add(self, row):
        self.added.append(row)

    async def scalar(self, statement):
        return WALL


async def test_timeline_entry_records_the_store_clock_beside_the_wall_clock():
    session = Session(SimpleNamespace(id="store-1", simulation_time=CLOCK))
    mission = SimpleNamespace(id="mission-1", store_id="store-1")

    await timeline(session, mission, "PLAN_DECIDED", "approve", actor="owner")

    (row,) = session.added
    assert (row.created_at, row.business_time) == (WALL, CLOCK)
    entry = TimelineEntry.model_validate(row).model_dump(mode="json")
    assert (entry["created_at"], entry["business_time"]) == (
        "2026-10-21T09:30:00Z",
        "2026-09-09T18:00:00Z",
    )


async def test_timeline_entry_without_a_store_clock_has_no_business_time():
    session = Session(SimpleNamespace(id="store-1", simulation_time=None))

    await timeline(session, SimpleNamespace(id="m", store_id="store-1"), "PLAN_DECIDED", "x")

    assert session.added[0].business_time is None


def test_runtime_contract_names_the_business_times_and_the_summary_zone():
    from app.core.config import Settings
    from app.main import create_app

    spec = create_app(Settings(_env_file=None)).openapi()
    schemas = spec["components"]["schemas"]
    nullable_time = [{"type": "string", "format": "date-time"}, {"type": "null"}]
    for schema, field in [
        ("TimelineEntry", "business_time"),
        ("Action", "submitted_business_time"),
        ("Action", "receipt_business_time"),
        ("LedgerEntryView", "simulation_time"),
    ]:
        assert schemas[schema]["properties"][field]["anyOf"] == nullable_time
    # The new fields may be left out, so hand-written frontend fixtures stay valid; the
    # ledger's simulation_time was already required.
    assert "simulation_time" in schemas["LedgerEntryView"]["required"]
    assert "business_time" not in schemas["TimelineEntry"]["required"]
    assert "receipt_business_time" not in schemas["Action"]["required"]
    assert schemas["SaleSummary"]["properties"]["timezone"]["type"] == "string"
    summary = spec["paths"]["/api/v1/sales/summary"]["get"]["parameters"]
    assert any(p["name"] == "tz" and p["in"] == "query" and not p["required"] for p in summary)
