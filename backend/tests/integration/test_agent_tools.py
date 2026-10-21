import pytest
from sqlalchemy import select
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_missions import headers

pytestmark = pytest.mark.integration


async def test_clarification_denial_revokes_original_memory_write_intent(db):
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    results = {}

    async def execute(context):
        if context["resume"] is None:
            return {
                "status": "WAITING_INPUT",
                "content": "",
                "references": [],
                "interrupt_id": "memory-question",
                "question": "要保存什么偏好？",
            }
        response = await client.post(
            "/internal/v1/agent-tools/memory_edit",
            headers={"Authorization": "Bearer " + context["token"]},
            json={
                "run_id": context["run_id"],
                "invocation_id": "denied-write",
                "arguments": {
                    "kind": "USER",
                    "operation": "add",
                    "content": "先风险",
                    "expected_version": 0,
                },
            },
        )
        results["write"] = response.json()
        return {"status": "SUCCEEDED", "content": "收到", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        rid = (
            await client.post(
                f"/api/v1/conversations/{cid}/messages",
                json={"content": "请记住我的偏好"},
                headers=headers(),
            )
        ).json()["agent_run_id"]
        runner = Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        )
        await runner.run_once()
        response = await client.post(
            f"/api/v1/agent-runs/{rid}/resume",
            json={"interrupt_id": "memory-question", "content": "请不要保存这个偏好"},
            headers=headers(),
        )
        assert response.status_code == 202
        await runner.run_once()
        assert results["write"]["ok"] is False
        assert results["write"]["error"]["code"] == "EXPLICIT_MEMORY_INTENT_REQUIRED"
        knowledge = await client.get(
            f"/api/v1/stores/{mission['store_id']}/agent-knowledge", headers=headers()
        )
        assert knowledge.json()["items"] == []
    await app.state.db.dispose()


async def test_tool_receipt_replay_scope_restriction_and_token_revocation(db):
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    results = {}

    async def execute(context):
        auth = {"Authorization": "Bearer " + context["token"]}
        payload = {"run_id": context["run_id"], "invocation_id": "read1", "arguments": {}}
        path = "/internal/v1/agent-tools/get_mission"
        results["first"] = await client.post(path, json=payload, headers=auth)
        results["replay"] = await client.post(path, json=payload, headers=auth)
        results["forbidden"] = await client.post(
            "/internal/v1/agent-tools/approve_plan", json=payload, headers=auth
        )
        payload["arguments"] = {"store_id": "foreign"}
        results["scope"] = await client.post(path, json=payload, headers=auth)
        payload.update(invocation_id="check1", arguments={"reason": "检查"})
        results["check1"] = await client.post(
            "/internal/v1/agent-tools/request_check", json=payload, headers=auth
        )
        results["check2"] = await client.post(
            "/internal/v1/agent-tools/request_check", json=payload, headers=auth
        )
        payload["arguments"] = {"reason": "different"}
        results["conflict"] = await client.post(
            "/internal/v1/agent-tools/request_check", json=payload, headers=auth
        )
        results["auth"], results["payload"] = auth, payload
        return {"status": "SUCCEEDED", "content": "已查询", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        await client.post(
            f"/api/v1/conversations/{cid}/messages", json={"content": "查询任务"}, headers=headers()
        )
        await Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        ).run_once()
        assert results["first"].status_code == 200, results["first"].text
        assert results["replay"].json() == results["first"].json()
        assert results["forbidden"].status_code == 403
        assert results["scope"].status_code == 422
        assert results["check1"].status_code == 200, results["check1"].text
        assert results["check1"].json() == results["check2"].json()
        assert results["conflict"].status_code == 409
        expired = await client.post(
            "/internal/v1/agent-tools/request_check",
            json=results["payload"],
            headers=results["auth"],
        )
        assert expired.status_code == 401
    await app.state.db.dispose()


@pytest.mark.parametrize("question", [
    "这次修改方案，最多采购20件",
    "请把方案修改为最多20件，不要下单",
])
async def test_whatif_is_readonly_and_explicit_revision_preserves_policy_and_old_plan(db, question):
    from app.agent_bridge.jobs import make_handlers
    from app.missions.models import MissionRow, PlanRow
    from app.planning.jobs import make_handlers as planning
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    await Runner(db, app.state.settings, handlers=planning(app.state.settings)).run_once()
    results = {}

    async def execute(context):
        from app.agent_bridge.models import Message

        async with db.session() as session:
            source = await session.scalar(
                select(Message).where(Message.run_id == context["run_id"])
            )
            row = await session.get(MissionRow, mission["id"])
            original = await session.get(PlanRow, row.current_plan_id)
            results["original"] = dict(original.document)
            results["policy"] = dict(row.policy)
        auth = {"Authorization": "Bearer " + context["token"]}
        args = {"plan_id": original.id, "max_purchase_qty": 20}
        payload = {"run_id": context["run_id"], "invocation_id": "whatif", "arguments": args}
        results["whatif"] = await client.post(
            "/internal/v1/agent-tools/evaluate_plan", json=payload, headers=auth
        )
        async with db.session() as session:
            row = await session.get(MissionRow, mission["id"])
            results["after_whatif"] = (
                row.current_plan_id,
                row.mission_version,
                dict(row.task_constraints),
            )
        args.update(
            expected_mission_version=mission["mission_version"], source_message_id=source.id
        )
        payload.update(invocation_id="revision", arguments=args)
        results["revision"] = await client.post(
            "/internal/v1/agent-tools/revise_plan", json=payload, headers=auth
        )
        return {"status": "SUCCEEDED", "content": "已修订", "references": []}

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
        assert results["whatif"].status_code == 200, results["whatif"].text
        assert results["whatif"].json()["data"]["recommended_candidate_id"] == "candidate_20"
        assert results["after_whatif"] == (results["original"]["id"], 1, {})
        assert results["revision"].status_code == 200, results["revision"].text
        new = results["revision"].json()["data"]
        assert new["proposed_purchase"]["quantity"] == 20
        assert new["proposal_hash"] != results["original"]["proposal_hash"]
        async with db.session() as session:
            row = await session.get(MissionRow, mission["id"])
            old = await session.get(PlanRow, results["original"]["id"])
            assert row.policy == results["policy"]
            assert old.document == results["original"] and old.status == "SUPERSEDED"
            assert row.task_constraints == {"max_purchase_qty": 20}
    await app.state.db.dispose()


async def test_tool_data_names_suppliers_states_validity_and_saves_a_memory_once(db):
    from app.agent_bridge.jobs import make_handlers
    from app.operations.models import OfferRow
    from app.planning.jobs import make_handlers as planning
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    await Runner(db, app.state.settings, handlers=planning(app.state.settings)).run_once()
    async with db.session() as session, session.begin():
        offer = await session.get(OfferRow, (mission["store_id"], "sku_001", "supplier_001"))
        offer.document = offer.document | {"supplier_name": "Huaxin Dairy"}
    results = {}

    async def execute(context):
        auth = {"Authorization": "Bearer " + context["token"]}

        async def call(name, invocation, arguments=None):
            response = await client.post(
                f"/internal/v1/agent-tools/{name}",
                json={
                    "run_id": context["run_id"],
                    "invocation_id": invocation,
                    "arguments": arguments or {},
                },
                headers=auth,
            )
            return response.json()

        results["plan"] = await call("get_plan", "plan")
        change = {
            "kind": "USER",
            "operation": "add",
            "content": "I don't take deliveries on weekends.",
            "expected_version": 0,
        }
        results["saved"] = await call("memory_edit", "first", change)
        results["again"] = await call("memory_edit", "again", change | {"expected_version": 1})
        return {"status": "SUCCEEDED", "content": "Saved.", "references": []}

    async with client:
        cid = (
            await client.post(
                f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
            )
        ).json()["id"]
        await client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "Remember: I don’t take deliveries on weekends."},
            headers=headers(),
        )
        await Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        ).run_once()
        plan = results["plan"]["data"]
        assert plan["supplier_names"] == {"supplier_001": "Huaxin Dairy"}
        assert plan["input_snapshot"]["offer"]["supplier_name"] == "Huaxin Dairy"
        # The verdict the product applies, not a wall-clock deadline to compare.
        assert (plan["status"], plan["expired"]) == ("PENDING_APPROVAL", False)
        assert "expires_at" not in plan and "expires_at_local" not in plan
        assert "valid_until" not in plan["input_snapshot"]["offer"]
        assert results["saved"]["ok"] is True
        assert results["again"]["ok"] is False
        assert results["again"]["error"]["code"] == "MEMORY_ALREADY_SAVED"
        knowledge = await client.get(
            f"/api/v1/stores/{mission['store_id']}/agent-knowledge", headers=headers()
        )
        entries = [e for scope in knowledge.json()["items"] for e in scope["entries"]]
        assert [e["content"] for e in entries] == ["I don't take deliveries on weekends."]
    await app.state.db.dispose()
