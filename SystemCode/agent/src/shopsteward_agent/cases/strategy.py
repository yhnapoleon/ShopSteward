"""Collaboration strategies on one ledger. Routing and joins are code, never votes."""

import json

from ..context.contracts import digest
from .runner import EXPERTS, SubtaskSpec

# Research IDs of the evaluation design. Every strategy shares the solver output,
# evidence permissions, output contract and root budget, so results are comparable.
STRATEGIES = {"fixed": "R0", "single": "R1", "static_multi": "R2", "adaptive_multi": "R3"}
# Results that can both hold for one subject are one stance, not a disagreement:
# the recommended candidate is also a feasible one.
SAME_STANCE = {("candidate", "recommended"): "feasible"}


def plan_roles(strategy, signals):
    """Return {role: reason}. Structured facts decide; wording never upgrades the mode."""
    if strategy not in STRATEGIES:
        raise ValueError("unknown_strategy")
    if strategy in ("fixed", "single"):
        return {strategy: "root_strategy"}
    if strategy == "static_multi":
        return dict.fromkeys(EXPERTS, "always")
    roles = {"evidence": "first_round", "impact": "first_round"}
    offers = signals.get("offer_count", 0)
    if offers > 1:
        roles["options"] = "multiple_offers"
    elif offers == 1 and not signals.get("feasible_purchases", 0):
        roles["options"] = "no_feasible_purchase"
    return roles


def merge(subtasks, *, calculation_ids=(), arbiter=None):
    """Join validated results without treating agreement as evidence.

    A source repeated by several experts stays one piece of support, prose cannot
    stand in for a solver field, and a contested reading is not published as a
    claim. Only the targeted follow-up (`arbiter`) can settle a conflict.
    """
    claims, conflicts, subjects = {}, [], {}
    for task in subtasks:
        for claim in task["claims"]:
            statement = " ".join(claim["statement"].split())
            if claim.get("kind") == "calculation" and not set(claim["support"]) & set(
                calculation_ids
            ):
                conflicts.append(
                    {
                        "type": "uncited_calculation",
                        "subtask_id": task["subtask_id"],
                        "statement": statement,
                    }
                )
                continue
            entry = claims.setdefault(
                statement, {**claim, "statement": statement, "support": [], "asserted_by": []}
            )
            entry["support"] = sorted({*entry["support"], *claim["support"]})
            if task["subtask_id"] not in entry["asserted_by"]:
                entry["asserted_by"].append(task["subtask_id"])
            result = claim.get("applicability", {}).get("result")
            if claim.get("subject") and isinstance(result, str):
                group = subjects.setdefault(
                    digest(claim["subject"]), {"subject": claim["subject"], "positions": []}
                )
                group["positions"].append(
                    {
                        "subtask_id": task["subtask_id"],
                        "result": result,
                        "stance": SAME_STANCE.get((claim["subject"].get("type"), result), result),
                        "statement": statement,
                        "support": claim["support"],
                    }
                )
    for group in subjects.values():
        if len({position["stance"] for position in group["positions"]}) < 2:
            continue
        conflict = {"type": "applicability", **group}
        rulings = {p["stance"] for p in group["positions"] if p["subtask_id"] == arbiter}
        if len(rulings) == 1:
            conflict.update(resolved_by=arbiter, result=rulings.pop())
        for position in group["positions"]:
            if position["stance"] != conflict.get("result"):
                claims.pop(position["statement"], None)
        conflicts.append(conflict)
    asked = next((task for task in subtasks if task.get("status") == "needs_input"), None)
    return {
        "claims": list(claims.values()),
        "missing": [
            {"subtask_id": task["subtask_id"], "item": item}
            for task in subtasks
            if task is not asked
            for item in task.get("missing", [])
        ],
        "conflicts": conflicts,
        # Experts only report needs_input; the root surfaces one question.
        "clarification": {"requested_by": asked["subtask_id"], "question": asked["missing"][0]}
        if asked
        else None,
    }


def _requests(subtasks):
    for task in subtasks:
        for item in task["followup_requests"]:
            item = {"question": item} if isinstance(item, str) else item
            yield {
                "requested_by": task["subtask_id"],
                "role": item.get("role", task["role"]),
                "question": item["question"],
            }


async def run_strategy(
    runner, strategy, *, base, questions, signals=None, calculation_ids=(), forced=False
):
    """Run one strategy to completion; `forced` marks a research override of routing."""
    signals = signals or {}
    roles = plan_roles(strategy, signals)
    limits = {
        # One explanation plus its protocol repair; no business tool is offered.
        "fixed": {"max_model_calls": 2, "max_tool_calls": 1},
        # The strong baseline is not weakened: it may spend the whole root ledger.
        "single": {
            "max_model_calls": min(14, runner.budget.max_model_calls),
            "max_tool_calls": min(28, runner.budget.max_tool_calls),
        },
    }
    subtasks = (
        await runner.run(
            [
                SubtaskSpec(
                    **base,
                    subtask_id=role,
                    role=role,
                    question=questions[role],
                    **limits.get(role, {}),
                )
                for role in roles
            ]
        )
    )["subtasks"]
    requests = list(_requests(subtasks))
    followup, arbiter = {"status": "not_applicable"}, None
    if strategy == "adaptive_multi":
        followup = {"status": "none"}
        conflict = next(
            (
                item
                for item in merge(subtasks, calculation_ids=calculation_ids)["conflicts"]
                if item["type"] == "applicability"
            ),
            None,
        )
        if conflict:
            # A code-detected disagreement outranks whatever the experts asked for.
            requests.insert(
                0,
                {
                    "requested_by": "coordinator",
                    "role": "evidence",
                    "question": "Expert claims disagree about the same subject. Re-check the "
                    "cited sources and return one typed applicability claim for it. "
                    + json.dumps(
                        {"subject": conflict["subject"], "positions": conflict["positions"]},
                        ensure_ascii=False,
                    ),
                },
            )
        if requests:
            request = requests.pop(0)
            launched = {task["role"]: task["subtask_id"] for task in subtasks}
            if request["role"] in launched:
                extra = await runner.followup(launched[request["role"]], request["question"])
            else:
                extra = await runner.followup(
                    subtasks[0]["subtask_id"], request["question"], role=request["role"]
                )
            subtasks.append(extra)
            requests += _requests([extra])
            followup = {"status": "dispatched", **request, "subtask_id": extra["subtask_id"]}
            arbiter = extra["subtask_id"] if conflict else None
    # Requests beyond the single round are reported, never silently dropped or looped.
    followup["unserved"] = requests
    merged = merge(subtasks, calculation_ids=calculation_ids, arbiter=arbiter)
    snapshot = runner.budget.snapshot()
    settled = all("resolved_by" in item for item in merged["conflicts"])
    return {
        "status": "complete"
        if settled and all(task["status"] == "complete" for task in subtasks)
        else "partial",
        "strategy": strategy,
        "strategy_id": STRATEGIES[strategy],
        "routing": {
            "forced": forced,
            "roles": roles,
            "signals": signals,
            "prompt_hash": digest({role: questions[role] for role in roles}),
        },
        "profiles": {
            task["role"]: runner.assigned(task["role"])[1].model_dump(mode="json")
            for task in subtasks
        },
        "subtasks": subtasks,
        "merged": merged,
        "followup": followup,
        "budget": snapshot,
        "usage": snapshot["usage"],
        "cost_status": "unknown",
    }
