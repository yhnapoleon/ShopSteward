import pytest
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_missions import headers

pytestmark = pytest.mark.integration


async def test_knowledge_versions_owner_isolation_and_delete(db):
    app, client, mission = await setup_agent(db)
    async with client:
        path = f"/api/v1/stores/{mission['store_id']}/agent-knowledge"
        change = {
            "kind": "USER",
            "operation": "add",
            "content": "先现金，再库存",
            "expected_version": 0,
        }
        saved = await client.post(path, json=change, headers=headers())
        assert saved.status_code == 200, saved.text
        scope = saved.json()
        assert scope["version"] == 1
        assert (await client.post(path, json=change, headers=headers())).status_code == 409
        assert (await client.get(path, headers=headers("viewer"))).json()["items"] == []
        change.update(
            operation="remove", entry_id=scope["entries"][0]["id"], content="", expected_version=1
        )
        deleted = await client.post(path, json=change, headers=headers())
        assert deleted.json()["entries"] == [] and deleted.json()["version"] == 2
        skill = {
            "kind": "SKILL",
            "task_type": "replenishment",
            "operation": "add",
            "content": "补货方案先比较现金风险，再说明缺货差异",
            "expected_version": 0,
            "required_tools": ["get_plan"],
        }
        assert (await client.post(path, json=skill, headers=headers())).status_code == 200
        skill.update(expected_version=1, required_tools=["approve_plan"], content="执行审批")
        assert (await client.post(path, json=skill, headers=headers())).status_code == 422
    await app.state.db.dispose()
