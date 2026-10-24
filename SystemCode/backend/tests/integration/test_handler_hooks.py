import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from test_bootstrap import isolated_jobs, settings  # noqa: F401

from app.operations.models import Command
from app.scheduling.handlers import Handler
from app.scheduling.models import Job
from app.scheduling.repository import enqueue
from app.scheduling.runner import Runner

pytestmark = pytest.mark.integration


async def test_before_claim_runs_once_per_callback_and_stop_skips_it(db):
    calls = []
    key = uuid4().hex

    async def prepare(database):
        calls.append("prepare")
        async with database.session() as session, session.begin():
            await enqueue(session, job_type="worker_probe", dedup_key=key)

    async def run(database, job):
        calls.append("run")
        return {"summary": "worker_probe", "references": []}

    handler = Handler(run, retry_safe=True, before_claim=prepare)
    runner = Runner(
        db, settings(db), handlers={"worker_probe": handler, "check_freshness": handler}
    )
    stop = asyncio.Event()
    stop.set()
    assert not await runner.run_once(stop)
    assert calls == []
    assert await runner.run_once()
    assert calls == ["prepare", "run"]


async def test_failed_before_claim_does_not_claim_ready_work(db):
    async with db.session() as session, session.begin():
        job = await enqueue(session, job_type="worker_probe", dedup_key=uuid4().hex)

    async def prepare(database):
        raise RuntimeError("prepare failed")

    async def run(database, claimed):
        pytest.fail("Work must not be claimed")

    runner = Runner(db, settings(db), handlers={"worker_probe": Handler(run, before_claim=prepare)})
    with pytest.raises(RuntimeError, match="prepare failed"):
        await runner.run_once()
    async with db.session() as session:
        current = await session.get(Job, job.id)
        assert current.status == "READY" and current.attempt_count == 0


@pytest.mark.parametrize("lease", ["live", "expired", "replaced"])
async def test_on_error_writes_and_failure_share_lease_fence(db, lease):
    marker = uuid4().hex
    async with db.session() as session, session.begin():
        job = await enqueue(session, job_type="worker_probe", dedup_key=uuid4().hex)

    async def run(database, claimed):
        raise RuntimeError("business failure")

    async def on_error(session, claimed, error):
        assert str(error) == "business failure"
        assert session.in_transaction()
        session.add(Command(id=marker, content_hash="0" * 64, response={"evidence": True}))
        if lease != "live":
            # Invalidate after the hook starts: checking only before it is insufficient.
            sql = (
                "lease_until=clock_timestamp()-interval '1 second'"
                if lease == "expired"
                else "lease_token='new-owner'"
            )
            async with db.session() as other, other.begin():
                await other.execute(
                    text("UPDATE job_runs SET " + sql + " WHERE id=:id"), {"id": job.id}
                )

    handler = Handler(run, retry_safe=True, on_error=on_error)
    assert await Runner(db, settings(db), handlers={"worker_probe": handler}).run_once()
    async with db.session() as session:
        assert (await session.get(Command, marker) is not None) == (lease == "live")
        assert (await session.get(Job, job.id)).status == (
            "FAILED" if lease == "live" else "RUNNING"
        )


async def test_failed_error_hook_rolls_back_and_leaves_job_for_lease_recovery(db):
    marker = uuid4().hex
    async with db.session() as session, session.begin():
        job = await enqueue(session, job_type="worker_probe", dedup_key=uuid4().hex)

    async def run(database, claimed):
        raise RuntimeError("business failure")

    async def on_error(session, claimed, error):
        session.add(Command(id=marker, content_hash="0" * 64, response={"evidence": True}))
        await session.flush()
        raise RuntimeError("error hook failed")

    handler = Handler(run, retry_safe=True, on_error=on_error)
    with pytest.raises(RuntimeError, match="error hook failed"):
        await Runner(db, settings(db), handlers={"worker_probe": handler}).run_once()
    async with db.session() as session:
        assert await session.get(Command, marker) is None
        assert (await session.get(Job, job.id)).status == "RUNNING"
