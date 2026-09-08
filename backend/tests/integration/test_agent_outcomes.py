"""Persisted outcomes use real business tools; document fixtures represent saved retrieval."""

import hashlib
from uuid import uuid4

import pytest
from test_agent_progress import queued
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_knowledge_documents import upload
from test_missions import headers

from app.agent_bridge.document_evidence import tool_result
from app.agent_bridge.jobs import make_handlers
from app.agent_bridge.models import ToolInvocation
from app.knowledge.models import KnowledgeDocument, KnowledgeVersion
from app.planning.jobs import make_handlers as planning
from app.scheduling.runner import Runner

pytestmark = pytest.mark.integration


async def test_real_evaluation_revision_replay_and_failure_preserve_outcomes(db):
    app, client, mission = await setup_agent(db)
    await Runner(db, app.state.settings, handlers=planning(app.state.settings)).run_once()
    captured = {}

    async def execute(context):
        auth = {"Authorization": "Bearer " + context["token"]}
        original = (await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())).json()
        args = {"plan_id": original["current_plan_id"], "max_purchase_qty": 20}
        for name in ("evaluate_plan", "revise_plan"):
            if name == "revise_plan":
                args["expected_mission_version"] = original["mission_version"]
            body = {"run_id": context["run_id"], "invocation_id": name, "arguments": args}
            r = await client.post("/internal/v1/agent-tools/" + name, json=body, headers=auth)
            assert r.status_code == 200 and r.json()["ok"], r.text
            captured[name] = r.json()
            assert (
                await client.post("/internal/v1/agent-tools/" + name, json=body, headers=auth)
            ).json() == r.json()
            if name == "evaluate_plan":
                assert (
                    await client.get(f"/api/v1/missions/{mission['id']}", headers=headers())
                ).json()["current_plan_id"] == original["current_plan_id"]
        return {
            "status": "FAILED",
            "content": "后续说明失败",
            "references": [],
            "error_code": "CONTROLLED_FAILURE",
        }

    async with client:
        rid = await queued(client, mission, "修改方案，最多20件，采购前让我确认")
        await Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        ).run_once()
        url = f"/api/v1/agent-runs/{rid}"
        r = await client.get(url, headers=headers())
        assert r.status_code == 200, r.text
        result = r.json()
        assert len(result["outcomes"]) == 2
        evaluation, revision = result["outcomes"]
        assert evaluation["availability"] == revision["availability"] == "available"
        assert evaluation["after"]["candidates"] == captured["evaluate_plan"]["data"]["candidates"]
        assert revision["before"]["plan_version"] == 1 and revision["after"]["plan_version"] == 2
        assert revision["before"]["plan_id"] == captured["revise_plan"]["data"]["base_plan_id"]
        assert revision["after"]["plan_id"] == captured["revise_plan"]["data"]["id"]
        assert (await client.get(url, headers=headers())).json()["outcomes"] == result["outcomes"]
        assert (await client.get(url, headers=headers("viewer"))).status_code == 404
        dashboard = (
            await client.get(
                "/api/v1/dashboard", params={"store_id": mission["store_id"]}, headers=headers()
            )
        ).json()
        assert (
            dashboard["state"]["cash_minor"] == 100000
            and dashboard["state"]["reserved_cash_minor"] == 0
        )
        assert (
            await client.get(
                "/api/v1/actions", params={"store_id": mission["store_id"]}, headers=headers()
            )
        ).json()["items"] == []
        async with db.session() as session, session.begin():
            row = await session.get(ToolInvocation, (rid, "revise_plan"))
            data = dict(row.result["data"])
            data.pop("base_plan_id")
            row.result = {**row.result, "data": data}
        old = (await client.get(url, headers=headers())).json()["outcomes"][1]
        assert old["availability"] == "unavailable" and old["before"] is None
    await app.state.db.dispose()


async def evidence_fixture(db, client, mission, rid):
    text = '<script>alert("untrusted")</script> 历史条款：最少20件。'
    doc = (
        await upload(
            client, mission["store_id"], content=text.encode(), metadata={"title": "原始供应商条款"}
        )
    ).json()
    candidate = {
        "document_id": doc["id"],
        "version_id": doc["latest_version_id"],
        "generation_id": str(uuid4()),
        "chunk_id": str(uuid4()),
        "metadata_revision": 1,
        "text": text,
        "title": "原始供应商条款",
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "locator": {"page": 1},
        "truncated": False,
    }
    result = tool_result({"candidates": [candidate]})
    async with db.session() as session, session.begin():
        session.add(
            ToolInvocation(
                run_id=rid,
                invocation_id="source",
                tool="search_documents",
                args_hash="fixture",
                result=result,
            )
        )
    params = {
        k: v
        for k, v in result["references"][0].items()
        if k
        in {"id", "version_id", "generation_id", "chunk_id", "metadata_revision", "content_sha256"}
    }
    return doc, candidate, params


async def test_historical_evidence_exact_version_permission_hash_and_archive(db, tmp_path):
    app, client, mission = await setup_agent(db)
    app.state.settings.knowledge_storage_root = str(tmp_path)
    async with client:
        rid = await queued(client, mission)
        doc, candidate, params = await evidence_fixture(db, client, mission, rid)
        url = f"/api/v1/agent-runs/{rid}/evidence"
        first = await client.get(url, params=params, headers=headers())
        assert first.status_code == 200, first.text
        assert first.json()["text"] == candidate["text"]
        async with db.session() as session:
            v = await session.get(KnowledgeVersion, doc["latest_version_id"])
            original_path = tmp_path / v.raw_key
        raw = original_path.read_bytes()
        original_path.unlink()
        assert (await client.get(url, params=params, headers=headers())).status_code == 404
        original_path.write_bytes(raw)
        async with db.session() as session, session.begin():
            row = await session.get(ToolInvocation, (rid, "source"))
            saved = row.result
            import copy

            damaged = copy.deepcopy(saved)
            damaged["data"]["candidates"][0]["text"] = "tampered"
            row.result = damaged
        assert (await client.get(url, params=params, headers=headers())).status_code == 404
        async with db.session() as session, session.begin():
            row = await session.get(ToolInvocation, (rid, "source"))
            row.result = saved
        newer = await upload(
            client,
            mission["store_id"],
            content=b"NEW DIFFERENT TERMS",
            url=f"/api/v1/documents/{doc['id']}/versions",
            metadata={"expected_metadata_version": 1},
        )
        assert newer.status_code == 201, newer.text
        assert (await client.get(url, params=params, headers=headers())).json() == first.json()
        assert (
            await client.get(
                url,
                params={**params, "version_id": newer.json()["latest_version_id"]},
                headers=headers(),
            )
        ).status_code == 404
        assert (
            await client.get(url, params={**params, "content_sha256": "0" * 64}, headers=headers())
        ).status_code == 404
        assert (await client.get(url, params=params, headers=headers("viewer"))).status_code == 404
        async with db.session() as session, session.begin():
            row = await session.get(KnowledgeDocument, doc["id"])
            row.visibility = "private"
            row.owner_principal_id = "someone-else"
        assert (await client.get(url, params=params, headers=headers())).status_code == 404
        async with db.session() as session, session.begin():
            row = await session.get(KnowledgeDocument, doc["id"])
            row.visibility = "store"
            row.status = "archived"
        assert (await client.get(url, params=params, headers=headers())).status_code == 404
    await app.state.db.dispose()
