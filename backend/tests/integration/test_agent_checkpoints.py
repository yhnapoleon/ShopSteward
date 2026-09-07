from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from langgraph.checkpoint.base import empty_checkpoint

from app.agent_bridge.checkpoint_fence import make_fence
from app.scheduling.models import Job
from app.scheduling.repository import claim, enqueue, recover_expired

pytestmark = pytest.mark.integration


async def test_live_old_writer_cannot_commit_after_new_worker_reclaims_lease(db):
    from shopsteward_agent import FencedPostgresSaver, RuntimeFailure

    async with db.session() as session, session.begin():
        queued = await enqueue(session, job_type="worker_probe", dedup_key="fence-" + str(uuid4()))
        queued.available_at = datetime(1970, 1, 1, tzinfo=UTC)
        await session.flush()
        old = await claim(session, lease_seconds=30, job_types=["worker_probe"])
        assert old.id == queued.id
    dsn = db.engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    saver = FencedPostgresSaver(dsn, make_fence(old.id, old.lease_token))
    await saver.setup()
    config = {"configurable": {"thread_id": "fence-" + str(uuid4()), "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    saved = await saver.aput(config, checkpoint, {"source": "input", "step": -1, "parents": {}}, {})
    await saver.aput_writes(saved, [("result", "valid")], "accepted")
    async with db.session() as session, session.begin():
        current = await session.get(Job, old.id, with_for_update=True)
        current.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.flush()
        await recover_expired(session, retry_safe_types=["worker_probe"])
        current.available_at = datetime(1970, 1, 1, tzinfo=UTC)
        await session.flush()
        replacement = await claim(session, lease_seconds=30, job_types=["worker_probe"])
        assert replacement.id == old.id and replacement.lease_token != old.lease_token
        assert replacement.attempt_count == 2
    before = await saver.aget_tuple(saved)
    with pytest.raises(RuntimeFailure, match="lease_lost"):
        await saver.aput_writes(saved, [("result", "stale")], "stale")
    with pytest.raises(RuntimeFailure, match="lease_lost"):
        await saver.aput(
            config, empty_checkpoint(), {"source": "loop", "step": 0, "parents": {}}, {}
        )
    after = await saver.aget_tuple(saved)
    assert after.checkpoint == before.checkpoint and after.pending_writes == before.pending_writes
    assert after.pending_writes == [("accepted", "result", "valid")]
    async with db.session() as session, session.begin():
        current = await session.get(Job, old.id)
        current.status = "SUCCEEDED"
        current.lease_until = current.lease_token = None
