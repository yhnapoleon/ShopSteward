"""Turn one collaboration-strategy run into a scoreable trace.

Business observations come from the caller's trusted oracle. This adapter only
adds what the run's own ledger proves (calls, routing, join bookkeeping), under
the reserved `collab.` prefix, so a strategy cannot vouch for its own success.
"""

import json

from pydantic import BaseModel

from .models import CaseContract, CaseTrace, content_hash
from .runtime_adapter import adapt_runtime_calls

# Root strategies are the root of the usage tree; experts are delegated calls.
ROLE_KINDS = {
    "fixed": "root",
    "single": "root",
    "evidence": "expert",
    "impact": "expert",
    "options": "expert",
}


def strategy_trace(
    case: CaseContract,
    analysis: dict,
    *,
    run_id: str,
    replicate_id: int,
    solver_version: str,
    adapter_version: str,
    observations=(),
    active_latency_ms: int | None = None,
    artifact_kind: str = "recorded",
) -> CaseTrace:
    from shopsteward_agent.context.contracts import CallRecord

    subtasks = analysis.get("subtasks", [])
    records = tuple(CallRecord.model_validate(item) for item in analysis.get("call_records", []))
    usage = adapt_runtime_calls(records, role_map=ROLE_KINDS)
    attempted = analysis["status"] not in ("disabled", "unavailable")
    failures = [code for task in subtasks for code in task.get("missing", [])]
    all_failed = bool(subtasks) and all(task["status"] == "failed" for task in subtasks)
    if not attempted:
        run_status = "not_started"
    elif all_failed:
        run_status = "timeout" if any(c.endswith("_DEADLINE") for c in failures) else "model_error"
    else:
        run_status = "completed"
    merged = analysis.get("merged") or {}
    followup = analysis.get("followup") or {}
    budget = analysis.get("budget") or {}
    profiles = analysis.get("profiles") or {}
    models = {role: profile["model_id"] for role, profile in sorted(profiles.items())}
    diagnostics = {
        "collab.instances": len(subtasks),
        "collab.followup_dispatched": followup.get("status") == "dispatched",
        "collab.unserved_followups": len(followup.get("unserved", [])),
        "collab.unsettled_conflicts": sum(
            "resolved_by" not in item for item in merged.get("conflicts", [])
        ),
        # Several experts repeating one statement is not several pieces of evidence.
        "collab.repeated_assertions": sum(
            len(item.get("asserted_by", [])) > 1 for item in merged.get("claims", [])
        ),
        "collab.model_calls": budget.get("model_calls", 0),
        "collab.tool_calls": budget.get("tool_calls", 0),
    }
    clarification = merged.get("clarification")
    builders = sorted({r.manifest["builder_version"] for r in records if r.manifest})
    return CaseTrace.model_validate_json(
        json.dumps(
            {
                "schema_version": "case_trace_v1",
                "case_id": case.case_id,
                "suite_id": case.suite_id,
                "fixture_hash": case.fixture_hash,
                "case_contract_hash": content_hash(case),
                "task_contract_version": case.task_contract_version,
                "run_id": run_id,
                "replicate_id": replicate_id,
                "strategy_id": analysis.get("strategy_id", "unassigned"),
                "model_snapshot": (
                    ";".join(f"{role}={model}" for role, model in models.items())
                    if len(set(models.values())) > 1
                    else next(iter(models.values()), "unassigned")
                ),
                "profile_hash": content_hash(json.dumps(profiles, sort_keys=True)),
                "prompt_hash": (analysis.get("routing") or {}).get(
                    "prompt_hash", content_hash("unassigned")
                ),
                "builder_version": ";".join(builders) or "unassigned",
                "solver_version": solver_version,
                "adapter_version": adapter_version,
                "artifact_kind": artifact_kind,
                "attempted": attempted,
                "trace_complete": attempted
                and usage.calls_complete
                and analysis["status"] != "running",
                "run_status": run_status,
                # What a reviewer reads is the joined result, not any one expert's prose.
                "response_text": json.dumps(merged, ensure_ascii=False, sort_keys=True)
                if attempted and merged and not all_failed
                else None,
                "observations": [
                    item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                    for item in observations
                ]
                + (
                    [
                        {
                            "observation_id": key,
                            "value": value,
                            "source_kind": "context",
                            "evidence_refs": [f"run:{run_id}/strategy-ledger"],
                        }
                        for key, value in diagnostics.items()
                    ]
                    if attempted
                    else []
                ),
                "clarification_questions": [clarification["question"]] if clarification else [],
                "followup_received": False,
                "decision_errors": [],
                "backend_blocks": [],
                "actual_side_effects": [],
                "calls": [item.model_dump(mode="json") for item in usage.calls],
                "calls_complete": usage.calls_complete,
                "active_latency_ms": active_latency_ms,
                "human_wait_ms": None,
            }
        )
    )
