"""Inclusive denominators with configuration/endpoint strata and explicit unknowns."""

from collections import Counter, defaultdict

from .models import CaseResult

GROUP_FIELDS = (
    "suite_id",
    "dataset_version",
    "task_contract_version",
    "goal_endpoint",
    "rubric_hash",
    "strategy_id",
    "model_snapshot",
    "profile_hash",
    "prompt_hash",
    "builder_version",
    "solver_version",
    "adapter_version",
    "artifact_kind",
    "split",
    "lock_status",
)


def _outcomes(rows):
    total = len(rows)
    success = sum(row.task_success is True for row in rows)
    failure = sum(row.task_success is False for row in rows)
    unknown = total - success - failure
    return {
        "attempted": total,
        "success": success,
        "failure": failure,
        "undetermined": unknown,
        "pending_review": sum(r.evaluation_status == "pending_review" for r in rows),
        "missing_trace": sum(r.evaluation_status == "missing_trace" for r in rows),
        "success_rate_lower": success / total if total else None,
        "success_rate_upper": (success + unknown) / total if total else None,
    }


def _cost(rows):
    successes = sum(r.task_success is True for r in rows)
    unknown = sum(r.cost_status != "known" for r in rows)
    subtotal = sum(r.known_cost_subtotal for r in rows)
    total = subtotal if rows and not unknown else None
    return {
        "status": "known"
        if total is not None
        else "partial"
        if any(r.cost_status in {"partial", "known"} for r in rows)
        else "unknown",
        "total": total,
        "known_subtotal": subtotal,
        "unknown_runs": unknown,
        "per_success": total / successes if successes and total is not None else None,
        "per_success_status": "undefined_no_success"
        if not successes
        else "unknown_cost"
        if total is None
        else "known",
    }


def _usage(rows):
    calls = [c for r in rows for c in r.calls]
    incomplete = sum(not r.calls_complete for r in rows)
    result = {
        "observed_calls": len(calls),
        "total_calls": None if incomplete else len(calls),
        "incomplete_call_ledgers": incomplete,
        "by_role": dict(sorted(Counter(c.role for c in calls).items())),
        "by_status": dict(sorted(Counter(c.status for c in calls).items())),
    }
    for key in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_input_tokens"):
        missing = sum(getattr(c, key) is None for c in calls)
        subtotal = sum(getattr(c, key) for c in calls if getattr(c, key) is not None)
        result[key] = {
            "total": None if missing or incomplete else subtotal,
            "known_subtotal": subtotal,
            "unknown_calls": missing,
        }
    return result


def _latency(rows, key):
    values = sorted(getattr(r, key) for r in rows if getattr(r, key) is not None)

    def percentile(p):
        if not values:
            return None
        position = (len(values) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        return values[lower] + (values[upper] - values[lower]) * (position - lower)

    return {
        "observed": len(values),
        "unknown": len(rows) - len(values),
        "p50_ms": percentile(0.5),
        "p95_ms": percentile(0.95),
    }


def _group(rows):
    included = [r for r in rows if r.attempted and r.evaluation_status != "invalid_fixture"]
    strata = {}
    for field in ("scenario_family", "complexity"):
        strata[field] = {
            value: _outcomes([r for r in included if getattr(r, field) == value])
            for value in sorted({getattr(r, field) for r in included})
        }
    dimensions = {}
    for key in ("D1", "D2", "D3", "D4", "D5", "D6"):
        items = [d for r in included for d in r.dimension_scores if d.dimension_id == key]
        scored = [d.score for d in items if d.score is not None]
        dimensions[key] = {
            "applicable": sum(d.applicable for d in items),
            "not_applicable": sum(not d.applicable for d in items),
            "scored": len(scored),
            "pending_review": sum(d.status == "pending_review" for d in items),
            "missing_trace": sum(d.status == "missing_trace" for d in items),
            "score_counts": dict(sorted(Counter(scored).items())),
            "mean_among_scored_only": sum(scored) / len(scored) if scored else None,
        }
    critical_runs = sum(bool(r.critical_failures) for r in included)
    return {
        "configuration": {key: getattr(rows[0], key) for key in GROUP_FIELDS},
        "outcomes": _outcomes(included),
        "strata": strata,
        "dimensions": dimensions,
        "clarification": {
            f"Q{i}": dict(
                sorted(
                    Counter(
                        q.status
                        for r in included
                        for q in r.clarification_scores
                        if q.check_id == f"Q{i}"
                    ).items()
                )
            )
            for i in range(1, 7)
        },
        "critical_failure_runs": critical_runs,
        "critical_failure_rate": critical_runs / len(included) if included else None,
        "critical_failures": dict(
            sorted(Counter(code for r in included for code in r.critical_failures).items())
        ),
        "failure_tags": dict(
            sorted(Counter(tag for r in included for tag in r.failure_tags).items())
        ),
        "review_status": dict(sorted(Counter(r.review_status for r in included).items())),
        "cost": _cost(included),
        "usage": _usage(included),
        "active_latency": _latency(included, "active_latency_ms"),
        "human_wait": _latency(included, "human_wait_ms"),
        "independent_scenarios": len({r.case_id for r in included}),
        "replicates_are_not_independent_scenarios": True,
    }


def summarize(results: list[CaseResult]) -> dict:
    seen = set()
    validity = {}
    contracts = {}
    groups = defaultdict(list)
    excluded = []
    for row in results:
        if row.run_id in seen:
            raise ValueError(f"duplicate run_id: {row.run_id}")
        seen.add(row.run_id)
        fixture_key = (row.suite_id, row.dataset_version, row.case_id, row.fixture_hash)
        invalid = row.evaluation_status == "invalid_fixture"
        if fixture_key in validity and validity[fixture_key] != invalid:
            raise ValueError("fixture validity must be consistent across all compared strategies")
        validity[fixture_key] = invalid
        contract_key = (
            row.suite_id,
            row.dataset_version,
            row.case_id,
            row.task_contract_version,
            row.goal_endpoint,
            row.rubric_hash,
        )
        if contract_key in contracts and contracts[contract_key] != row.case_hash:
            raise ValueError("frozen case gold differs across compared runs/strategies")
        contracts[contract_key] = row.case_hash
        if invalid or not row.attempted:
            excluded.append(
                {
                    "run_id": row.run_id,
                    "case_id": row.case_id,
                    "strategy_id": row.strategy_id,
                    "reason": row.invalid_fixture_reason if invalid else "not_started",
                    "known_cost_subtotal": row.known_cost_subtotal,
                }
            )
        groups[tuple(getattr(row, key) for key in GROUP_FIELDS)].append(row)
    return {
        "schema_version": "case_report_v1",
        "notice": "Example fixture outcomes are not model/research scores. Endpoint and configuration groups are not pooled. Bounds reflect undetermined results, not confidence intervals.",
        "record_count": len(results),
        "excluded": excluded,
        "all_recorded_spend_known_subtotal": sum(r.known_cost_subtotal for r in results),
        "groups": [_group(rows) for _, rows in sorted(groups.items())],
    }


def markdown_report(report: dict) -> str:
    lines = [
        "# Offline agent case evaluation",
        "",
        report["notice"],
        "",
        f"Records: {report['record_count']}; excluded: {len(report['excluded'])}.",
        "",
        "| Suite / endpoint / strategy | Artifact | Attempts | Success / failure / undetermined | Success bounds | Cost / success |",
        "|---|---|---:|---|---|---|",
    ]
    for group in report["groups"]:
        config, outcomes, cost = group["configuration"], group["outcomes"], group["cost"]
        lower, upper = outcomes["success_rate_lower"], outcomes["success_rate_upper"]
        bounds = "undefined" if lower is None else f"{lower:.1%}–{upper:.1%}"
        per_success = (
            str(cost["per_success"])
            if cost["per_success"] is not None
            else cost["per_success_status"]
        )
        label = " / ".join(config[k] for k in ("suite_id", "goal_endpoint", "strategy_id"))
        lines.append(
            f"| {label} | {config['artifact_kind']} | {outcomes['attempted']} | {outcomes['success']} / {outcomes['failure']} / {outcomes['undetermined']} | {bounds} | {per_success} |"
        )
    lines.extend(
        [
            "",
            "See report.json for strata, every dimension and clarification status, critical errors, review status, known/unknown token usage, failed/retried call costs, and latency. No summed rubric ranking is produced.",
            "",
        ]
    )
    return "\n".join(lines)
