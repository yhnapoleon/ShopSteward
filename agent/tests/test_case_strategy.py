import json

import pytest

EXPERTS = ("evidence", "impact", "options")
TOOLS = [
    {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
    for name in (
        "read_case_snapshot",
        "read_forecast_profile",
        "list_case_offers",
        "evaluate_recovery",
        "memory_edit",
    )
]
QUESTIONS = {role: f"Q:{role}" for role in ("fixed", "single", *EXPERTS)}
BASE = {
    "case_id": "c",
    "revision_id": "1",
    "run_id": "root",
    "allowed_scope": {"store_id": "s", "sku_id": "k"},
    "supplied_evidence_ids": ["snap", "proposal"],
}


def claim(statement, support, **typed):
    return {"statement": statement, "support": support, **typed}


def ok(**fields):
    return {"claims": [], "missing": [], "followup_requests": [], **fields}


def task(subtask_id, claims):
    return {"subtask_id": subtask_id, "role": subtask_id.split(":")[0], "claims": claims}


class Scripted:
    """Replies keyed by a marker in the rendered request; records the tools each call saw."""

    def __init__(self, replies):
        self.replies, self.seen = replies, []

    async def complete(self, messages, tools, **kwargs):
        text = json.dumps(messages, ensure_ascii=False)
        for marker, reply in self.replies.items():
            if marker in text:
                self.seen.append((marker, sorted(tool["function"]["name"] for tool in tools)))
                if "tool_calls" in reply:
                    return reply
                return {
                    "content": reply if isinstance(reply, str) else json.dumps(reply),
                    "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                }
        raise AssertionError("unexpected request")


async def run(model, strategy, *, signals=None, budget=None, **kwargs):
    from shopsteward_agent.cases import BoundedCaseRunner, CallBudget, run_strategy
    from shopsteward_agent.context import ModelProfile

    async def call_tool(spec, name, args, invocation_id):
        return {"ok": True, "data": {}, "references": [{"id": "snap"}]}

    runner = BoundedCaseRunner(
        model=model,
        profile=ModelProfile(model_id="main"),
        tools=TOOLS,
        call_tool=call_tool,
        budget=budget or CallBudget(),
        **kwargs.pop("runner", {}),
    )
    return await run_strategy(
        runner, strategy, base=BASE, questions=QUESTIONS, signals=signals or {}, **kwargs
    )


def test_only_structured_signals_add_the_options_expert():
    from shopsteward_agent.cases import plan_roles

    one_feasible = {"offer_count": 1, "feasible_purchases": 1}
    assert list(plan_roles("adaptive_multi", one_feasible)) == ["evidence", "impact"]
    assert plan_roles("adaptive_multi", {"offer_count": 3})["options"] == "multiple_offers"
    assert (
        plan_roles("adaptive_multi", {"offer_count": 1, "feasible_purchases": 0})["options"]
        == "no_feasible_purchase"
    )
    assert list(plan_roles("static_multi", {})) == list(EXPERTS)
    assert list(plan_roles("single", {"offer_count": 3})) == ["single"]
    assert list(plan_roles("fixed", {"offer_count": 3})) == ["fixed"]
    with pytest.raises(ValueError, match="unknown_strategy"):
        plan_roles("debate", {})


@pytest.mark.asyncio
async def test_adaptive_serves_exactly_one_typed_followup_and_reports_the_rest():
    model = Scripted(
        {
            "check MOQ wording": ok(
                claims=[claim("B needs 20", ["proposal"])], followup_requests=["and again"]
            ),
            "Q:evidence": ok(
                followup_requests=[{"role": "options", "question": "check MOQ wording"}]
            ),
            "Q:impact": ok(followup_requests=["recheck day 3"]),
        }
    )
    result = await run(model, "adaptive_multi", signals={"offer_count": 1, "feasible_purchases": 1})
    assert [item["subtask_id"] for item in result["subtasks"]] == [
        "evidence",
        "impact",
        "options:followup",
    ]
    assert result["strategy_id"] == "R3"
    assert result["routing"]["roles"] == {"evidence": "first_round", "impact": "first_round"}
    followup = result["followup"]
    assert (followup["status"], followup["role"], followup["requested_by"]) == (
        "dispatched",
        "options",
        "evidence",
    )
    assert [item["question"] for item in followup["unserved"]] == ["recheck day 3", "and again"]
    assert result["budget"]["model_calls"] == 3
    assert dict(model.seen)["check MOQ wording"] == [
        "clarify",
        "evaluate_recovery",
        "list_case_offers",
        "read_case_snapshot",
    ]


@pytest.mark.asyncio
async def test_followup_cannot_exceed_the_shared_ledger():
    from shopsteward_agent.cases import CallBudget

    model = Scripted({"Q:evidence": ok(followup_requests=["look again"]), "Q:impact": ok()})
    result = await run(model, "adaptive_multi", budget=CallBudget(max_model_calls=2))
    assert result["budget"]["model_calls"] == 2
    assert result["subtasks"][-1]["subtask_id"] == "evidence:followup"
    assert result["subtasks"][-1]["status"] == "failed"
    assert result["subtasks"][-1]["missing"] == ["AGENT_MODEL_BUDGET"]
    assert result["status"] == "partial"


@pytest.mark.asyncio
async def test_single_agent_keeps_every_expert_tool_and_the_root_budget_without_delegation():
    from shopsteward_agent.cases import CallBudget

    looping = {
        "tool_calls": [{"id": "c1", "function": {"name": "read_case_snapshot", "arguments": "{}"}}]
    }
    model = Scripted({"Q:single": looping})
    result = await run(model, "single", budget=CallBudget(max_model_calls=6))
    assert [item["role"] for item in result["subtasks"]] == ["single"]
    assert model.seen[0][1] == [
        "clarify",
        "evaluate_recovery",
        "list_case_offers",
        "read_case_snapshot",
        "read_forecast_profile",
    ]
    # An expert stops after four calls; the strong baseline may use the whole root ledger.
    assert result["budget"]["model_calls"] == 6
    assert result["subtasks"][0]["missing"] == ["AGENT_MODEL_BUDGET"]
    assert result["followup"] == {"status": "not_applicable", "unserved": []}
    assert result["strategy_id"] == "R1"


@pytest.mark.asyncio
async def test_static_multi_launches_all_experts_and_never_follows_up():
    model = Scripted({f"Q:{role}": ok(followup_requests=["more"]) for role in EXPERTS})
    result = await run(model, "static_multi", signals={"offer_count": 0})
    assert [item["role"] for item in result["subtasks"]] == list(EXPERTS)
    assert result["budget"]["model_calls"] == 3
    assert result["followup"]["status"] == "not_applicable"
    assert len(result["followup"]["unserved"]) == 3
    assert result["strategy_id"] == "R2"


@pytest.mark.asyncio
async def test_fixed_workflow_explains_supplied_results_without_business_tools():
    model = Scripted(
        {"Q:fixed": ok(claims=[claim("Waiting loses 20", ["proposal"], kind="calculation")])}
    )
    result = await run(model, "fixed", calculation_ids=["proposal"])
    assert model.seen == [("Q:fixed", ["clarify"])]
    assert result["status"] == "complete" and result["strategy_id"] == "R0"
    assert result["merged"]["claims"][0]["asserted_by"] == ["fixed"]


def test_join_counts_a_repeated_source_once_and_rejects_uncited_numbers():
    from shopsteward_agent.cases import merge

    merged = merge(
        [
            task("evidence", [claim("Order is delayed", ["snap"])]),
            task(
                "impact",
                [
                    claim("Order  is delayed", ["snap"]),
                    claim("Lost demand is 20", ["snap"], kind="calculation"),
                ],
            ),
        ],
        calculation_ids=["proposal"],
    )
    assert [(c["statement"], c["support"], c["asserted_by"]) for c in merged["claims"]] == [
        ("Order is delayed", ["snap"], ["evidence", "impact"])
    ]
    assert merged["conflicts"] == [
        {"type": "uncited_calculation", "subtask_id": "impact", "statement": "Lost demand is 20"}
    ]


@pytest.mark.asyncio
async def test_applicability_conflict_gets_one_evidence_recheck_that_settles_it():
    subject = {"type": "action", "id": "order-1"}
    exempt = {"subject": subject, "applicability": {"result": "not_supported"}}
    model = Scripted(
        {
            "disagree": ok(claims=[claim("Notice exempts accepted orders", ["snap"], **exempt)]),
            "Q:evidence": ok(
                claims=[
                    claim(
                        "Notice applies",
                        ["snap"],
                        subject=subject,
                        applicability={"result": "supported"},
                    )
                ]
            ),
            "Q:impact": ok(claims=[claim("Order is exempt", ["snap"], **exempt)]),
        }
    )
    result = await run(model, "adaptive_multi")
    assert (result["followup"]["requested_by"], result["followup"]["role"]) == (
        "coordinator",
        "evidence",
    )
    conflict = result["merged"]["conflicts"][0]
    assert (conflict["resolved_by"], conflict["result"]) == ("evidence:followup", "not_supported")
    assert len(conflict["positions"]) == 3
    assert [c["statement"] for c in result["merged"]["claims"]] == [
        "Order is exempt",
        "Notice exempts accepted orders",
    ]
    assert result["status"] == "complete"


@pytest.mark.asyncio
async def test_unsettled_conflict_stays_visible_and_is_not_published_as_a_claim():
    subject = {"type": "action", "id": "order-1"}
    model = Scripted(
        {
            "disagree": ok(missing=["Document tail unavailable"]),
            "Q:evidence": ok(
                claims=[
                    claim("Applies", ["snap"], subject=subject, applicability={"result": "yes"})
                ]
            ),
            "Q:impact": ok(
                claims=[
                    claim("Exempt", ["snap"], subject=subject, applicability={"result": "no"}),
                    claim("Stock runs out on day 3", ["proposal"]),
                ]
            ),
        }
    )
    result = await run(model, "adaptive_multi")
    conflict = result["merged"]["conflicts"][0]
    assert "resolved_by" not in conflict
    assert {p["result"] for p in conflict["positions"]} == {"yes", "no"}
    assert [c["statement"] for c in result["merged"]["claims"]] == ["Stock runs out on day 3"]
    assert result["status"] == "partial"
    assert result["budget"]["model_calls"] == 3


@pytest.mark.asyncio
async def test_expert_questions_become_one_clarification_instead_of_more_model_work():
    def ask(question):
        arguments = json.dumps({"question": question})
        return {
            "tool_calls": [{"id": "q", "function": {"name": "clarify", "arguments": arguments}}]
        }

    model = Scripted({"Q:evidence": ask("Which order?"), "Q:impact": ask("Which day?")})
    result = await run(model, "adaptive_multi")
    assert result["merged"]["clarification"] == {
        "requested_by": "evidence",
        "question": "Which order?",
    }
    assert result["followup"]["status"] == "none"
    assert result["status"] == "partial" and result["budget"]["model_calls"] == 2


@pytest.mark.asyncio
async def test_each_role_uses_its_frozen_profile():
    from shopsteward_agent.context import ModelProfile

    records = []

    async def record(item):
        records.append(item)

    light, main = Scripted({"Q:evidence": ok()}), Scripted({"Q:impact": ok()})
    result = await run(
        main,
        "adaptive_multi",
        runner={
            "role_models": {
                "evidence": (light, ModelProfile(profile_id="case-evidence", model_id="light"))
            },
            "record_call": record,
        },
    )
    assert {(item["role"], item["profile"]["model_id"]) for item in records} == {
        ("evidence", "light"),
        ("impact", "main"),
    }
    assert [marker for marker, _ in light.seen] == ["Q:evidence"]
    assert {role: p["model_id"] for role, p in result["profiles"].items()} == {
        "evidence": "light",
        "impact": "main",
    }


@pytest.mark.asyncio
async def test_untyped_claim_metadata_fails_closed():
    model = Scripted(
        {
            "Q:evidence": ok(claims=[claim("x", ["snap"], kind="majority_vote")]),
            "Q:impact": ok(followup_requests=[{"role": "auditor", "question": "approve it"}]),
        }
    )
    result = await run(model, "adaptive_multi")
    assert [item["missing"] for item in result["subtasks"]] == [
        ["invalid_subtask_result"],
        ["invalid_subtask_result"],
    ]
    assert result["followup"]["status"] == "none"


@pytest.mark.asyncio
async def test_one_followup_may_start_an_unused_role_but_not_a_second_round():
    from shopsteward_agent.cases import BoundedCaseRunner, CallBudget, SubtaskSpec
    from shopsteward_agent.context import ModelProfile

    runner = BoundedCaseRunner(
        model=Scripted({"Q": ok()}),
        profile=ModelProfile(model_id="main"),
        tools=[],
        call_tool=None,
        budget=CallBudget(),
    )
    await runner.run(
        [SubtaskSpec(**BASE, subtask_id="evidence", role="evidence", question="Q:evidence")]
    )
    with pytest.raises(ValueError, match="followup_limit"):
        await runner.followup("evidence", "Q again", role="single")
    extra = await runner.followup("evidence", "Q:options", role="options")
    assert (extra["subtask_id"], extra["role"]) == ("options:followup", "options")
    with pytest.raises(ValueError, match="followup_limit"):
        await runner.followup("evidence", "Q again")


@pytest.mark.asyncio
async def test_fenced_or_narrated_json_is_accepted_but_prose_alone_fails_with_a_stable_code():
    wrapped = "```json\n" + json.dumps(ok(claims=[claim("x", ["snap"])])) + "\n```\nAdvisory only."
    model = Scripted({"Q:evidence": wrapped, "Q:impact": "I could not decide {yet}."})
    result = await run(model, "adaptive_multi")
    evidence, impact = result["subtasks"]
    assert (evidence["status"], len(evidence["claims"])) == ("complete", 1)
    assert (impact["status"], impact["missing"]) == ("failed", ["invalid_subtask_result"])


def test_compatible_typed_results_are_not_a_conflict_but_feasible_versus_rejected_is():
    from shopsteward_agent.cases import merge

    def typed(statement, result, target="B_20"):
        return claim(
            statement,
            ["proposal"],
            subject={"type": "candidate", "id": target},
            applicability={"result": result},
        )

    agreeing = merge(
        [
            task("impact", [typed("B_20 is recommended", "recommended")]),
            task("options", [typed("B_20 passes every constraint", "feasible")]),
        ]
    )
    assert agreeing["conflicts"] == []
    assert len(agreeing["claims"]) == 2

    disputed = merge(
        [
            task("impact", [typed("B_20 is recommended", "recommended")]),
            task("options", [typed("B_20 breaks the cash floor", "rejected")]),
        ]
    )
    assert [item["type"] for item in disputed["conflicts"]] == ["applicability"]
    assert disputed["claims"] == []
