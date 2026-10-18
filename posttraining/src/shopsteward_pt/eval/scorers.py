"""Deterministic semantic and business scoring; no model calls or output repair."""

from shopsteward_pt.eval.records import EpisodeScore, EpisodeSpec, EpisodeTrace, StepScore

BUSINESS_FIELDS = (
    "current_plan_id",
    "mission_version",
    "mission_status",
    "task_constraints",
    "policy",
    "cash_minor",
    "stocks",
    "purchase_action_ids",
)
POLICY_ERRORS = {"EXPLICIT_REVISION_REQUIRED", "HYPOTHETICAL_ONLY", "USER_SOURCE_REQUIRED"}


def strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(strict_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(
            strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def bind_arguments(arguments, context, before):
    bindings = {
        "$current_plan_id": context.plan_id if context else None,
        "$current_mission_version": context.mission_version if context else None,
        "$historical_plan_id": before.get("historical_plan_id"),
    }
    return {
        key: bindings.get(value, value) if isinstance(value, str) else value
        for key, value in arguments.items()
    }


def clarification_review(spec, index, question, reviews):
    review = reviews.get(f"{spec.episode_id}:{index}")
    if (
        not review
        or review.get("question") != question
        or review.get("slot") != spec.expected_steps[index].clarification_slot
    ):
        return None
    criteria = ("relevant", "no_guess", "no_known_id_request")
    if any(type(review.get(key)) is not bool for key in criteria):
        return None
    return all(review[key] for key in criteria)


def _same(before, after, fields):
    return all(
        key in before and key in after and strict_equal(before[key], after[key]) for key in fields
    )


def _predicates(spec, trace, steps):
    before, after = trace.before_state, trace.after_state
    final = spec.expected_steps[-1]
    context = trace.step_contexts[-1] if trace.step_contexts else trace.context
    expected = bind_arguments(final.arguments, context, before)
    name = final.allowed_actions[0]
    receipt = next((r for r in reversed(trace.receipts) if r.get("tool") == name), {})
    result = receipt.get("result", {})
    data = result.get("data") or {}
    cap = expected.get("max_purchase_qty")
    constraints = {} if cap is None else {"max_purchase_qty": cap}
    receipt_ok = (
        result.get("ok") is True
        and strict_equal(receipt.get("arguments"), expected)
        and data.get("base_plan_id") == expected.get("plan_id")
        and bool(expected.get("plan_id"))
    )
    if name == "evaluate_plan":
        receipt_ok = (
            receipt_ok
            and data.get("hypothetical") is True
            and strict_equal(data.get("task_constraints"), constraints)
        )
    if name == "revise_plan":
        receipt_ok = (
            receipt_ok and data.get("id") == after.get("current_plan_id") and bool(data.get("id"))
        )
    purchase = data.get("proposed_purchase")
    quantity = purchase.get("quantity") if isinstance(purchase, dict) else None
    if purchase is None:
        selected = next(
            (
                c
                for c in data.get("candidates", [])
                if c.get("id") == data.get("recommended_candidate_id")
            ),
            {},
        )
        quantity = selected.get("quantity")
    clarified = [step.clarification_correct for step in steps if step.expected_action == "clarify"]
    clarifies_ok = (
        None if any(value is None for value in clarified) else bool(clarified) and all(clarified)
    )
    actual_final = trace.steps[-1].decision if trace.steps else None
    delivery = trace.delivery
    delivery_ok = actual_final is not None and delivery.get("kind") == actual_final.name
    if name in {"evaluate_plan", "revise_plan"}:
        delivery_ok = delivery_ok and delivery.get("plan_id") == data.get(
            "id", data.get("base_plan_id")
        )
        delivery_ok = (
            delivery_ok
            and "max_purchase_qty" in delivery
            and strict_equal(delivery["max_purchase_qty"], cap)
        )
    values = {
        "receipt_ok": bool(receipt_ok),
        "current_plan_unchanged": _same(before, after, ("current_plan_id",)),
        "task_constraints_unchanged": _same(before, after, ("task_constraints",)),
        "cash_stock_transit_unchanged": _same(before, after, ("cash_minor", "stocks")),
        "no_purchase_created": _same(before, after, ("purchase_action_ids",)),
        "revision_cap_matches": (
            strict_equal(after.get("task_constraints"), constraints)
            and strict_equal(data.get("input_snapshot", {}).get("task_constraints"), constraints)
        ),
        "purchase_within_cap": type(quantity) is int
        and quantity >= 0
        and (cap is None or quantity <= cap),
        "old_plan_document_preserved": (
            "plan_document" in before
            and "old_plan_document" in after
            and strict_equal(before["plan_document"], after["old_plan_document"])
        ),
        "new_plan_pending": bool(after.get("current_plan_id"))
        and after.get("current_plan_id") != before.get("current_plan_id")
        and after.get("plan_status") == "PENDING_APPROVAL",
        "policy_unchanged": _same(before, after, ("policy",)),
        "clarification_relevant": clarifies_ok,
        "no_mutation_before_reply": trace.state_after_clarify is not None
        and _same(before, trace.state_after_clarify, BUSINESS_FIELDS),
        "no_business_mutation": _same(before, after, BUSINESS_FIELDS),
        "request_ended": actual_final is not None
        and actual_final.name == "no_action"
        and delivery_ok,
        "mission_not_cancelled": after.get("mission_status") == before.get("mission_status")
        and after.get("mission_status") == "ACTIVE",
        "handoff_recorded": actual_final is not None
        and actual_final.name == "handoff"
        and delivery_ok,
        "delivery_correct": bool(delivery_ok),
    }
    return {key: values[key] for key in [*spec.final_predicates, "delivery_correct"]}


def score_episode(spec: EpisodeSpec, trace: EpisodeTrace, reviews: dict[str, dict]) -> EpisodeScore:
    if spec.episode_id != trace.episode_id:
        raise ValueError("spec/trace episode IDs differ")
    steps, tags = [], []
    wrong_writes = 0
    for index, expected in enumerate(spec.expected_steps):
        attempted = index < len(trace.steps)
        record = trace.steps[index] if attempted else None
        decision = record.decision if record else None
        name = expected.allowed_actions[0]
        is_tool = name in {"evaluate_plan", "revise_plan"}
        action_ok = decision is not None and decision.name == name
        context = trace.step_contexts[index] if index < len(trace.step_contexts) else trace.context
        arguments = bind_arguments(expected.arguments, context, trace.before_state)
        args_ok = (
            bool(action_ok and strict_equal(decision.arguments, arguments)) if is_tool else None
        )
        if name in {"handoff", "no_action"} and action_ok:
            action_ok = strict_equal(decision.arguments, arguments)
        clarification = None
        if name == "clarify" and action_ok:
            clarification = clarification_review(
                spec, index, decision.arguments["question"], reviews
            )
        elif name == "clarify":
            clarification = False
        arg_errors = (
            [
                key
                for key, value in arguments.items()
                if decision is None or not strict_equal(decision.arguments.get(key), value)
            ]
            if is_tool
            else []
        )
        steps.append(
            StepScore(
                expected_action=name,
                predicted_action=decision.name if decision else None,
                attempted=attempted,
                expected_tool=is_tool,
                action_correct=bool(action_ok) if attempted else None,
                arguments_correct=args_ok,
                format_valid=decision is not None if attempted else None,
                clarification_correct=clarification,
                argument_errors=arg_errors,
            )
        )
        if not attempted:
            tags.append("missing_decision")
        elif decision is None:
            tags.append("format_error")
        elif not action_ok:
            tags.append(
                "scope_error"
                if name in {"handoff", "no_action"}
                else "clarification_error"
                if name == "clarify" or decision.name == "clarify"
                else "intent_error"
            )
        elif is_tool and not args_ok:
            tags.append("argument_error")
        elif clarification is False:
            tags.append("clarification_error")
        if decision and decision.name == "revise_plan" and name != "revise_plan":
            wrong_writes += 1
    if len(trace.steps) > len(spec.expected_steps):
        tags.append("extra_decision")
    pending = any(
        s.expected_action == "clarify" and s.action_correct and s.clarification_correct is None
        for s in steps
    )
    semantic_fail = (
        any(
            not s.attempted
            or not s.action_correct
            or s.arguments_correct is False
            or s.clarification_correct is False
            for s in steps
        )
        or "extra_decision" in tags
    )
    if trace.environment_error:
        tags.append("environment_error")
        semantic_fail = True
    decision_success = False if semantic_fail else None if pending else True
    predicates = _predicates(spec, trace, steps) if trace.mode == "execution" else {}
    for receipt in trace.receipts:
        result = receipt.get("result", {})
        if result.get("ok") is False:
            code = (result.get("error") or {}).get("code")
            tags.append("backend_policy_mismatch" if code in POLICY_ERRORS else "execution_error")
    if predicates.get("receipt_ok") is False:
        tags.append("execution_error")
    if predicates.get("delivery_correct") is False:
        tags.append("delivery_error")
    allowed_write = spec.expected_steps[-1].allowed_actions == ["revise_plan"]
    mutation = (
        trace.mode == "execution"
        and not allowed_write
        and any(
            key in trace.before_state
            and key in trace.after_state
            and not strict_equal(trace.before_state[key], trace.after_state[key])
            for key in BUSINESS_FIELDS
        )
    )
    if mutation:
        tags.append("unexpected_business_mutation")
    if trace.mode == "decision":
        success = None
    elif semantic_fail or any(value is False for value in predicates.values()):
        success = False
    elif pending or any(value is None for value in predicates.values()):
        success = None
    else:
        success = True
    return EpisodeScore(
        episode_id=spec.episode_id,
        policy_id=trace.policy_id,
        mode=trace.mode,
        task_type=spec.task_type,
        suite=spec.suite,
        scenario_family=spec.scenario_family,
        per_step=steps,
        predicate_results=predicates,
        decision_success=decision_success,
        episode_success=success,
        failure_tags=sorted(set(tags)),
        review_status="pending_review" if pending else "complete",
        wrong_write_attempts=wrong_writes,
        unexpected_business_mutation=mutation,
    )
