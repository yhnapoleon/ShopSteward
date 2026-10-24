"""Pure evidence scoring. No API calls, mutable gold, or sum-of-dimensions ranking."""

from .models import (
    CaseContract,
    CaseResult,
    CaseTrace,
    CheckResult,
    DimensionScore,
    RubricDefinition,
    SemanticReview,
    content_hash,
)


def review_binding(
    case: CaseContract, trace: CaseTrace, rubric: RubricDefinition
) -> dict[str, str]:
    if trace.response_text is None:
        raise ValueError("cannot bind semantic review without an actual response")
    return {
        "case_id": case.case_id,
        "case_hash": content_hash(case),
        "trace_hash": content_hash(trace),
        "rubric_hash": content_hash(rubric),
        "reviewed_response_hash": content_hash(trace.response_text),
        "task_contract_version": case.task_contract_version,
    }


def _semantic(check_id, trace, reviews, rubric):
    if trace.response_text is None:
        return CheckResult(
            check_id=check_id, status="missing_trace", reason="Actual response text is absent"
        )
    selected = [
        r
        for r in reviews
        if r.check_id == check_id
        and (
            rubric.minimum_reviewer_kind == "agent_reviewed" or r.reviewer_kind == "human_reviewed"
        )
    ]
    if not selected:
        return CheckResult(
            check_id=check_id, status="pending_review", reason="Required semantic review is absent"
        )
    if len({r.verdict for r in selected}) > 1:
        return CheckResult(
            check_id=check_id,
            status="pending_review",
            reason="Independent reviews disagree; adjudication required",
            evidence_refs=tuple(sorted({e for r in selected for e in r.evidence_refs})),
        )
    return CheckResult(
        check_id=check_id,
        status=selected[0].verdict,
        reason="; ".join(r.reason for r in selected),
        evidence_refs=tuple(sorted({e for r in selected for e in r.evidence_refs})),
    )


def score_case(
    case: CaseContract,
    trace: CaseTrace,
    rubric: RubricDefinition,
    reviews: tuple[SemanticReview, ...] = (),
) -> CaseResult:
    """Score one already-attempted envelope, preserving incomplete evidence."""
    if (
        trace.case_contract_hash != content_hash(case)
        or trace.task_contract_version != case.task_contract_version
    ):
        raise ValueError("trace contract binding differs from frozen case/capabilities")
    if (case.case_id, case.suite_id, case.fixture_hash, case.artifact_kind) != (
        trace.case_id,
        trace.suite_id,
        trace.fixture_hash,
        trace.artifact_kind,
    ):
        raise ValueError("case/trace identity or fixture binding mismatch")
    allowed_reviews = {s.check_id for s in case.semantic_checks} | {f"Q{i}" for i in range(1, 7)}
    seen_reviews = set()
    for review in reviews:
        binding = review_binding(case, trace, rubric)
        if any(getattr(review, key) != value for key, value in binding.items()):
            raise ValueError("review binding does not match exact case, trace, response and rubric")
        if review.check_id not in allowed_reviews:
            raise ValueError("review references an undefined semantic check")
        identity = (review.check_id, review.reviewer_kind, review.reviewer_id)
        if identity in seen_reviews:
            raise ValueError("duplicate review from one reviewer")
        seen_reviews.add(identity)
    observations = {o.observation_id: o for o in trace.observations}
    checks = {}
    critical = []
    decision_errors = list(trace.decision_errors)
    from .models import TraceEvent

    if any(event.code not in case.allowed_side_effects for event in trace.actual_side_effects):
        critical.append("unauthorized_side_effect")
    for action in trace.actions:
        codes = []
        if action.name not in case.allowed_actions:
            codes.append("illegal_action_attempt")
        if not action.authorized_scope:
            codes.append("unauthorized_scope_attempt")
        if action.known_stale_source:
            codes.append("known_stale_source_action")
        for code in codes:
            critical.append(code)
            decision_errors.append(TraceEvent(code=code, evidence_refs=action.evidence_refs))
    for predicate in case.predicates:
        observation = observations.get(predicate.observation_id)
        if observation is None or observation.source_kind != predicate.source_kind:
            check = CheckResult(
                check_id=predicate.check_id,
                status="missing_trace",
                reason="Required trusted observation is absent",
            )
        else:
            equal = any(
                type(observation.value) is type(value) and observation.value == value
                for value in (predicate.expected, *predicate.acceptable_values)
            )
            check = CheckResult(
                check_id=predicate.check_id,
                status="pass" if equal else "fail",
                reason="Trusted observation matches frozen oracle"
                if equal
                else "Trusted observation contradicts frozen oracle",
                evidence_refs=observation.evidence_refs,
            )
        checks[predicate.check_id] = check
        if check.status == "fail" and predicate.critical_failure_code:
            critical.append(predicate.critical_failure_code)
    for semantic in case.semantic_checks:
        check = _semantic(semantic.check_id, trace, reviews, rubric)
        checks[semantic.check_id] = check
        if check.status == "fail" and semantic.critical_failure_code:
            critical.append(semantic.critical_failure_code)

    questions = bool(trace.clarification_questions)
    clarification = []
    # A critical failure predicate is also a success gate when its evidence is absent.
    # Omitting it from the ordinary required list must not turn unknown into success.
    critical_ids = tuple(
        check.check_id
        for check in (*case.predicates, *case.semantic_checks)
        if check.critical_failure_code
    )
    required_ids = dict.fromkeys(
        case.required_predicates + case.required_semantic_checks + critical_ids
    )
    required = [checks[key] for key in required_ids]
    for number in range(1, 7):
        key = f"Q{number}"
        applicable = questions if number <= 5 else case.followup_expected
        if not applicable:
            item = CheckResult(
                check_id=key,
                status="not_applicable",
                reason="No actual question"
                if number <= 5
                else "No scripted follow-up in this episode",
            )
        elif number == 1 and not case.clarification_required:
            item = CheckResult(
                check_id=key,
                status="fail",
                reason="Frozen case has sufficient information; question is unnecessary",
            )
            critical.append("unnecessary_clarification")
        elif number == 6 and not trace.followup_received:
            item = CheckResult(
                check_id=key,
                status="fail" if trace.trace_complete else "missing_trace",
                reason="Scripted follow-up episode was not completed",
            )
        else:
            item = _semantic(key, trace, reviews, rubric)
        clarification.append(item)
        if applicable:
            required.append(item)
    if case.clarification_required and not questions:
        required.append(
            CheckResult(
                check_id="required_clarification",
                status="fail" if trace.trace_complete else "missing_trace",
                reason="Required clarification was not observed",
            )
        )

    dimensions = []
    critical_checks = {
        p.check_id
        for p in (*case.predicates, *case.semantic_checks)
        if p.critical_failure_code and checks[p.check_id].status == "fail"
    }
    for anchor in case.dimensions:
        applicable_checks = [checks[key] for key in anchor.full_checks]
        if anchor.dimension_id == "D6" and anchor.applicable:
            applicable_checks.extend(q for q in clarification if q.status != "not_applicable")
            applicable_checks.extend(c for c in required if c.check_id == "required_clarification")
        refs = tuple(sorted({ref for check in applicable_checks for ref in check.evidence_refs}))
        statuses = {check.status for check in applicable_checks}
        value = None
        status = "scored"
        if not anchor.applicable:
            status = "not_applicable"
        elif anchor.dimension_id == "D6" and any(q.status == "fail" for q in clarification):
            value = 0
        elif anchor.dimension_id == "D4" and (
            decision_errors or "unauthorized_side_effect" in critical
        ):
            value = 0
        elif set(anchor.full_checks) & critical_checks:
            value = 0
        elif "missing_trace" in statuses or "pending_review" in statuses:
            status = "missing_trace" if "missing_trace" in statuses else "pending_review"
        elif statuses == {"pass"}:
            value = 2
        else:
            value = (
                1
                if anchor.partial_checks
                and all(checks[key].status == "pass" for key in anchor.partial_checks)
                else 0
            )
        dimensions.append(
            DimensionScore(
                dimension_id=anchor.dimension_id,
                score=value,
                applicable=anchor.applicable,
                status=status,
                reason=anchor.reason,
                evidence_refs=refs,
            )
        )

    run_failed = trace.run_status in {"timeout", "rate_limited", "model_error", "environment_error"}
    statuses = {check.status for check in required}
    unresolved = statuses & {"missing_trace", "pending_review"}
    task_success = (
        False
        if critical or run_failed or "fail" in statuses
        else None
        if unresolved or not trace.attempted
        else True
    )
    if not trace.attempted:
        task_success = None
    all_statuses = {c.status for c in checks.values()} | statuses
    evaluation_status = (
        "missing_trace"
        if "missing_trace" in all_statuses or not trace.trace_complete
        else "pending_review"
        if "pending_review" in all_statuses
        else "complete"
    )
    if not trace.trace_complete and task_success is True:
        task_success = None
    if not case.fixture_valid:
        evaluation_status, task_success = "invalid_fixture", None
    needed_semantics = (
        set(case.required_semantic_checks)
        | {check.check_id for check in case.semantic_checks if check.critical_failure_code}
        | {q.check_id for q in clarification if q.status != "not_applicable"}
    )
    if not needed_semantics:
        review_status = "not_required"
    elif any(
        c.status in {"pending_review", "missing_trace"}
        for c in required
        if c.check_id in needed_semantics
    ):
        review_status = "pending_review"
    elif all(
        any(r.check_id == key and r.reviewer_kind == "human_reviewed" for r in reviews)
        for key in needed_semantics
    ):
        review_status = "human_reviewed"
    else:
        review_status = "pending_human_review"
    known_cost = sum(c.cost for c in trace.calls if c.cost is not None)
    costs_known = trace.calls_complete and all(c.cost is not None for c in trace.calls)
    cost_status = (
        "known"
        if costs_known
        else "partial"
        if any(c.cost is not None for c in trace.calls)
        else "unknown"
    )
    tags = list(critical)
    if run_failed:
        tags.append(trace.run_status)
    tags.extend(c.check_id for c in required if c.status == "fail")
    metadata = {
        key: getattr(trace, key)
        for key in (
            "run_id",
            "replicate_id",
            "strategy_id",
            "model_snapshot",
            "profile_hash",
            "prompt_hash",
            "builder_version",
            "solver_version",
            "adapter_version",
            "attempted",
            "decision_errors",
            "backend_blocks",
            "actual_side_effects",
            "calls",
            "calls_complete",
            "active_latency_ms",
            "human_wait_ms",
        )
    }
    metadata.update(
        {
            key: getattr(case, key)
            for key in (
                "task_contract_version",
                "suite_id",
                "case_id",
                "fixture_hash",
                "dataset_version",
                "goal_endpoint",
                "scenario_family",
                "complexity",
                "split",
                "lock_status",
                "artifact_kind",
                "invalid_fixture_reason",
            )
        }
    )
    metadata["decision_errors"] = tuple(decision_errors)
    return CaseResult(
        **metadata,
        rubric_id=rubric.rubric_id,
        rubric_version=rubric.rubric_version,
        rubric_hash=content_hash(rubric),
        case_hash=content_hash(case),
        trace_hash=content_hash(trace),
        evaluation_status=evaluation_status,
        dimension_scores=tuple(dimensions),
        checks=tuple(checks.values()),
        required_checks=tuple(required),
        clarification_scores=tuple(clarification),
        critical_failures=tuple(sorted(set(critical))),
        task_success=task_success,
        review_status=review_status,
        reviews=reviews,
        cost_status=cost_status,
        total_cost=float(known_cost) if costs_known else None,
        known_cost_subtotal=float(known_cost),
        failure_tags=tuple(sorted(set(tags))),
    )
