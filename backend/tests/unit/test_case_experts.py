import pytest

from app.core.config import Settings


@pytest.mark.asyncio
async def test_case_input_overflow_obeys_configured_budget_before_any_model_send():
    from app.agent_bridge.context_cases import analyze_case_experts

    class Model:
        calls = 0

        async def complete(self, messages, tools, **kwargs):
            self.calls += 1
            return {"content": '{"claims": [], "missing": [], "followup_requests": []}'}

    model = Model()
    result = await analyze_case_experts(
        {"recovery": {"store_id": "s", "sku_id": "sku", "offers": [], "daily_demand": []}},
        case_id="case",
        revision_id="1",
        run_id="small-budget",
        settings=Settings(agent_case_experts_enabled=True, agent_max_input_tokens=256),
        model=model,
    )
    assert model.calls == 0
    assert result["status"] == "partial"
    assert all(task["status"] == "failed" for task in result["subtasks"])
    assert "CONTEXT_REQUIRED_OVERFLOW" in str(result)
    assert result["profile"]["max_input_tokens"] == 256


@pytest.mark.asyncio
async def test_case_experts_share_frozen_solver_evidence_without_changing_proposal():
    from app.agent_bridge.context_cases import analyze_case_experts

    class Model:
        async def complete(self, messages, tools, **kwargs):
            return {
                "content": (
                    '{"claims": [], "missing": ["No document supplied"], "followup_requests": []}'
                )
            }

    proposal = {
        "id": "proposal",
        "recommended_candidate_id": "wait",
        "candidates": [{"id": "wait", "quantity": 0}],
    }
    result = await analyze_case_experts(
        {"recovery": {"store_id": "store", "sku_id": "sku", "offers": [], "daily_demand": []}},
        case_id="case",
        revision_id="1",
        run_id="run",
        settings=Settings(agent_case_experts_enabled=True),
        proposal=proposal,
        model=Model(),
    )
    assert result["status"] == "partial"
    assert result["budget"]["model_calls"] == 2
    assert result["usage"] is None
    assert result["cost_status"] == "unknown"
    assert proposal["candidates"][0]["quantity"] == 0
    assert {record["role"] for record in result["call_records"]} == {"evidence", "impact"}


def recovery_snapshot(*suppliers):
    return {
        "recovery": {
            "store_id": "store",
            "sku_id": "sku",
            "offers": [{"supplier_id": supplier} for supplier in suppliers],
            "daily_demand": [],
        }
    }


class Agreeable:
    async def complete(self, messages, tools, **kwargs):
        return {"content": '{"claims": [], "missing": [], "followup_requests": []}'}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "roles"),
    [
        ("fixed", {"fixed"}),
        ("single", {"single"}),
        ("static_multi", {"evidence", "impact", "options"}),
        ("adaptive_multi", {"evidence", "impact"}),
    ],
)
async def test_each_strategy_runs_on_the_same_evidence_and_root_budget(strategy, roles):
    from app.agent_bridge.context_cases import analyze_case_experts

    proposal = {"id": "proposal", "candidates": [{"id": "b", "quantity": 20, "feasible": True}]}
    result = await analyze_case_experts(
        recovery_snapshot("b"),
        case_id="case",
        revision_id="1",
        run_id="run",
        settings=Settings(agent_case_experts_enabled=True, agent_case_strategy=strategy),
        proposal=proposal,
        model=Agreeable(),
    )
    assert {record["role"] for record in result["call_records"]} == roles
    assert (result["strategy"], result["routing"]["forced"]) == (strategy, False)
    assert result["routing"]["signals"] == {"offer_count": 1, "feasible_purchases": 1}
    assert (result["budget"]["max_model_calls"], result["budget"]["max_tool_calls"]) == (14, 28)
    assert result["advisory_only"] is True


@pytest.mark.asyncio
async def test_options_expert_joins_only_when_the_solver_found_no_feasible_purchase():
    from app.agent_bridge.context_cases import analyze_case_experts

    proposal = {
        "id": "proposal",
        "candidates": [
            {"id": "wait", "quantity": 0, "feasible": True},
            {"id": "a", "quantity": 40, "feasible": False},
        ],
    }
    result = await analyze_case_experts(
        recovery_snapshot("a"),
        case_id="case",
        revision_id="1",
        run_id="run",
        settings=Settings(agent_case_experts_enabled=True),
        proposal=proposal,
        model=Agreeable(),
    )
    assert result["routing"]["roles"]["options"] == "no_feasible_purchase"
    assert result["routing"]["signals"] == {"offer_count": 1, "feasible_purchases": 0}


@pytest.mark.asyncio
async def test_research_override_and_role_models_are_recorded_not_inferred():
    from pydantic import ValidationError

    from app.agent_bridge.context_cases import analyze_case_experts

    settings = Settings(
        agent_case_experts_enabled=True,
        agent_case_model="main",
        agent_case_role_models={"evidence": "light"},
    )
    result = await analyze_case_experts(
        recovery_snapshot("a", "b"),
        case_id="case",
        revision_id="1",
        run_id="run",
        settings=settings,
        strategy="static_multi",
        model=Agreeable(),
    )
    assert (result["strategy_id"], result["routing"]["forced"]) == ("R2", True)
    assert {role: profile["model_id"] for role, profile in result["profiles"].items()} == {
        "evidence": "light",
        "impact": "main",
        "options": "main",
    }
    assert {(r["role"], r["profile"]["model_id"]) for r in result["call_records"]} == {
        ("evidence", "light"),
        ("impact", "main"),
        ("options", "main"),
    }
    with pytest.raises(ValidationError):
        Settings(agent_case_role_models={"auditor": "main"})
    with pytest.raises(ValidationError):
        Settings(agent_case_strategy="debate")


def test_case_publication_fence_rejects_cancelled_run_and_live_permission_revocation():
    from types import SimpleNamespace

    from app.agent_bridge.context_cases import case_current, current_case_principal
    from app.core.errors import AppError

    row = SimpleNamespace(
        current_revision=1,
        proposal_id="p",
        expert_analysis={"root_run_id": "r"},
        status="CANCELLED",
    )
    assert not case_current(row, 1, "p", "r")
    grant = SimpleNamespace(principal_id="u", kind="user", roles=["operator"], store_ids=["s"])
    settings = SimpleNamespace(auth_tokens=[grant])
    assert current_case_principal(settings, "u", "s") is grant
    settings.auth_tokens = []
    with pytest.raises(AppError, match="access"):
        current_case_principal(settings, "u", "s")
