from uuid import uuid4

import pytest
from sqlalchemy import select
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_learning_review_fixes import approved_fixture
from test_learning_storage import enable
from test_missions import headers

pytestmark = pytest.mark.integration


async def test_revocation_during_model_call_blocks_tool_and_final_publication(db):
    from app.agent_bridge.jobs import make_handlers
    from app.agent_bridge.models import AgentRun, Message
    from app.learning.lifecycle import change_policy
    from app.learning.retrieval import retrieve
    from app.learning.schemas import LearningScope, PolicyChange
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    app.state.settings.learning_enabled = True
    app.state.db.learning_enabled = True
    principal = next(p for p in app.state.settings.auth_tokens if p.principal_id == "operator")
    scope = LearningScope(principal_id="operator", store_id=mission["store_id"])
    async with db.session() as s, s.begin():
        await enable(s, scope)
        await approved_fixture(s, scope, app.state.settings, principal)
    observed = {}

    async def execute(context):
        async with db.session() as s, s.begin():
            skills = await retrieve(
                s,
                scope=scope,
                family="replenishment",
                facts={"current_mission": True, "unknown_execution": False},
                settings=app.state.settings,
                principal=principal,
                run_id=context["run_id"],
            )
            assert len(skills) == 1
        # A user's opt-out lands while the fake model request is in flight.
        async with db.session() as s, s.begin():
            await change_policy(
                s, scope=scope, body=PolicyChange(expected_version=1, mode="off"), key=str(uuid4())
            )
        observed["tool"] = await client.post(
            "/internal/v1/agent-tools/request_check",
            headers={"Authorization": "Bearer " + context["token"]},
            json={
                "run_id": context["run_id"],
                "invocation_id": "stale-model-write",
                "arguments": {"reason": "Old inferred skill"},
            },
        )
        return {"status": "SUCCEEDED", "content": "Old skill answer", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        rid = (
            await client.post(
                f"/api/v1/conversations/{cid}/messages",
                json={"content": "看看当前计划"},
                headers=headers(),
            )
        ).json()["agent_run_id"]
        runner = Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        )
        assert await runner.run_once()
        assert observed["tool"].status_code == 409, observed["tool"].text
        async with db.session() as s:
            run = await s.get(AgentRun, rid)
            assert run.status == "FAILED"
            assert run.error_code == "LEARNING_CONTEXT_CHANGED"
            assert not await s.scalar(
                select(Message).where(Message.run_id == rid, Message.role == "assistant")
            )
    await app.state.db.dispose()


async def test_successful_explicit_memory_edit_clears_pin_and_can_finish(db):
    from app.agent_bridge.jobs import make_handlers
    from app.agent_bridge.models import AgentRun
    from app.learning.retrieval import retrieve
    from app.learning.run_binding import selection
    from app.learning.schemas import LearningScope
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    app.state.settings.learning_enabled = True
    app.state.db.learning_enabled = True
    principal = next(p for p in app.state.settings.auth_tokens if p.principal_id == "operator")
    scope = LearningScope(principal_id="operator", store_id=mission["store_id"])
    async with db.session() as s, s.begin():
        await enable(s, scope)
        await approved_fixture(s, scope, app.state.settings, principal)

    async def execute(context):
        async with db.session() as s, s.begin():
            assert await retrieve(
                s,
                scope=scope,
                family="replenishment",
                facts={"current_mission": True, "unknown_execution": False},
                settings=app.state.settings,
                principal=principal,
                run_id=context["run_id"],
            )
        response = await client.post(
            "/internal/v1/agent-tools/memory_edit",
            headers={"Authorization": "Bearer " + context["token"]},
            json={
                "run_id": context["run_id"],
                "invocation_id": "explicit-write",
                "arguments": {
                    "kind": "USER",
                    "operation": "add",
                    "content": "先说明风险",
                    "expected_version": 0,
                },
            },
        )
        assert response.status_code == 200 and response.json()["ok"], response.text
        return {"status": "SUCCEEDED", "content": "已保存偏好", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        rid = (
            await client.post(
                f"/api/v1/conversations/{cid}/messages",
                json={"content": "请记住先说明风险"},
                headers=headers(),
            )
        ).json()["agent_run_id"]
        runner = Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        )
        assert await runner.run_once()
        async with db.session() as s:
            assert (await s.get(AgentRun, rid)).status == "SUCCEEDED"
            frozen = await selection(s, scope, rid)
            assert frozen.result["assets"] == [] and frozen.result["policy_version"] == 2
    await app.state.db.dispose()
