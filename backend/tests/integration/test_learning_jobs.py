import pytest
from sqlalchemy import select
from test_learning_storage import enable, event
from test_missions import fresh_seed, settings
from test_operations import initialize

pytestmark = pytest.mark.integration


async def test_dispatch_dedupes_and_worker_commits_only_drafts(db):
    from app.learning.dispatch import enqueue_due
    from app.learning.jobs import make_handlers
    from app.learning.models import AssetRevisionRow, BatchRow
    from app.learning.outbox import append
    from app.learning.schemas import LearningScope
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    seed = fresh_seed()
    await initialize(db, seed)
    scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
    cfg = settings(db, seed, learning_enabled=True, learning_generation_enabled=True)
    async with db.session() as session, session.begin():
        await enable(session, scope)
        for i in range(3):
            e = event(str(i))
            e.payload = {"business_date": f"2026-10-0{1 + i % 2}"}
            await append(session, scope=scope, event=e)
    async with db.session() as session, session.begin():
        ids = await enqueue_due(session, settings=cfg)
        assert len(ids) == 1
        assert await enqueue_due(session, settings=cfg) == []
        batch = await session.get(BatchRow, ids[0])
        job = await session.scalar(
            select(Job).where(
                Job.job_type == "learning_batch", Job.payload["batch_id"].astext == batch.id
            )
        )
        jobid = job.id

    async def generator(bundle, existing):
        return [
            {
                "spec": {
                    "title": "Delay check",
                    "task_family": "supply_delay_recovery",
                    "summary": "Check",
                    "inputs": ["case_id"],
                    "preconditions": ["current_case"],
                    "exclusions": ["unknown_execution"],
                    "required_tools": ["get_recovery_case"],
                    "procedure": ["Read inbound", "Compare"],
                    "outputs": ["comparison"],
                    "exceptions": ["Missing ETA"],
                },
                "evidence_ids": [e["id"] for e in bundle["events"]],
            }
        ]

    runner = Runner(db, cfg, handlers=make_handlers(cfg, generator=generator), job_ids=[jobid])
    assert await runner.run_once()
    async with db.session() as session:
        batch = await session.get(BatchRow, ids[0])
        assert batch.status == "SUCCEEDED"
        revs = list(
            await session.scalars(
                select(AssetRevisionRow).where(
                    AssetRevisionRow.asset_id.in_(batch.usage["asset_ids"])
                )
            )
        )
        assert len(revs) == 1 and revs[0].status == "DRAFT"
