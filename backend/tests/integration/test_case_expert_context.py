import asyncio

import pytest
from test_missions import clean_queue, environment, headers  # noqa: F401
from test_operations_cases import recovery_case

pytestmark = pytest.mark.integration


async def test_case_expert_hook_persists_shared_usage_and_replay_does_not_call_again(
    db, monkeypatch
):
    import shopsteward_agent

    class Model:
        calls = 0

        async def complete(self, messages, tools, **kwargs):
            self.calls += 1
            return {
                "content": '{"claims": [], "missing": [], "followup_requests": []}',
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }

    model = Model()
    monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: model)
    async with environment(db) as (seed, client):
        settings = client._transport.app.state.settings
        settings.agent_case_experts_enabled = True
        settings.agent_case_model = "test-model"
        settings.agent_api_key_file = "test-provider-does-not-read-this"
        settings.agent_max_input_tokens = 48000
        case = await recovery_case(db, seed, client)
        path = f"/api/v1/operations-cases/{case['id']}/analyze"
        request_headers = headers()
        first = await client.post(path, json={"expected_revision": 1}, headers=request_headers)
        assert first.status_code == 200, first.text
        analysis = first.json()["expert_analysis"]
        assert analysis["status"] == "complete"
        assert model.calls == 3
        assert analysis["budget"]["model_calls"] == 3
        assert analysis["usage"]["total_tokens"] == 45
        assert all(call["status"] == "completed" for call in analysis["call_records"])
        second = await client.post(path, json={"expected_revision": 1}, headers=request_headers)
        assert second.json()["expert_analysis"]["root_run_id"] == analysis["root_run_id"]
        assert model.calls == 3
        assert first.json()["plan_id"] is None


async def test_targeted_followup_is_charged_to_the_same_durable_ledger(db, monkeypatch):
    import json

    import shopsteward_agent

    class Model:
        calls = 0

        async def complete(self, messages, tools, **kwargs):
            self.calls += 1
            text = str(messages)
            ask = '"role": "impact"' in text and "recheck the arrival day" not in text
            return {
                "content": json.dumps(
                    {
                        "claims": [],
                        "missing": [],
                        "followup_requests": ["recheck the arrival day"] if ask else [],
                    }
                ),
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }

    model = Model()
    monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: model)
    async with environment(db) as (seed, client):
        settings = client._transport.app.state.settings
        settings.agent_case_experts_enabled = True
        settings.agent_case_model = "test-model"
        settings.agent_api_key_file = "test-provider-does-not-read-this"
        settings.agent_max_input_tokens = 48000
        case = await recovery_case(db, seed, client)
        path = f"/api/v1/operations-cases/{case['id']}/analyze"
        first = await client.post(path, json={"expected_revision": 1}, headers=headers())
        assert first.status_code == 200, first.text
        analysis = first.json()["expert_analysis"]
        assert analysis["strategy"] == "adaptive_multi"
        assert analysis["followup"]["subtask_id"] == "impact:followup"
        assert [item["subtask_id"] for item in analysis["subtasks"]][-1] == "impact:followup"
        assert analysis["budget"]["model_calls"] == model.calls == 4
        assert analysis["usage"]["total_tokens"] == 60
        assert len(analysis["call_records"]) == 4
        second = await client.post(path, json={"expected_revision": 1}, headers=headers())
        assert second.json()["expert_analysis"]["root_run_id"] == analysis["root_run_id"]
        assert model.calls == 4
        assert first.json()["plan_id"] is None


async def test_changed_case_revision_cannot_publish_old_expert_results(db, monkeypatch):
    import shopsteward_agent

    started, release = asyncio.Event(), asyncio.Event()

    class Model:
        async def complete(self, messages, tools, **kwargs):
            started.set()
            await release.wait()
            return {"content": '{"claims": [], "missing": []}'}

    monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: Model())
    async with environment(db) as (seed, client):
        settings = client._transport.app.state.settings
        settings.agent_case_experts_enabled = True
        settings.agent_case_model = "test-model"
        settings.agent_api_key_file = "unused-fake-path"
        settings.agent_max_input_tokens = 48000
        case = await recovery_case(db, seed, client)
        analysis = asyncio.create_task(
            client.post(
                f"/api/v1/operations-cases/{case['id']}/analyze",
                json={"expected_revision": 1},
                headers=headers(),
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        revised = await client.post(
            f"/api/v1/operations-cases/{case['id']}/revise",
            json={"expected_revision": 1, "budget_minor": 20000},
            headers=headers(),
        )
        assert revised.status_code == 200, revised.text
        release.set()
        result = await asyncio.wait_for(analysis, 10)
        assert result.json()["current_revision"] == 2
        assert result.json()["expert_analysis"] is None
        assert result.json()["proposal"] is None
        from sqlalchemy import select

        from app.agent_bridge.models import Receipt

        async with db.session() as session:
            history = (
                await session.scalars(
                    select(Receipt).where(Receipt.owner == f"case-context:{case['id']}:1")
                )
            ).all()
            assert len(history) == 1
            assert history[0].result["budget"]["model_calls"] >= 2
            assert any(call["status"] == "completed" for call in history[0].result["call_records"])


@pytest.mark.parametrize("change", ["cancel", "revoke"])
async def test_case_cancel_or_permission_revocation_stops_experts_but_keeps_accounting(
    db, monkeypatch, change
):
    import shopsteward_agent
    from sqlalchemy import select

    from app.agent_bridge.models import Receipt

    started, release = asyncio.Event(), asyncio.Event()

    class Model:
        calls = 0

        async def complete(self, messages, tools, **kwargs):
            self.calls += 1
            started.set()
            await release.wait()
            return {
                "content": '{"claims": [], "missing": []}',
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

    model = Model()
    monkeypatch.setattr(shopsteward_agent, "OpenAIModel", lambda **kwargs: model)
    async with environment(db) as (seed, client):
        settings = client._transport.app.state.settings
        settings.agent_case_experts_enabled = True
        settings.agent_case_model = "test-model"
        settings.agent_api_key_file = "unused-test-path"
        settings.agent_max_input_tokens = 48000
        case = await recovery_case(db, seed, client)
        analysis = asyncio.create_task(
            client.post(
                f"/api/v1/operations-cases/{case['id']}/analyze",
                json={"expected_revision": 1},
                headers=headers(),
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        if change == "cancel":
            cancelled = await client.post(
                f"/api/v1/operations-cases/{case['id']}/control",
                json={"expected_revision": 1, "operation": "cancel"},
                headers=headers(),
            )
            assert cancelled.status_code == 200
        else:
            settings.auth_tokens = [
                grant for grant in settings.auth_tokens if grant.principal_id != "operator"
            ]
        release.set()
        response = await asyncio.wait_for(analysis, 10)
        if change == "cancel":
            assert response.json()["status"] == "CANCELLED"
            assert response.json()["expert_analysis"] is None
        else:
            assert response.status_code == 403
        assert model.calls <= 2
        async with db.session() as session:
            history = (
                await session.scalars(
                    select(Receipt).where(Receipt.owner == f"case-context:{case['id']}:1")
                )
            ).all()
            assert len(history) == 1
            assert any(call["status"] == "completed" for call in history[0].result["call_records"])
