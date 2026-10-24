import os
from uuid import uuid4

import pytest
from langgraph.checkpoint.base import empty_checkpoint

from shopsteward_agent import FencedPostgresSaver


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["aput", "aput_writes"])
async def test_post_write_fence_rolls_back_official_saver(operation):
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("dedicated TEST_DATABASE_URL required")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    calls = 0

    async def fence(conn):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("lost lease after write")

    saver = FencedPostgresSaver(dsn, fence)
    await saver.setup()
    config = {"configurable": {"thread_id": str(uuid4()), "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    if operation == "aput":
        with pytest.raises(RuntimeError, match="lost lease"):
            await saver.aput(config, checkpoint, {"source": "input", "step": 0, "parents": {}}, {})
        assert await saver.aget_tuple(config) is None
    else:

        async def valid(conn):
            pass

        good = FencedPostgresSaver(dsn, valid)
        config = await good.aput(
            config, checkpoint, {"source": "input", "step": 0, "parents": {}}, {}
        )
        with pytest.raises(RuntimeError, match="lost lease"):
            await saver.aput_writes(config, [("answer", "must rollback")], "test-task")
        restored = await good.aget_tuple(config)
        assert restored.pending_writes == []


@pytest.mark.asyncio
async def test_real_postgres_graph_restart_interrupt():
    from test_runtime import Model, call, context, tool

    from shopsteward_agent import Runtime

    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("dedicated TEST_DATABASE_URL required")

    async def fence(conn):
        pass

    saver = FencedPostgresSaver(dsn.replace("postgresql+asyncpg://", "postgresql://"), fence)
    await saver.setup()
    run_id = str(uuid4())
    first = Runtime(
        Model([{"tool_calls": [call("clarify", '{"question":"Which?"}')]}]),
        saver,
        [],
        tool,
        context,
    )
    assert (await first.execute(run_id, []))["status"] == "WAITING_INPUT"
    restarted = Runtime(Model([{"content": "Recovered"}]), saver, [], tool, context)
    assert (await restarted.execute(run_id, [], resume="A"))["content"] == "Recovered"
