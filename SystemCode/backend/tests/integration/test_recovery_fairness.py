import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_execution import (
    Supplier,
    approve,
    clean_queue,  # noqa: F401
    environment,
    isolated_actions,  # noqa: F401
    planned,
    settings,
)

from app.execution.jobs import make_handlers
from app.operations.models import Store
from app.scheduling.handlers import make_handlers as system_handlers
from app.scheduling.models import Job
from app.scheduling.repository import enqueue
from app.scheduling.runner import Runner

pytestmark = pytest.mark.integration


async def test_busy_orphan_action_does_not_block_unrelated_worker_claim(db):
    async with environment(db) as (seed, client):
        _, plan = await planned(db, seed, client)
        accepted = await approve(client, plan)
        async with db.session() as session, session.begin():
            job = await session.get(Job, accepted["job_run_id"])
            job.status = "CANCELLED"
            probe = await enqueue(session, job_type="worker_probe", dedup_key=uuid4().hex)
        config = settings(db, seed)
        runner = Runner(
            db, config, handlers=make_handlers(config, client=Supplier()) | system_handlers(config)
        )
        async with db.session() as busy, busy.begin():
            await busy.execute(select(Store).where(Store.id == seed["store_id"]).with_for_update())
            # The unrelated claim must finish while the contending transaction is still open.
            assert await asyncio.wait_for(runner.run_once(), 1)
            async with db.session() as session:
                assert (await session.get(Job, probe.id)).status == "SUCCEEDED"
