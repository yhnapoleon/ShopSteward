import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def db():
    from app.db.session import Database

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to the dedicated migrated PostgreSQL test database")
    from sqlalchemy.engine import make_url

    assert make_url(url).database == "shopsteward_test", (
        "Only the dedicated test database is allowed"
    )
    database = Database(url)
    assert await database.ready(), "Apply Alembic migrations before integration tests"
    yield database
    await database.dispose()


async def add_job(db, **kwargs):
    from app.scheduling.repository import enqueue

    async with db.session() as session, session.begin():
        return await enqueue(session, job_type="worker_probe", dedup_key=str(uuid4()), **kwargs)


async def claim_job(db):
    from app.scheduling.repository import claim

    async with db.session() as session, session.begin():
        return await claim(session, lease_seconds=30, job_types=["worker_probe"])


@pytest.mark.parametrize("enabled", [False, True])
async def test_monitoring_reports_actual_agent_configuration(db, enabled):
    from httpx import ASGITransport, AsyncClient

    from app.core.config import Settings
    from app.main import create_app

    token = "monitoring-test-admin-credential-0001"
    app = create_app(
        Settings(
            _env_file=None,
            database_url=os.environ["TEST_DATABASE_URL"],
            agent_enabled=enabled,
            auth_tokens=[{"token": token, "principal_id": "monitoring-admin", "roles": ["admin"]}],
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get(
            "/api/v1/monitoring/status", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["agent_enabled"] is enabled


@pytest_asyncio.fixture(autouse=True)
async def isolated_queue(db):
    # These are only the two B0-01 tables in the dedicated database created for this suite.
    async with db.session() as session, session.begin():
        await session.execute(text("DELETE FROM job_runs"))
        await session.execute(text("DELETE FROM worker_heartbeats"))


async def test_enqueue_replays_same_resource_and_rejects_conflicting_content(db):
    from app.core.errors import AppError
    from app.scheduling.repository import enqueue

    async with db.session() as session, session.begin():
        first = await enqueue(
            session, job_type="worker_probe", dedup_key="same-key", payload={"note": "first"}
        )
    async with db.session() as session, session.begin():
        second = await enqueue(
            session, job_type="worker_probe", dedup_key="same-key", payload={"note": "first"}
        )
    assert first.id == second.id
    with pytest.raises(AppError) as failure:
        async with db.session() as session, session.begin():
            await enqueue(
                session, job_type="worker_probe", dedup_key="same-key", payload={"note": "changed"}
            )
    assert failure.value.code == "IDEMPOTENCY_KEY_REUSED"


async def test_concurrent_claimers_receive_each_job_only_once(db):
    jobs = [await add_job(db) for _ in range(4)]
    claimed = await asyncio.gather(*(claim_job(db) for _ in range(8)))
    ids = [job.id for job in claimed if job]
    assert sorted(ids) == sorted(job.id for job in jobs)


async def test_skip_locked_does_not_wait_or_claim_the_same_row(db):
    job = await add_job(db)
    async with db.session() as owner, owner.begin():
        await owner.execute(text("SELECT id FROM job_runs WHERE id=:id FOR UPDATE"), {"id": job.id})
        assert await asyncio.wait_for(claim_job(db), timeout=2) is None


async def test_wrong_or_expired_lease_cannot_write_result(db):
    from app.scheduling.models import Job
    from app.scheduling.repository import complete

    await add_job(db)
    job = await claim_job(db)
    async with db.session() as session, session.begin():
        assert not await complete(
            session, job.id, "wrong-token", {"summary": "bad", "references": []}
        )
        await session.execute(
            text(
                "UPDATE job_runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id"
            ),
            {"id": job.id},
        )
        assert not await complete(
            session, job.id, job.lease_token, {"summary": "old", "references": []}
        )
    async with db.session() as session:
        current = await session.get(Job, job.id)
        assert current.status == "RUNNING"
        assert current.result is None


async def test_recovery_changes_token_and_does_not_replay_external_purchase(db):
    from app.scheduling.repository import complete, enqueue, recover_expired

    await add_job(db)
    old = await claim_job(db)
    async with db.session() as session, session.begin():
        external = await enqueue(session, job_type="execute_purchase", dedup_key="external")
        await session.execute(
            text(
                "UPDATE job_runs SET status='RUNNING',lease_token='external',"
                "lease_until=clock_timestamp()-interval '1 second' WHERE id IN (:first,:second)"
            ),
            {"first": old.id, "second": external.id},
        )
        await recover_expired(session, retry_safe_types=["worker_probe"])
    new = await claim_job(db)
    assert new.id == old.id
    assert new.lease_token != old.lease_token
    async with db.session() as session, session.begin():
        assert not await complete(
            session, old.id, old.lease_token, {"summary": "old", "references": []}
        )
        assert await complete(
            session, new.id, new.lease_token, {"summary": "new", "references": []}
        )
        assert (
            await session.scalar(
                text("SELECT status FROM job_runs WHERE id=:id"), {"id": external.id}
            )
            == "RUNNING"
        )


async def test_runner_executes_probe_and_persists_heartbeat_and_result(db):
    from app.core.config import Settings
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    created = await add_job(db)
    runner = Runner(db, Settings(_env_file=None), worker_id="test-worker")
    assert await runner.run_once()
    async with db.session() as session:
        job = await session.get(Job, created.id)
        assert job.status == "SUCCEEDED"
        assert job.attempt_count == 1
        assert job.result["summary"] == "Worker database probe completed"
        assert (
            await session.scalar(
                text("SELECT status FROM worker_heartbeats WHERE worker_id='test-worker'")
            )
            == "RUNNING"
        )


async def test_job_visibility_and_monitoring_with_real_database(db):
    from httpx import ASGITransport, AsyncClient

    from app.core.config import Settings
    from app.main import create_app

    scoped = await add_job(db, store_id="store_a", mission_id="mission_a")
    other = await add_job(db, store_id="store_b", mission_id="mission_b")
    technical = await add_job(db)
    token = "viewer-token-00000000000000000000001"
    settings = Settings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        auth_tokens=[
            {
                "token": token,
                "principal_id": "viewer",
                "roles": ["viewer"],
                "store_ids": ["store_a"],
            },
        ],
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health/ready")).status_code == 200
            headers = {"Authorization": f"Bearer {token}"}
            assert (
                await client.get(f"/api/v1/job-runs/{scoped.id}", headers=headers)
            ).status_code == 200
            assert (
                await client.get(f"/api/v1/job-runs/{other.id}", headers=headers)
            ).status_code == 404
            assert (
                await client.get(f"/api/v1/job-runs/{technical.id}", headers=headers)
            ).status_code == 404


async def test_wrong_database_credentials_report_unavailable_readiness(db):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.engine import make_url

    from app.core.config import Settings
    from app.main import create_app

    url = make_url(os.environ["TEST_DATABASE_URL"]).set(password="deliberately-incorrect")
    app = create_app(
        Settings(_env_file=None, database_url=url.render_as_string(hide_password=False))
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            response = await client.get("/health/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "unavailable", "component": "backend"}


async def test_probe_failure_is_persisted_without_exception_details(db):
    from app.core.config import Settings
    from app.scheduling.handlers import Handler
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    async def failing_probe(database, job):
        raise RuntimeError("private diagnostic must not escape")

    job = await add_job(db)
    runner = Runner(
        db,
        Settings(_env_file=None),
        handlers={
            "worker_probe": Handler(failing_probe, retry_safe=True),
        },
    )
    assert await runner.run_once()
    async with db.session() as session:
        stored = await session.get(Job, job.id)
        assert stored.status == "FAILED"
        assert stored.error_code == "HANDLER_FAILED"
        assert "private diagnostic" not in stored.last_error


async def test_lease_renewal_requires_current_unexpired_owner(db):
    from app.scheduling.repository import renew

    await add_job(db)
    job = await claim_job(db)
    async with db.session() as session, session.begin():
        assert not await renew(session, job.id, "not-owner", 60)
        assert await renew(session, job.id, job.lease_token, 60)
        lease = await session.scalar(
            text("SELECT lease_until FROM job_runs WHERE id=:id"), {"id": job.id}
        )
        assert lease > job.lease_until
        await session.execute(
            text(
                "UPDATE job_runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id"
            ),
            {"id": job.id},
        )
        assert not await renew(session, job.id, job.lease_token, 60)


async def test_continuous_worker_stops_cleanly_and_monitoring_is_honest(db):
    from app.core.config import Settings
    from app.scheduling.repository import monitoring_status
    from app.scheduling.runner import Runner

    runner = Runner(db, Settings(_env_file=None, worker_poll_seconds=0.02), worker_id="stop-test")
    stop = asyncio.Event()
    task = asyncio.create_task(runner.serve(stop))
    try:
        for _ in range(50):
            async with db.session() as session:
                status = await monitoring_status(session, 30)
                if status["worker_status"] == "RUNNING":
                    assert isinstance(status["sources"], list)
                    break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("Worker never reported a persisted heartbeat")
    finally:
        stop.set()
        await asyncio.wait_for(task, 5)
    async with db.session() as session:
        assert (await monitoring_status(session, 30))["worker_status"] == "STOPPED"


async def test_shutdown_does_not_claim_new_work_after_waiting_for_database_lock(db):
    from app.core.config import Settings
    from app.scheduling.models import Job
    from app.scheduling.repository import heartbeat
    from app.scheduling.runner import Runner

    job = await add_job(db)
    worker_id = "blocked-stop-test"
    async with db.session() as session, session.begin():
        await heartbeat(session, worker_id)
    runner = Runner(db, Settings(_env_file=None, worker_poll_seconds=0.02), worker_id=worker_id)
    stop = asyncio.Event()
    async with db.session() as locker, locker.begin():
        await locker.execute(
            text("SELECT worker_id FROM worker_heartbeats WHERE worker_id=:id FOR UPDATE"),
            {"id": worker_id},
        )
        task = asyncio.create_task(runner.serve(stop))
        for _ in range(100):
            async with db.session() as observer:
                blocked = await observer.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                        "AND wait_event_type='Lock' AND query LIKE '%worker_heartbeats%'"
                    )
                )
            if blocked >= 2:  # pulse plus at least one run_once are waiting before claiming.
                break
            await asyncio.sleep(0.01)
        else:
            stop.set()
            pytest.fail("Worker did not reach the controlled pre-claim boundary")
        stop.set()
    await asyncio.wait_for(task, 5)
    async with db.session() as session:
        assert (await session.get(Job, job.id)).status == "READY"
