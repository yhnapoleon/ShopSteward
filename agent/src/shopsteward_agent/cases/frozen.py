"""Read-only Case evidence, shared by the product hook and offline evaluation."""

from ..context.contracts import digest
from .budget import CallBudget
from .bundle import load_bundle
from .runner import BoundedCaseRunner
from .strategy import run_strategy

NAMES = ("read_case_snapshot", "read_forecast_profile", "list_case_offers", "evaluate_recovery")


def signals(snapshot, proposal):
    """Structured facts only: routing never reads wording such as "complex"."""
    return {
        "offer_count": len(snapshot["recovery"].get("offers", [])),
        "feasible_purchases": sum(
            candidate.get("quantity", 0) > 0 and bool(candidate.get("feasible"))
            for candidate in (proposal or {}).get("candidates", [])
        ),
    }


def frozen_tools(snapshot, proposal, log=None):
    """Return (schemas, call_tool, evidence_ids) over one frozen snapshot and proposal."""
    recovery = snapshot["recovery"]
    evidence_id = "snapshot:" + digest(snapshot)
    proposal_id = (proposal or {}).get("id")

    async def call(spec, name, args, invocation_id):
        if log is not None:
            log.append({"subtask_id": spec.subtask_id, "name": name, "args_hash": digest(args)})
        if args:
            return {"ok": False, "error": "EMPTY_ARGUMENTS_REQUIRED", "references": []}
        data = {
            "read_case_snapshot": snapshot,
            "read_forecast_profile": {
                "daily_demand": recovery.get("daily_demand"),
                "demand_source": recovery.get("demand_source"),
            },
            "list_case_offers": recovery.get("offers", []),
            "evaluate_recovery": proposal,
        }.get(name)
        if data is None:
            return {"ok": False, "error": "EVIDENCE_UNAVAILABLE", "references": []}
        return {
            "ok": True,
            "data": data,
            "persisted": False,
            "references": [
                {
                    "type": "recovery_evidence",
                    "id": proposal_id if name == "evaluate_recovery" else evidence_id,
                }
            ],
        }

    schemas = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": "Read authorized frozen Case evidence; never modify business state.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }
        for name in NAMES
    ]
    return schemas, call, [evidence_id, *([proposal_id] if proposal_id else [])]


async def analyze_frozen_case(
    snapshot,
    proposal,
    *,
    case_id,
    revision_id,
    run_id,
    strategy,
    model,
    profile,
    bundle=None,
    role_models=None,
    budget=None,
    record_call=None,
    forced=False,
):
    """One advisory strategy run. Nothing here can write business state."""
    bundle = bundle or load_bundle()
    records, tool_log = {}, []

    async def observe(record):
        records[(record["run_id"], record["role"], record["call_index"])] = record
        if record_call:
            await record_call(record)

    tools, call, evidence_ids = frozen_tools(snapshot, proposal, tool_log)
    recovery = snapshot["recovery"]
    runner = BoundedCaseRunner(
        model=model,
        profile=profile,
        tools=tools,
        call_tool=call,
        budget=budget or CallBudget(),
        record_call=observe,
        role_models=role_models,
    )
    result = await run_strategy(
        runner,
        strategy,
        base={
            "case_id": case_id,
            "revision_id": str(revision_id),
            "run_id": run_id,
            "allowed_scope": {"store_id": recovery["store_id"], "sku_id": recovery["sku_id"]},
            "supplied_evidence_ids": evidence_ids,
            "dependency_versions": {
                "snapshot": digest(snapshot),
                "case_revision": str(revision_id),
            },
            "context": {"snapshot": snapshot, "proposal": proposal, "advisory_only": True},
        },
        questions=bundle.questions(),
        signals=signals(snapshot, proposal),
        calculation_ids=evidence_ids[1:],
        forced=forced,
    )
    # The run is bound to the exact text artifact, not just to the questions asked.
    result["routing"].update(prompt_hash=bundle.content_hash, bundle_revision=bundle.revision)
    result.update(call_records=list(records.values()), tool_log=tool_log, advisory_only=True)
    return result
