from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from test_missions import body, fresh_seed, headers, settings
from test_operations import initialize

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def clean_agent(db):
    async with db.session() as session, session.begin():
        for table in [
            "agent_tool_calls",
            "agent_messages",
            "agent_runs",
            "agent_triggers",
            "agent_conversations",
            "agent_receipts",
        ]:
            await session.execute(text(f"DELETE FROM {table}"))
        await session.execute(text("DELETE FROM job_runs"))


async def setup_agent(db):
    from app.main import create_app

    seed = fresh_seed()
    await initialize(db, seed)
    from app.operations.repository import mark_caught_up

    async with db.session() as session, session.begin():
        await mark_caught_up(session, seed["scenario_run_id"], 0)
    app = create_app(settings(db, seed, agent_enabled=True))
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    mission = (await client.post("/api/v1/missions", json=body(seed), headers=headers())).json()
    await client.aclose()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return app, client, mission


async def test_message_replay_queue_and_owner_isolation(db):
    from app.agent_bridge.models import AgentRun, Conversation, Message

    app, client, mission = await setup_agent(db)
    async with client:
        path = f"/api/v1/missions/{mission['id']}/conversations"
        response = await client.post(path, json={}, headers=headers())
        assert response.status_code == 201, response.text
        cid = response.json()["id"]
        path = f"/api/v1/conversations/{cid}/messages"
        key = str(uuid4())
        first = await client.post(path, json={"content": "先看现金"}, headers=headers(key=key))
        assert first.status_code == 202, first.text
        replay = await client.post(path, json={"content": "先看现金"}, headers=headers(key=key))
        assert replay.json() == first.json()
        conflict = await client.post(path, json={"content": "改了"}, headers=headers(key=key))
        assert conflict.status_code == 409
        second = await client.post(path, json={"content": "再看库存"}, headers=headers())
        assert second.status_code == 202
        assert (await client.get(path, headers=headers("viewer"))).status_code == 404
        async with db.session() as session:
            conversation = await session.get(Conversation, cid)
            runs = (
                await session.scalars(select(AgentRun).where(AgentRun.conversation_id == cid))
            ).all()
            messages = (
                await session.scalars(select(Message).where(Message.conversation_id == cid))
            ).all()
            assert len(messages) == 2 and len(runs) == 2
            assert sum(run.job_id is not None for run in runs) == 1
            assert conversation.active_run_id == first.json()["agent_run_id"]
    await app.state.db.dispose()


async def test_worker_publishes_once_and_promotes_next_message(db):
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)

    async def execute(context):
        if context["messages"][-1]["content"] == "第二条":
            assert [m["role"] for m in context["messages"]] == ["user", "assistant", "user"]
        return {"status": "SUCCEEDED", "content": "已读取", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        path = f"/api/v1/conversations/{cid}/messages"
        for content in ["第一条", "第二条"]:
            assert (
                await client.post(path, json={"content": content}, headers=headers())
            ).status_code == 202
        runner = Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        )
        await runner.run_once()
        await runner.run_once()
        messages = (await client.get(path, headers=headers())).json()["items"]
        assert [m["content"] for m in messages if m["role"] == "assistant"] == ["已读取", "已读取"]
        assert len({m["run_id"] for m in messages if m["role"] == "assistant"}) == 2
    await app.state.db.dispose()
