import asyncio
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from test_operations import event, initial_snapshot, initialize

pytestmark = pytest.mark.integration
ADMIN = "bootstrap-admin-token-00000001"
SERVICE = "bootstrap-source-token-0000001"


@pytest_asyncio.fixture(autouse=True)
async def isolated_jobs(db):
    async with db.session() as session, session.begin():
        await session.execute(text("DELETE FROM job_runs"))


def settings(db, seed=None, **kwargs):
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        database_url=db.engine.url.render_as_string(hide_password=False),
        auth_tokens=[
            {"token": ADMIN, "principal_id": "admin", "roles": ["admin"]},
            {
                "token": SERVICE,
                "principal_id": "source",
                "kind": "service",
                "scenario_run_ids": [seed["scenario_run_id"]] if seed else [],
            },
        ],
        **kwargs,
    )


async def test_catalog_service_scope_dev_gate_and_replay_stable_create_receipt(db):
    from app.main import create_app

    seed = initial_snapshot()
    await initialize(db, seed)
    app = create_app(settings(db, seed))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://backend"
        ) as client,
    ):
        admin = {"Authorization": f"Bearer {ADMIN}", "Idempotency-Key": str(uuid4())}
        response = await client.get(
            "/api/v1/catalog", params={"store_id": seed["store_id"]}, headers=admin
        )
        assert response.status_code == 200, response.text
        assert response.json() == seed["initial_catalog"]
        body = {
            "source": "simulation",
            "scenario_run_id": seed["scenario_run_id"],
            "events": [event(seed)],
        }
        assert (
            await client.post("/internal/v1/events/batches", json=body, headers=admin)
        ).status_code == 403
        service = {"Authorization": f"Bearer {SERVICE}", "Idempotency-Key": str(uuid4())}
        assert (
            await client.post("/internal/v1/events/batches", json=body, headers=service)
        ).status_code == 200
        body["scenario_run_id"] = "ungranted-run"
        assert (
            await client.post("/internal/v1/events/batches", json=body, headers=service)
        ).status_code == 403
        first = await client.post("/dev/v1/scenarios", json={"scenario": "SC01"}, headers=admin)
        assert first.status_code == 202, first.text
        replay = await client.post("/dev/v1/scenarios", json={"scenario": "SC01"}, headers=admin)
        assert first.json() == replay.json()
    production = create_app(settings(db, app_env="production", docs_enabled=True))
    assert "/dev/v1/scenarios" not in production.openapi()["paths"]


async def test_lost_lease_rolls_back_derived_business_state(db):
    from app.operations.repository import initialize as import_seed
    from app.operations.schemas import ScenarioRun
    from app.scheduling.handlers import Handler
    from app.scheduling.repository import enqueue
    from app.scheduling.runner import Runner

    seed = initial_snapshot()
    async with db.session() as session, session.begin():
        job = await enqueue(
            session,
            job_type="initialize_scenario",
            dedup_key=str(uuid4()),
            payload={"scenario": "SC01"},
        )

    async def prepare(database, claimed):
        async with database.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE job_runs SET lease_until=clock_timestamp()-interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": claimed.id},
            )
        return ScenarioRun.model_validate(seed)

    async def apply(session, claimed, prepared):
        await import_seed(session, prepared)
        return {"summary": "initialized", "references": []}

    runner = Runner(
        db,
        settings(db),
        handlers={"initialize_scenario": Handler(prepare, retry_safe=True, apply=apply)},
    )
    await runner.run_once()
    async with db.session() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM stores WHERE id=:id"), {"id": seed["store_id"]}
            )
            == 0
        )
        assert (
            await session.scalar(text("SELECT status FROM job_runs WHERE id=:id"), {"id": job.id})
            == "RUNNING"
        )


async def test_source_page_validation_prevents_false_freshness_and_applies_empty_caught_up(db):
    from app.core.errors import AppError
    from app.operations.jobs import apply_page
    from app.operations.models import SourceCursor
    from app.operations.schemas import EventPage

    seed = initial_snapshot()
    await initialize(db, seed)
    for invalid in [
        {"events": [], "last_sequence": 0, "source_head_sequence": 2, "has_more": False},
        {"events": [], "last_sequence": 2, "source_head_sequence": 2, "has_more": False},
    ]:
        with pytest.raises(AppError):
            async with db.session() as session, session.begin():
                await apply_page(
                    session, seed["scenario_run_id"], 0, EventPage(**invalid), str(uuid4())
                )
    async with db.session() as session, session.begin():
        await apply_page(
            session,
            seed["scenario_run_id"],
            0,
            EventPage(events=[], last_sequence=0, source_head_sequence=0, has_more=False),
            str(uuid4()),
        )
    async with db.session() as session:
        cursor = await session.scalar(
            select(SourceCursor).where(SourceCursor.scenario_run_id == seed["scenario_run_id"])
        )
        assert cursor.last_sequence == 0 and cursor.last_success_at is not None

    async with db.session() as session, session.begin():
        await apply_page(
            session,
            seed["scenario_run_id"],
            0,
            EventPage(events=[event(seed)], last_sequence=1, source_head_sequence=2, has_more=True),
            str(uuid4()),
        )
    from app.scheduling.repository import monitoring_status

    async with db.session() as session:
        monitoring = await monitoring_status(session, 30)
        source = next(
            s
            for s in monitoring["sources"]
            if s["source"] == f"simulation:{seed['scenario_run_id']}"
        )
        assert source["status"] == "STALE"


async def test_remote_commit_then_lost_local_lease_recovers_same_run_and_syncs(db):
    from simulator.config import Settings as SimSettings
    from simulator.main import create_app as create_simulator
    from simulator.models import Run

    from app.operations.client import SimulationClient
    from app.operations.jobs import make_handlers
    from app.operations.models import SourceCursor, Store
    from app.scheduling.handlers import Handler
    from app.scheduling.models import Job
    from app.scheduling.repository import enqueue, monitoring_status
    from app.scheduling.runner import Runner

    sim_url = os.environ.get("TEST_SIM_DATABASE_URL")
    if not sim_url:
        pytest.skip("Set TEST_SIM_DATABASE_URL for cross-service PostgreSQL integration")
    from sqlalchemy.engine import make_url

    assert make_url(sim_url).database == "shopsteward_sim_test"
    simulator = create_simulator(
        SimSettings(_env_file=None, sim_database_url=sim_url, sim_service_token=SERVICE)
    )
    configured = settings(db, simulation_token=SERVICE)
    client = SimulationClient(configured, transport=httpx.ASGITransport(app=simulator))
    handlers = make_handlers(configured, client=client)
    async with db.session() as session, session.begin():
        job = await enqueue(
            session,
            job_type="initialize_scenario",
            dedup_key=str(uuid4()),
            payload={"scenario": "SC01"},
        )

    async def interrupt_after_remote(database, claimed):
        seed = await handlers["initialize_scenario"].run(database, claimed)
        async with database.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE job_runs SET lease_until=clock_timestamp()-interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": claimed.id},
            )
        return seed

    async with simulator.router.lifespan_context(simulator):
        interrupted = Runner(
            db,
            configured,
            handlers={
                "initialize_scenario": Handler(
                    interrupt_after_remote,
                    retry_safe=True,
                    apply=handlers["initialize_scenario"].apply,
                )
            },
        )
        await interrupted.run_once()
        worker = Runner(db, configured, handlers=handlers)
        await worker.run_once()
        await worker.run_once()
        async with db.session() as session:
            completed = await session.get(Job, job.id)
            assert completed.status == "SUCCEEDED" and completed.attempt_count == 2
            run_id = next(
                r["id"] for r in completed.result["references"] if r["type"] == "scenario"
            )
            store = await session.scalar(select(Store).where(Store.scenario_run_id == run_id))
            assert store.cash_minor == 100000 and store.state_version == 1
            cursor = await session.get(SourceCursor, run_id)
            assert cursor.last_success_at is not None
            monitoring = await monitoring_status(session, 30)
            source = next(s for s in monitoring["sources"] if s["source"] == f"simulation:{run_id}")
            assert source["status"] == "FRESH"
        async with simulator.state.db.session() as session:
            assert (
                len((await session.scalars(select(Run).where(Run.command_key == job.id))).all())
                == 1
            )
        async with db.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE source_cursors SET "
                    "last_success_at=clock_timestamp()-interval '60 seconds' "
                    "WHERE scenario_run_id=:id"
                ),
                {"id": run_id},
            )
        async with db.session() as session:
            monitoring = await monitoring_status(session, 30)
            assert (
                next(s for s in monitoring["sources"] if s["source"] == f"simulation:{run_id}")[
                    "status"
                ]
                == "STALE"
            )


async def test_retryable_dependency_failure_keeps_original_job_for_bounded_retry(db):
    from app.core.errors import AppError
    from app.scheduling.handlers import Handler
    from app.scheduling.models import Job
    from app.scheduling.repository import enqueue
    from app.scheduling.runner import Runner

    async with db.session() as session, session.begin():
        job = await enqueue(session, job_type="initialize_scenario", dedup_key=str(uuid4()))

    async def unavailable(database, claimed):
        raise AppError(503, "SIMULATION_UNAVAILABLE", "Unavailable", retryable=True)

    worker = Runner(
        db, settings(db), handlers={"initialize_scenario": Handler(unavailable, retry_safe=True)}
    )
    for attempt in [1, 2, 3]:
        await worker.run_once()
        async with db.session() as session, session.begin():
            current = await session.get(Job, job.id)
            assert current.status == ("RETRY_WAIT" if attempt < 3 else "FAILED")
            assert current.attempt_count == attempt
            await session.execute(
                text("UPDATE job_runs SET available_at=clock_timestamp() WHERE id=:id"),
                {"id": job.id},
            )


async def test_handler_apply_is_subject_to_job_deadline_and_rolls_back(db):
    from app.operations.repository import initialize as import_seed
    from app.operations.schemas import ScenarioRun
    from app.scheduling.handlers import Handler
    from app.scheduling.models import Job
    from app.scheduling.repository import enqueue
    from app.scheduling.runner import Runner

    seed = initial_snapshot()
    async with db.session() as session, session.begin():
        job = await enqueue(session, job_type="initialize_scenario", dedup_key=str(uuid4()))

    async def prepare(database, claimed):
        return seed

    async def apply(session, claimed, value):
        await import_seed(session, ScenarioRun.model_validate(value))
        await asyncio.sleep(0.3)
        return {"summary": "Must time out", "references": []}

    runner = Runner(
        db,
        settings(db, job_timeout_seconds=0.15),
        handlers={"initialize_scenario": Handler(prepare, retry_safe=True, apply=apply)},
    )
    await runner.run_once()
    async with db.session() as session:
        assert (await session.get(Job, job.id)).status != "SUCCEEDED"
        assert (
            await session.scalar(
                text("SELECT count(*) FROM stores WHERE id=:id"), {"id": seed["store_id"]}
            )
            == 0
        )
