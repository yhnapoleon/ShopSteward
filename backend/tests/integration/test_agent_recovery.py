import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_missions import headers

pytestmark = pytest.mark.integration


async def test_event_foreign_key_does_not_block_while_conversation_is_locked(db):
    from app.agent_bridge.models import Conversation
    from app.agent_bridge.repository import visible_conversation
    from app.agent_bridge.triggers import record_event

    app, client, mission = await setup_agent(db)
    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        async with db.session() as session, session.begin():
            conversation = await session.get(Conversation, cid)
            conversation.followup_enabled = True
        principal = next(g for g in app.state.settings.auth_tokens if g.principal_id == "operator")
        async with db.session() as holder, holder.begin():
            await visible_conversation(holder, principal, cid, lock=True)
            async with asyncio.timeout(1):
                async with db.session() as writer, writer.begin():
                    await record_event(writer, mission["id"], "lock-compatible-event", [])
                    await writer.flush()
    await app.state.db.dispose()


async def test_interrupt_resume_idempotency_cancel_and_terminal_job_reconciliation(db):
    from app.agent_bridge.jobs import make_handlers
    from app.agent_bridge.models import AgentRun
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    seen = []

    async def execute(context):
        seen.append(context)
        if context["resume"]:
            return {
                "status": "SUCCEEDED",
                "content": "收到：" + context["resume"],
                "references": [],
            }
        return {
            "status": "WAITING_INPUT",
            "content": "",
            "references": [],
            "interrupt_id": "question1",
            "question": "希望比较哪个上限？",
        }

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        path = f"/api/v1/conversations/{cid}/messages"
        first = (await client.post(path, json={"content": "帮我调整"}, headers=headers())).json()[
            "agent_run_id"
        ]
        second = (await client.post(path, json={"content": "下一件事"}, headers=headers())).json()[
            "agent_run_id"
        ]
        runner = Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        )
        await runner.run_once()
        assert (await client.get(f"/api/v1/agent-runs/{first}", headers=headers())).json()[
            "status"
        ] == "WAITING_INPUT"
        assert [m["content"] for m in seen[0]["messages"]] == ["帮我调整"]
        bad = await client.post(
            f"/api/v1/agent-runs/{first}/resume",
            json={"interrupt_id": "wrong", "content": "20"},
            headers=headers(),
        )
        assert bad.status_code == 409
        auth = headers()
        reply = {"interrupt_id": "question1", "content": "20"}
        resumed = await client.post(f"/api/v1/agent-runs/{first}/resume", json=reply, headers=auth)
        assert resumed.status_code == 202
        assert (
            await client.post(f"/api/v1/agent-runs/{first}/resume", json=reply, headers=auth)
        ).json() == resumed.json()
        await runner.run_once()
        assert "下一件事" not in [m["content"] for m in seen[-1]["messages"]]
        async with db.session() as session, session.begin():
            run = await session.get(AgentRun, second)
            job = await session.get(Job, run.job_id)
            job.status = "RUNNING"
            job.lease_token = "old"
            job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
            job.attempt_count = 3
            run.status = "RUNNING"
        third = (await client.post(path, json={"content": "最后一件事"}, headers=headers())).json()[
            "agent_run_id"
        ]
        await runner.run_once()  # recover_expired marks job FAILED after before_claim
        await runner.run_once()  # reconciliation releases orphan active slot
        assert (await client.get(f"/api/v1/agent-runs/{second}", headers=headers())).json()[
            "status"
        ] == "FAILED"
        cancelled = await client.post(f"/api/v1/agent-runs/{third}/cancel", headers=headers())
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    await app.state.db.dispose()


async def test_followup_events_survive_running_and_unchanged_tick_is_silent(db):
    from app.agent_bridge.jobs import make_handlers
    from app.agent_bridge.models import AgentRun, Conversation, Trigger
    from app.agent_bridge.triggers import dispatch_followups, record_event
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    calls = 0

    async def execute(context):
        nonlocal calls
        calls += 1
        if calls == 1:
            async with db.session() as session, session.begin():
                await record_event(
                    session,
                    mission["id"],
                    "arrived-during-run",
                    [{"type": "mission", "id": mission["id"]}],
                )
        return {"status": "SUCCEEDED", "content": "跟进结果", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        config = await client.patch(
            f"/api/v1/conversations/{cid}/followup",
            json={"enabled": True, "expected_version": 1, "interval_seconds": 60},
            headers=headers(),
        )
        assert config.status_code == 200
        async with db.session() as session, session.begin():
            conversation = await session.get(Conversation, cid)
            conversation.next_due = datetime.now(UTC) - timedelta(seconds=1)
            await record_event(session, mission["id"], "before", [])
            await record_event(session, mission["id"], "before", [])
        await dispatch_followups(db, app.state.settings)
        runner = Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        )
        await runner.run_once()
        async with db.session() as session, session.begin():
            conversation = await session.get(Conversation, cid)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Trigger)
                    .where(
                        Trigger.conversation_id == cid, Trigger.seq > conversation.consumed_trigger
                    )
                )
                == 1
            )
            conversation.next_due = datetime.now(UTC) - timedelta(seconds=1)
        await dispatch_followups(db, app.state.settings)
        await runner.run_once()
        async with db.session() as session, session.begin():
            conversation = await session.get(Conversation, cid)
            conversation.next_due = datetime.now(UTC) - timedelta(seconds=1)
        await dispatch_followups(db, app.state.settings)
        async with db.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AgentRun)
                    .where(AgentRun.conversation_id == cid)
                )
                == 2
            )
        assert calls == 2
    await app.state.db.dispose()
