import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def isolated_commands(db):
    async with db.session() as session, session.begin():
        await session.execute(text("DELETE FROM command_receipts"))


def initial_snapshot():
    contract = json.loads(
        (Path(__file__).parents[3] / "docs/api/services.openapi.json").read_text(encoding="utf-8")
    )
    sample = contract["paths"]["/sim/v1/runs"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["example"]
    suffix = uuid4().hex
    return json.loads(
        json.dumps(sample)
        .replace("store_001", "store_" + suffix)
        .replace("scenario_001", "run_" + suffix)
        .replace("forecast_001", "forecast_" + suffix)
    )


def event(seed, sequence=1, kind="SALE_RECORDED", **payload):
    defaults = {"sku_id": "sku_001", "quantity": 10, "unit_price_minor": 2000}
    if kind == "DEMAND_REVISED":
        forecast = seed["initial_forecast"]
        defaults = {
            "sku_id": "sku_001",
            "remaining_demand": 70,
            "forecast_version": "fixed-0",
            **{
                key: forecast[key]
                for key in ("data_as_of", "valid_until", "horizon_start", "horizon_end")
            },
        }
    elif kind == "GOODS_RECEIVED":
        defaults = {"sku_id": "sku_001", "quantity": 40, "action_id": "unknown"}
    return {
        "event_id": str(uuid4()),
        "sequence": sequence,
        "schema_version": "1.0",
        "event_type": kind,
        "store_id": seed["store_id"],
        "occurred_at": seed["simulation_time"],
        "simulation_time": seed["simulation_time"],
        "payload": defaults | payload,
    }


async def initialize(db, seed):
    from app.operations.repository import initialize
    from app.operations.schemas import ScenarioRun

    async with db.session() as session, session.begin():
        await initialize(session, ScenarioRun.model_validate(seed))


async def ingest(db, seed, events, key=None):
    from app.operations.repository import ingest
    from app.operations.schemas import EventBatch

    batch = EventBatch(source="simulation", scenario_run_id=seed["scenario_run_id"], events=events)
    async with db.session() as session, session.begin():
        return await ingest(session, batch, command_scope="test", key=key or str(uuid4()))


async def state(db, seed):
    from app.operations.repository import get_state

    async with db.session() as session:
        return (await get_state(session, seed["store_id"])).model_dump(mode="json")


async def test_init_replay_preserves_mutated_projection_and_one_init_ledger(db):
    seed = initial_snapshot()
    await initialize(db, seed)
    await ingest(db, seed, [event(seed)])
    await initialize(db, seed)
    current = await state(db, seed)
    assert (current["cash_minor"], current["receivables_minor"], current["state_version"]) == (
        100000,
        20000,
        2,
    )
    assert current["stocks"][0]["on_hand"] == 10
    assert current["stocks"][0]["remaining_demand"] == 50
    async with db.session() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM ledger_entries WHERE store_id=:id AND effect_type='INIT'"
                ),
                {"id": seed["store_id"]},
            )
            == 1
        )


async def test_batch_replay_and_event_duplicates_do_not_apply_twice(db):
    seed = initial_snapshot()
    await initialize(db, seed)
    sale = event(seed)
    first = await ingest(db, seed, [sale], "stable")
    replay = await ingest(db, seed, [sale], "stable")
    duplicate = await ingest(db, seed, [sale])
    assert first == replay
    assert duplicate.duplicate_event_ids == [sale["event_id"]]
    assert duplicate.accepted_event_ids == []
    assert (await state(db, seed))["receivables_minor"] == 20000


@pytest.mark.parametrize(
    "change,code",
    [
        ("gap", "EVENT_SEQUENCE_GAP"),
        ("content", "EVENT_CONFLICT"),
        ("sequence", "EVENT_CONFLICT"),
        ("store", "EVENT_STORE_MISMATCH"),
        ("sku", "RESOURCE_NOT_FOUND"),
        ("receipt", "ACTION_NOT_CONFIRMED"),
        ("cash", "INSUFFICIENT_STOCK"),
        ("key", "IDEMPOTENCY_KEY_REUSED"),
    ],
)
async def test_invalid_batch_rolls_back_all_projection_and_cursor_changes(db, change, code):
    from app.core.errors import AppError

    seed = initial_snapshot()
    await initialize(db, seed)
    first = event(seed, quantity=1)
    await ingest(db, seed, [first], "original")
    before = await state(db, seed)
    next_event = event(seed, 2, quantity=1)
    invalid = event(seed, 3)
    key = None
    if change == "gap":
        invalid["sequence"] = 4
    if change == "content":
        invalid = copy.deepcopy(first)
        invalid["payload"]["quantity"] = 2
    if change == "sequence":
        invalid["sequence"] = 1
    if change == "store":
        invalid["store_id"] = "another-store"
    if change == "sku":
        invalid["payload"]["sku_id"] = "unknown-sku"
    if change == "receipt":
        invalid = event(seed, 3, "GOODS_RECEIVED")
    if change == "cash":
        invalid["payload"]["quantity"] = 999
    if change == "key":
        key = "original"
    with pytest.raises(AppError) as failure:
        await ingest(db, seed, [next_event, invalid], key)
    assert failure.value.code == code
    assert await state(db, seed) == before
    async with db.session() as session:
        assert (
            await session.scalar(
                text("SELECT last_sequence FROM source_cursors WHERE scenario_run_id=:id"),
                {"id": seed["scenario_run_id"]},
            )
            == 1
        )


async def test_concurrent_delivery_is_applied_once(db):
    seed = initial_snapshot()
    await initialize(db, seed)
    sale = event(seed)
    results = await asyncio.gather(*(ingest(db, seed, [sale]) for _ in range(5)))
    assert sum(len(result.accepted_event_ids) for result in results) == 1
    assert (await state(db, seed))["state_version"] == 2


async def test_demand_versions_are_opaque_and_sales_can_exceed_remaining_forecast(db):
    seed = initial_snapshot()
    await initialize(db, seed)
    demand = event(seed, 1, "DEMAND_REVISED", remaining_demand=2)
    await ingest(db, seed, [demand, event(seed, 2)])
    current = await state(db, seed)
    assert current["stocks"][0]["remaining_demand"] == 0
    assert current["stocks"][0]["forecast_version"].startswith("local-")
    assert current["receivables_minor"] == 20000


async def test_source_can_reuse_opaque_forecast_version_for_a_new_sequence(db):
    seed = initial_snapshot()
    await initialize(db, seed)
    before = await state(db, seed)
    await ingest(db, seed, [event(seed, 1, "DEMAND_REVISED", forecast_version="fixed-1")])
    current = await state(db, seed)
    assert current["stocks"][0]["remaining_demand"] == 70
    assert current["stocks"][0]["forecast_version"] != before["stocks"][0]["forecast_version"]


async def test_concurrent_same_command_key_across_runs_conflicts_atomically(db):
    from app.core.errors import AppError

    seeds = [initial_snapshot(), initial_snapshot()]
    for seed in seeds:
        await initialize(db, seed)
    results = await asyncio.gather(
        *(ingest(db, seed, [event(seed)], "cross-run-" + seeds[0]["store_id"]) for seed in seeds),
        return_exceptions=True,
    )
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], AppError) and failures[0].code == "IDEMPOTENCY_KEY_REUSED"
    states = [await state(db, seed) for seed in seeds]
    assert sum(s["receivables_minor"] for s in states) == 20000
