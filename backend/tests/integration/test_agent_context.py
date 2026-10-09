from uuid import uuid4

import pytest
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_missions import headers

pytestmark = pytest.mark.integration


async def test_gateway_saves_explicit_preference_while_denied_plan_stays_unchanged(db):
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    results = {}

    async def execute(context):
        for tool, args in [
            ("memory_edit", {"kind": "USER", "operation": "add",
                             "content": "先结论", "expected_version": 0}),
            ("request_check", {}),
            ("revise_plan", {"plan_id": "irrelevant", "max_purchase_qty": 20,
                             "expected_mission_version": 1}),
        ]:
            response = await client.post(
                f"/internal/v1/agent-tools/{tool}",
                headers={"Authorization": "Bearer " + context["token"]},
                json={"run_id": context["run_id"], "invocation_id": tool, "arguments": args},
            )
            results[tool] = response.json()
        return {"status": "SUCCEEDED", "content": "done", "references": []}

    async with client:
        cid = (await client.post(
            f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
        )).json()["id"]
        await client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "请保存这个偏好：先结论，不要修改当前方案"}, headers=headers(),
        )
        await Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        ).run_once()
        assert results["memory_edit"]["ok"] is True, results
        assert results["request_check"]["error"]["code"] == "EXPLICIT_READ_ONLY"
        assert results["revise_plan"]["error"]["code"] == "EXPLICIT_READ_ONLY"
        knowledge = (await client.get(
            f"/api/v1/stores/{mission['store_id']}/agent-knowledge", headers=headers()
        )).json()
        assert knowledge["items"][0]["entries"][0]["content"] == "先结论"
        current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        assert current["mission_version"] == mission["mission_version"]
    await app.state.db.dispose()


async def test_worker_admission_retains_early_constraint_and_inspector_is_owner_scoped(db):
    from app.agent_bridge.context_repository import save_call
    from app.agent_bridge.jobs import make_handlers
    from app.agent_bridge.models import AgentRun, Conversation, Message
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    seen = []

    async def execute(context):
        seen.append(context)
        async with db.session() as session, session.begin():
            await session.get(AgentRun, context["run_id"], with_for_update=True)
            record = {
                "run_id": context["run_id"],
                "call_index": 1,
                "role": "root",
                "status": "reserved",
                "request_hash": "known-request",
                "manifest": {"selected_source_ids": ["early"]},
                "usage": None,
                "cost_status": "unknown",
            }
            await save_call(session, context["run_id"], record)
        return {
            "status": "SUCCEEDED",
            "content": "done",
            "references": [],
            "context_frame": {"frame_id": "frame", "source_message_ids": ["early"]},
        }

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        async with db.session() as session, session.begin():
            conversation = await session.get(Conversation, cid)
            for index in range(81):
                run_id = str(uuid4())
                session.add(
                    AgentRun(
                        id=run_id,
                        conversation_id=cid,
                        input_through_seq=index * 2 + 1,
                        status="SUCCEEDED",
                    )
                )
                await session.flush()
                session.add(
                    Message(
                        id="early" if index == 0 else str(uuid4()),
                        conversation_id=cid,
                        seq=index * 2 + 1,
                        role="user",
                        content="预算最多200元" if index == 0 else f"turn {index}",
                        run_id=run_id,
                    )
                )
                session.add(
                    Message(
                        id=str(uuid4()),
                        conversation_id=cid,
                        seq=index * 2 + 2,
                        role="assistant",
                        content="ack",
                        run_id=run_id,
                    )
                )
            conversation.next_seq = 163
        first = (
            await client.post(
                f"/api/v1/conversations/{cid}/messages",
                json={"content": "evaluate now"},
                headers=headers(),
            )
        ).json()
        await client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "FUTURE SECRET"},
            headers=headers(),
        )
        runner = Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        )
        await runner.run_once()
        assert seen and seen[0]["messages"][0]["content"] == "预算最多200元"
        assert "FUTURE SECRET" not in str(seen[0]["messages"])
        assert len(seen[0]["messages"]) == 163
        endpoint = f"/api/v1/agent-runs/{first['agent_run_id']}/context"
        response = await client.get(endpoint, headers=headers())
        assert response.status_code == 200, response.text
        assert response.json()["calls"][0]["status"] == "reserved"
        assert response.json()["calls"][0]["usage"] is None
        assert response.json()["config"]["enabled"] is True
        assert (await client.get(endpoint, headers=headers("viewer"))).status_code == 404
        from app.core.errors import AppError

        async with db.session() as session, session.begin():
            with pytest.raises(AppError, match="outcome"):
                await save_call(session, first["agent_run_id"], response.json()["calls"][0])
    await app.state.db.dispose()


@pytest.mark.parametrize("question", [
    "只试算最多20件，不要保存",
    "只试算，不要保存，数量上限改成20件",
    "不要保存，先把数量上限改成20件试算一下",
])
async def test_gateway_enforces_no_save_even_if_model_requests_mutation(db, question):
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    outcomes = []

    async def execute(context):
        for name, arguments in [
            ("request_check", {}),
            (
                "revise_plan",
                {"plan_id": "irrelevant", "max_purchase_qty": 20, "expected_mission_version": 1},
            ),
            (
                "memory_edit",
                {"kind": "USER", "operation": "add", "content": "prefer A", "expected_version": 0},
            ),
            ("analyze_recovery_case", {"case_id": "irrelevant", "expected_revision": 1}),
        ]:
            response = await client.post(
                f"/internal/v1/agent-tools/{name}",
                headers={"Authorization": "Bearer " + context["token"]},
                json={"run_id": context["run_id"], "invocation_id": name, "arguments": arguments},
            )
            outcomes.append(response.json())
        return {"status": "SUCCEEDED", "content": "read only", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        await client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": question},
            headers=headers(),
        )
        await Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        ).run_once()
        assert len(outcomes) == 4
        assert all(result["ok"] is False for result in outcomes)
        assert {result["error"]["code"] for result in outcomes} <= {
            "EXPLICIT_READ_ONLY",
            "EXPLICIT_MEMORY_INTENT_REQUIRED",
        }
        current = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        assert current["mission_version"] == mission["mission_version"]
    await app.state.db.dispose()
