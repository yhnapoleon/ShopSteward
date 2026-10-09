"""Optional experts over frozen Case evidence, outside business transactions."""

from datetime import UTC, datetime
from uuid import uuid4

from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.core.hashing import digest


def current_case_principal(settings, principal_id, store_id):
    for grant in settings.auth_tokens:
        if grant.kind != "user" or grant.principal_id != principal_id:
            continue
        try:
            authorize_store(grant, store_id)
            return grant
        except AppError:
            continue
    raise AppError(403, "CASE_PERMISSION_REVOKED", "Case owner no longer has access")


def case_current(case, revision, proposal_id, run_id):
    return (
        case.current_revision == revision
        and case.proposal_id == proposal_id
        and (case.expert_analysis or {}).get("root_run_id") == run_id
        and case.status not in {"CANCELLED", "RESOLVED", "CLOSED"}
    )


async def analyze_case_experts(
    snapshot,
    *,
    case_id,
    revision_id,
    run_id,
    settings,
    proposal=None,
    persist=None,
    record_call=None,
    model=None,
    strategy=None,
):
    from shopsteward_agent import OpenAIModel
    from shopsteward_agent.cases import CallBudget, analyze_frozen_case, load_bundle
    from shopsteward_agent.context import ModelProfile

    if not settings.agent_case_experts_enabled:
        return {"status": "disabled", "subtasks": [], "call_records": [], "cost_status": "unknown"}
    if model is None and (not settings.agent_api_key_file or not settings.agent_case_model):
        return {
            "status": "unavailable",
            "subtasks": [],
            "missing": ["CASE_MODEL_NOT_CONFIGURED"],
            "call_records": [],
            "cost_status": "unknown",
        }
    profile = ModelProfile(
        profile_id="case-configured",
        model_id=settings.agent_case_model or "test-injected",
        api_mode=settings.agent_case_api_mode,
        reasoning_effort=settings.agent_reasoning_effort,
        max_input_tokens=settings.agent_max_input_tokens,
        max_output_tokens=settings.agent_max_output_tokens,
        timeout_s=settings.agent_model_timeout_seconds,
    )

    def client(profile):
        return model or OpenAIModel(
            base_url=settings.agent_base_url,
            model=profile.model_id,
            profile=profile,
            key_file=settings.agent_api_key_file,
        )

    # Role -> model is frozen here for the whole run; a role cannot change its
    # tools or permissions by using another model.
    role_models = {}
    for role, model_id in settings.agent_case_role_models.items():
        role_profile = profile.model_copy(
            update={"profile_id": f"case-{role}", "model_id": model_id}
        )
        role_models[role] = (client(role_profile), role_profile)
    result = await analyze_frozen_case(
        snapshot,
        proposal,
        case_id=case_id,
        revision_id=revision_id,
        run_id=run_id,
        strategy=strategy or settings.agent_case_strategy,
        model=client(profile),
        profile=profile,
        bundle=load_bundle(settings.agent_case_text_bundle),
        role_models=role_models,
        budget=CallBudget(persist=persist),
        record_call=record_call,
        forced=strategy is not None,
    )
    result.update(root_run_id=run_id, profile=profile.model_dump(mode="json"))
    return result


async def attach_case_experts(db, settings, principal, case_id, revision, proposal_id):
    """Persist before send; concurrent/replayed analyze requests cannot double-spend."""
    from app.agent_bridge.models import Receipt
    from app.operations_cases import repository as repo
    from app.operations_cases.models import CaseRevisionRow, RecoveryProposalRow

    run_id = str(uuid4())
    history_owner = f"case-context:{case_id}:{revision}"
    async with db.session() as session, session.begin():
        case = await repo.visible(session, principal, case_id, lock=True)
        current_case_principal(settings, principal.principal_id, case.store_id)
        if (
            case.current_revision != revision
            or case.proposal_id != proposal_id
            or case.status in {"CANCELLED", "RESOLVED", "CLOSED"}
        ):
            return await repo.detail(session, case)
        previous = case.expert_analysis
        if (
            previous
            and previous.get("revision") == revision
            and previous.get("proposal_id") == proposal_id
        ):
            if (
                previous.get("status") == "running"
                and datetime.now(UTC).timestamp() >= previous["deadline"]
            ):
                case.expert_analysis = {
                    **previous,
                    "status": "partial",
                    "missing": ["EXPERT_RUN_INTERRUPTED"],
                    "cost_status": "unknown",
                }
            return await repo.detail(session, case)
        row = await session.get(CaseRevisionRow, (case_id, revision))
        proposal = await session.get(RecoveryProposalRow, proposal_id)
        if row is None or row.snapshot is None or proposal is None:
            return await repo.detail(session, case)
        snapshot, proposal_doc = row.snapshot, proposal.document
        case.expert_analysis = {
            "status": "running",
            "revision": revision,
            "proposal_id": proposal_id,
            "root_run_id": run_id,
            "deadline": datetime.now(UTC).timestamp() + 150,
            "call_records": [],
            "cost_status": "unknown",
            "advisory_only": True,
        }
        session.add(
            Receipt(
                owner=history_owner,
                key=run_id,
                args_hash=digest(
                    {"case_id": case_id, "revision": revision, "proposal_id": proposal_id}
                ),
                result=case.expert_analysis,
            )
        )

    async def update(patch, record=None):
        from shopsteward_agent import RuntimeFailure

        async with db.session() as session, session.begin():
            case = await repo.visible(session, principal, case_id, lock=True)
            history = await session.get(Receipt, (history_owner, run_id), with_for_update=True)
            existing = history.result
            try:
                grant = current_case_principal(settings, principal.principal_id, case.store_id)
                authorized = bool({"operator", "admin"} & set(grant.roles))
            except AppError:
                authorized = False
            current = authorized and case_current(case, revision, proposal_id, run_id)
            if not current:
                # A stale run may finish accounting for already-sent requests,
                # but cannot reserve/send more work or overwrite current output.
                reserving = record is not None and record["status"] == "reserved"
                if set(patch) == {"budget"}:
                    old_budget = existing.get("budget", {})
                    reserving = any(
                        patch["budget"][key] > old_budget.get(key, 0)
                        for key in ("model_calls", "tool_calls")
                    )
                if reserving:
                    raise RuntimeFailure("case_input_changed")
            if record is not None:
                records = {
                    (item["run_id"], item["role"], item["call_index"]): item
                    for item in existing.get("call_records", [])
                }
                records[(record["run_id"], record["role"], record["call_index"])] = record
                patch = {**patch, "call_records": list(records.values())}
            history.result = {**existing, **patch}
            if current:
                case.expert_analysis = history.result

    async def persist_budget(value):
        await update({"budget": value})

    async def persist_call(record):
        await update({}, record=record)

    try:
        result = await analyze_case_experts(
            snapshot,
            case_id=case_id,
            revision_id=str(revision),
            run_id=run_id,
            settings=settings,
            proposal=proposal_doc,
            persist=persist_budget,
            record_call=persist_call,
        )
        await update(result)
    except Exception:
        # Keep already committed reservations/unknown usage. Re-authorize before
        # returning; a revoked owner cannot obtain stale analysis from this path.
        async with db.session() as session, session.begin():
            case = await repo.visible(session, principal, case_id, lock=True)
            history = await session.get(Receipt, (history_owner, run_id), with_for_update=True)
            existing = history.result
            history.result = {
                **existing,
                "status": "partial",
                "missing": ["EXPERT_ANALYSIS_UNAVAILABLE"],
                "cost_status": "unknown",
            }
            try:
                current_case_principal(settings, principal.principal_id, case.store_id)
                authorized = True
            except AppError:
                authorized = False
            if authorized and case_current(case, revision, proposal_id, run_id):
                case.expert_analysis = history.result
    async with db.session() as session:
        case = await repo.visible(session, principal, case_id)
        grant = current_case_principal(settings, principal.principal_id, case.store_id)
        return await repo.detail(session, await repo.visible(session, grant, case_id))
