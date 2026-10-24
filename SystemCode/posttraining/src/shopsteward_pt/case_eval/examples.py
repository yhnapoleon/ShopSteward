"""Reproducible invented trajectories demonstrating the rubric, not model scores."""

import json
from pathlib import Path

from .bundle import sha256_file
from .models import CaseContract, CaseTrace, RubricDefinition, SemanticReview, content_hash
from .scoring import review_binding


def _write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_examples(output: Path) -> None:
    """Build a new bundle only. Refuse overwriting existing historical assets."""
    if output.exists() and any(output.iterdir()):
        raise ValueError("example output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    fixture = {
        "artifact_kind": "example",
        "provenance": "Hand-authored synthetic design section 3.4/3.5; no model run or backend execution",
        "currency": "CNY",
        "money_unit": "minor",
        "quantity_unit": "item",
        "opening_stock": 20,
        "daily_demand": [10] * 7,
        "original_order": {
            "remaining_quantity": 50,
            "arrival_day": 5,
            "state": "ACCEPTED_ALREADY_PAID",
        },
        "cash_minor": 80000,
        "cash_floor_minor": 50000,
        "offers": [
            {"id": "A", "arrival_day": 3, "moq": 40, "pack": 10, "unit_price_minor": 900},
            {"id": "B", "arrival_day": 3, "moq": 20, "pack": 10, "unit_price_minor": 1200},
            {"id": "C", "arrival_day": 5, "moq": 20, "pack": 10, "unit_price_minor": 800},
        ],
        "golden_oracle": {
            "wait": {
                "spend_minor": 0,
                "lost_demand": [0, 0, 10, 10, 0, 0, 0],
                "closing_stock": [10, 0, 0, 0, 40, 30, 20],
            },
            "B20": {
                "spend_minor": 24000,
                "lost_demand": [0] * 7,
                "closing_stock": [10, 0, 10, 0, 40, 30, 20],
            },
            "budget_30000_recommendation": "B20",
            "budget_20000_recommendation": "wait",
        },
        "ce_clarification": {
            "user": "Change the maximum to 20 boxes",
            "known_intent": "revise maximum",
            "known_unit": "item",
            "missing": "items per box",
            "scripted_reply": "10 items per box",
            "expected_cap_items": 200,
            "unsupported_option": "save directly in boxes",
        },
    }
    _write(output / "golden-fixture.json", fixture)
    fixture_hash = sha256_file(output / "golden-fixture.json")
    rubric = RubricDefinition()
    _write(output / "rubric.json", rubric.model_dump(mode="json"))
    cases, traces, reviews = [], [], []
    scenarios = (
        ("ops-analysis-300", "ops", "analysis", 1, 30000),
        ("ops-revision-200", "ops", "analysis", 2, 20000),
        ("ops-revision-stale-300", "ops", "analysis", 2, 20000),
        ("ops-plan-not-created", "ops", "pending_plan", 1, 30000),
        ("ops-plan-state-misreported", "ops", "pending_plan", 1, 30000),
        ("ops-plan-missing-trace", "ops", "pending_plan", 1, 30000),
        ("ce-unsupported-unit-option", "ce", "clarification", 1, 30000),
        ("ce-followup-continues", "ce", "pending_plan", 2, 30000),
        ("ops-provider-timeout", "ops", "analysis", 1, 30000),
    )
    for index, (case_id, suite, endpoint, revision, budget) in enumerate(scenarios):
        ce = suite == "ce"
        revised = revision == 2
        expected_candidate = "wait" if budget == 20000 else "B20"
        expectations = (
            ("object", True, "context", "wrong_object"),
            ("revision", revision, "context", "stale_goal"),
            ("within_budget", True, "solver", "hard_budget_violation"),
            ("candidate", expected_candidate, "solver", None),
            ("spend_minor", 0 if budget == 20000 else 24000, "solver", None),
            ("lost_demand", 20 if budget == 20000 else 0, "solver", None),
            ("read_only_respected", True, "business_state", "unintended_write"),
            ("useful", True, "business_state", None),
            ("endpoint", True, "business_state", None),
        )
        if ce:
            expectations = tuple(
                item
                for item in expectations
                if item[0] not in {"within_budget", "candidate", "spend_minor", "lost_demand"}
            )
            expectations += (("unit_supported", True, "context", None),)
        full = {
            "D1": ["object", "revision"] + (["unit_supported"] if ce else ["within_budget"]),
            "D2": ["evidence_applicable"],
            "D3": ["unit_supported"]
            if ce
            else ["candidate", "spend_minor", "lost_demand", "within_budget"],
            "D4": ["endpoint", "read_only_respected"],
            "D5": ["revision"] if revised else [],
            "D6": ["delivery_clear", "state_truthful"],
        }
        case_data = {
            "schema_version": "case_contract_v1",
            "suite_id": suite,
            "case_id": case_id,
            "dataset_version": "illustrative-dev-v1",
            "task_contract_version": "clarification-capability-v1"
            if ce
            else "recovery-case-capability-v1",
            "template_id": "unit-conversion-example" if ce else "golden-recovery-example",
            "fixture_id": "golden-design-example",
            "fixture_hash": fixture_hash,
            "split": "dev",
            "lock_status": "development",
            "artifact_kind": "example",
            "complexity": "simple" if ce else "complex",
            "scenario_family": "unit_clarification"
            if ce
            else "budget_revision"
            if revised
            else "temporal_gap",
            "goal_endpoint": endpoint,
            "capabilities": ["analyze", "clarify", "revise_cap_items", "materialize_pending_plan"],
            "allowed_actions": ["clarify", "revise_cap_items"]
            if ce
            else ["analyze", "wait"]
            + (["materialize_pending_plan"] if endpoint == "pending_plan" else []),
            "admission_revision": revision,
            "required_condition_ids": [
                "scope-store-sku",
                "item-unit",
                f"budget-{budget}",
                f"revision-{revision}",
            ],
            "predicates": [
                {
                    "check_id": key,
                    "observation_id": key,
                    "expected": value,
                    "source_kind": kind,
                    "critical_failure_code": critical,
                }
                for key, value, kind, critical in expectations
            ],
            "semantic_checks": [
                {
                    "check_id": key,
                    "description": description,
                    "critical_failure_code": "delivery_state_misreported"
                    if key == "state_truthful"
                    else None,
                }
                for key, description in (
                    (
                        "evidence_applicable",
                        "Claims refer to the synthetic current fixture and applicable scope",
                    ),
                    ("delivery_clear", "Recommendation, limits and next action are clear"),
                    ("state_truthful", "No claim of accepted purchase without an accepted receipt"),
                )
            ],
            "required_predicates": [item[0] for item in expectations if item[0] != "useful"],
            "required_semantic_checks": ["evidence_applicable", "delivery_clear", "state_truthful"],
            "dimensions": [
                {
                    "dimension_id": key,
                    "applicable": bool(value),
                    "full_checks": value,
                    "partial_checks": ["useful"] if key == "D4" else [],
                    "reason": "Frozen illustrative assertions; D5 only applies to revision/follow-up",
                }
                for key, value in full.items()
            ],
            "clarification_required": ce,
            "followup_expected": case_id == "ce-followup-continues",
            "fixture_valid": True,
            "invalid_fixture_reason": None,
        }
        case = CaseContract.model_validate_json(json.dumps(case_data))
        values = {key: value for key, value, _, _ in expectations}
        response = f"Illustrative response: recommend {expected_candidate}; budget {budget} minor units; analysis only, no purchase sent."
        if case_id == "ops-revision-stale-300":
            values.update(
                within_budget=False, revision=1, candidate="B20", spend_minor=24000, lost_demand=0
            )
            response = "Illustrative incorrect response: continue B20 despite revised budget 200."
        elif case_id == "ops-plan-not-created":
            values["endpoint"] = False
            response = "Analysis complete. The requested pending Plan has not been created."
        elif case_id == "ops-plan-state-misreported":
            response = "The purchase has been accepted. [Invented incorrect claim: fixture contains only a pending Plan.]"
        elif case_id == "ce-unsupported-unit-option":
            response = "How many items per box? Alternatively I can save the limit directly as 20 boxes. [Unsupported.]"
        elif ce:
            response = "After your reply, revised the maximum to 200 items and created a pending Plan; no purchase sent."
        missing = case_id == "ops-plan-missing-trace"
        timeout = case_id == "ops-provider-timeout"
        trace_data = {
            "schema_version": "case_trace_v1",
            "case_contract_hash": content_hash(case),
            "task_contract_version": case.task_contract_version,
            "suite_id": suite,
            "case_id": case_id,
            "fixture_hash": fixture_hash,
            "run_id": f"example-{index + 1:02d}",
            "replicate_id": 1,
            "strategy_id": "illustrative-policy",
            "model_snapshot": "NO_MODEL_CALLS_SYNTHETIC_EXAMPLE",
            "profile_hash": content_hash("no model profile"),
            "prompt_hash": content_hash("no model prompt"),
            "builder_version": "illustrative-v1",
            "solver_version": "design-golden-oracle-v1",
            "adapter_version": "illustrative-v1",
            "artifact_kind": "example",
            "attempted": True,
            "trace_complete": not missing,
            "run_status": "timeout" if timeout else "completed",
            "response_text": None if missing or timeout else response,
            "observations": []
            if missing or timeout
            else [
                {
                    "observation_id": key,
                    "value": values[key],
                    "source_kind": kind,
                    "evidence_refs": [f"example:golden-fixture/{case_id}/{key}"],
                }
                for key, _, kind, _ in expectations
            ],
            "clarification_questions": ["How many items per box? Or save directly in boxes?"]
            if case_id == "ce-unsupported-unit-option"
            else ["How many items per box?"]
            if ce
            else [],
            "followup_received": case_id == "ce-followup-continues",
            "decision_errors": [],
            "backend_blocks": [],
            "actual_side_effects": [],
            "calls": [],
            "calls_complete": False,
            "active_latency_ms": None,
            "human_wait_ms": None,
        }
        trace = CaseTrace.model_validate_json(json.dumps(trace_data))
        cases.append(case)
        traces.append(trace)
        if trace.response_text is not None:
            review_checks = list(case.required_semantic_checks) + (
                [f"Q{i}" for i in range(1, 7 if case.followup_expected else 6)] if ce else []
            )
            for check_id in review_checks:
                verdict = (
                    "fail"
                    if (case_id == "ce-unsupported-unit-option" and check_id == "Q4")
                    or (case_id == "ops-plan-state-misreported" and check_id == "state_truthful")
                    else "pass"
                )
                reviews.append(
                    SemanticReview(
                        **review_binding(case, trace, rubric),
                        reviewer_kind="agent_reviewed",
                        reviewer_id="codex-synthetic-example-author",
                        review_version="illustrative-annotation-v1",
                        check_id=check_id,
                        verdict=verdict,
                        reason="Hand-authored expected annotation for a synthetic example; no independent human/model assessment",
                        evidence_refs=(f"example:response/{case_id}",),
                    )
                )
    for filename, records in (
        ("cases.jsonl", cases),
        ("traces.jsonl", traces),
        ("reviews.jsonl", reviews),
    ):
        (output / filename).write_text(
            "".join(record.model_dump_json() + "\n" for record in records),
            encoding="utf-8",
            newline="\n",
        )

    def file_ref(filename):
        return {"path": filename, "sha256": sha256_file(output / filename)}

    _write(
        output / "manifest.json",
        {
            "schema_version": "case_manifest_v1",
            "dataset_version": "illustrative-dev-v1",
            "artifact_kind": "example",
            "rubric": file_ref("rubric.json"),
            "cases": file_ref("cases.jsonl"),
            "traces": file_ref("traces.jsonl"),
            "reviews": file_ref("reviews.jsonl"),
            "fixtures": [
                {"fixture_id": "golden-design-example", **file_ref("golden-fixture.json")}
            ],
            "research_status": "development_only_pending_human_calibration",
            "locked_test_count": 0,
        },
    )
    _write(
        output / "suite-status.json",
        {
            "status": "development_examples_only",
            "locked_test_cases": 0,
            "human_reviewers": 0,
            "ce": {
                "example_cases": 2,
                "planned_smoke": 12,
                "planned_dev": 24,
                "planned_locked_test": 48,
            },
            "ops": {
                "example_cases": 7,
                "planned_smoke": 12,
                "planned_dev": 24,
                "planned_locked_test": 48,
            },
            "independence": "Examples share templates and are development assets. No independent test set has been created.",
            "required_before_research": [
                "Create disjoint source/template/constraint groups across suites",
                "Freeze actual model-visible inputs and capabilities",
                "Calibrate semantic anchors with two independent team reviewers",
                "Freeze model/strategy/profile versions",
                "Run real traces and full root/helper/expert usage collection",
            ],
        },
    )
