from datetime import timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.core.hashing import digest
from app.execution.models import ActionRow
from app.missions.models import InboundRow, MissionRow, PlanRow
from app.missions.repository import command, lock_mission, timeline
from app.operations.models import Store
from app.operations_cases.models import CaseEventRow, CaseRevisionRow, CaseRow, RecoveryProposalRow
from app.operations_cases.processor import capture_snapshot
from app.operations_cases.schemas import CaseDetail, CaseList
from app.planning.recovery.materialize import build_recovery_plan
from app.planning.recovery.schemas import RecoveryProposal
from app.planning.recovery.solver import SearchSpaceExceeded, solve
from app.planning.recovery.validation import validate_sources
from app.planning.schemas import RecoveryDecisionSnapshot


async def visible(session, principal, identifier, *, lock=False):
    row = await session.get(CaseRow, identifier)
    if row is None or row.owner_id != principal.principal_id:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Case is not visible or does not exist")
    authorize_store(principal, row.store_id)
    if lock:
        await lock_mission(session, row.mission_id)
        await session.refresh(row, with_for_update=True)
    return row


def check_revision(row, expected):
    if row.current_revision != expected:
        raise AppError(
            409, "CASE_REVISION_CONFLICT", "The Case has newer inputs; refresh before continuing"
        )
    if row.status in {"CANCELLED", "RESOLVED", "CLOSED"}:
        raise AppError(409, "CASE_TERMINAL", "This Case is closed")


async def event(session, row, kind, payload=None):
    row.event_seq += 1
    row.updated_at = await session.scalar(select(func.clock_timestamp()))
    session.add(
        CaseEventRow(
            case_id=row.id,
            seq=row.event_seq,
            kind=kind,
            revision=row.current_revision,
            payload=payload or {},
            created_at=row.updated_at,
        )
    )
    from app.learning.capture import case_event

    await case_event(session, row, kind)


async def detail(session, row):
    mission = await session.get(MissionRow, row.mission_id)
    store = await session.get(Store, row.store_id)
    revision = await session.get(CaseRevisionRow, (row.id, row.current_revision))
    proposal_row = (
        await session.get(RecoveryProposalRow, row.proposal_id) if row.proposal_id else None
    )
    proposal = RecoveryProposal.model_validate(proposal_row.document) if proposal_row else None
    plan = await session.get(PlanRow, row.plan_id) if row.plan_id else None
    action = (
        await session.scalar(select(ActionRow).where(ActionRow.plan_id == row.plan_id))
        if row.plan_id
        else None
    )
    execution_status = None
    if action:
        execution_status = action.status
        if action.status == "SUCCEEDED":
            inbound = await session.get(InboundRow, (action.id, row.sku_id))
            execution_status = (
                "RECEIVED"
                if inbound and inbound.received_qty == inbound.ordered_qty
                else "PARTIALLY_RECEIVED"
                if inbound and inbound.received_qty > 0
                else "ACCEPTED"
            )
    elif plan:
        execution_status = plan.status
    now = await session.scalar(select(func.clock_timestamp()))
    current_plan_revision = bool(
        plan and plan.document.get("recovery_intent", {}).get("revision") == row.current_revision
    )
    source = plan.document["input_snapshot"] if current_plan_revision else revision.snapshot
    stale = bool(
        proposal
        and (
            proposal.expires_at <= now
            or source is None
            or source["state"]["state_version"] != store.state_version
            or source["mission_version"] != mission.mission_version
        )
    )
    values = revision.inputs
    return CaseDetail(
        id=row.id,
        mission_id=row.mission_id,
        store_id=row.store_id,
        sku_id=row.sku_id,
        status=row.status,
        current_revision=row.current_revision,
        objective=values["objective"],
        budget_minor=values["budget_minor"],
        max_purchase_qty=values.get("max_purchase_qty"),
        daily_demand=values.get("daily_demand"),
        proposal=proposal,
        plan_id=row.plan_id,
        plan_status=(
            "EXPIRED"
            if plan.status == "PENDING_APPROVAL" and plan.expires_at <= now
            else plan.status
        )
        if plan
        else None,
        plan_revision=plan.document.get("recovery_intent", {}).get("revision") if plan else None,
        action_id=action.id if action else None,
        execution_status=execution_status,
        missing_inputs=row.missing_inputs,
        evidence=revision.evidence,
        current_mission_version=mission.mission_version,
        current_state_version=store.state_version,
        current_plan_id=mission.current_plan_id,
        stale=stale,
        expert_analysis=row.expert_analysis,
        followup_enabled=row.followup_enabled,
        supplier_ids=revision.inputs.get("supplier_ids"),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def listing(session, principal, store_id, limit):
    authorize_store(principal, store_id)
    rows = list(
        await session.scalars(
            select(CaseRow)
            .where(CaseRow.store_id == store_id, CaseRow.owner_id == principal.principal_id)
            .order_by(CaseRow.created_at.desc(), CaseRow.id.desc())
            .limit(limit)
        )
    )
    return CaseList(items=[await detail(session, row) for row in rows])


async def create(session, body, principal, key):
    _, mission = await lock_mission(session, body.mission_id)
    authorize_store(principal, mission.store_id)
    receipt, replay = await command(
        session, principal.principal_id, "create_case", key, body.model_dump(mode="json")
    )
    if replay:
        return CaseDetail.model_validate(receipt.response)
    if mission.status != "ACTIVE":
        raise AppError(409, "MISSION_NOT_ACTIVE", "Recovery requires an active Mission")
    now = await session.scalar(select(func.clock_timestamp()))
    row = CaseRow(
        id=str(uuid4()),
        mission_id=mission.id,
        store_id=mission.store_id,
        sku_id=mission.sku_id,
        owner_id=principal.principal_id,
        status="OPEN",
        current_revision=1,
        event_seq=0,
        missing_inputs=[],
        followup_enabled=False,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    session.add(
        CaseRevisionRow(
            case_id=row.id,
            revision=1,
            inputs=body.model_dump(mode="json"),
            evidence=[],
            created_at=now,
        )
    )
    await event(session, row, "CASE_CREATED")
    await session.flush()
    result = await detail(session, row)
    receipt.response = result.model_dump(mode="json")
    return result


async def analyze(session, row, body, principal, key, settings):
    receipt, replay = await command(
        session,
        principal.principal_id,
        "analyze_case",
        key,
        {"case_id": row.id, **body.model_dump(mode="json")},
    )
    if replay:
        return CaseDetail.model_validate(receipt.response)
    check_revision(row, body.expected_revision)
    revision = await session.get(CaseRevisionRow, (row.id, row.current_revision))
    if row.proposal_id is None:
        mission = await session.get(MissionRow, row.mission_id)
        try:
            snapshot, evidence = await capture_snapshot(session, row, revision, mission, settings)
            result = solve(snapshot.recovery)
        except (AppError, ValidationError, ValueError) as exc:
            code = (
                exc.code
                if isinstance(exc, AppError)
                else "SEARCH_SPACE_EXCEEDED"
                if isinstance(exc, SearchSpaceExceeded)
                else "RECOVERY_INPUT_INVALID"
            )
            row.status = (
                "NEEDS_INPUT"
                if code
                in {"DAILY_DEMAND_REQUIRED", "OFFER_SELECTION_REQUIRED", "RECOVERY_INPUT_INVALID"}
                else "BLOCKED"
            )
            row.missing_inputs = [code]
            await event(session, row, "ANALYSIS_BLOCKED", {"reason": code})
        else:
            now = snapshot.evaluated_at
            proposal = RecoveryProposal(
                **result.model_dump(),
                id=str(uuid4()),
                case_id=row.id,
                revision=row.current_revision,
                snapshot_hash=digest(snapshot.model_dump(mode="json")),
                candidate_set_hash=digest(result.model_dump(mode="json")),
                proposal_hash="",
                created_at=now,
                expires_at=min(
                    now + timedelta(seconds=settings.plan_ttl_seconds),
                    snapshot.forecast.valid_until,
                ),
            )
            proposal.proposal_hash = "sha256:" + digest(
                proposal.model_dump(mode="json", exclude={"proposal_hash"})
            )
            revision.snapshot = snapshot.model_dump(mode="json")
            revision.evidence = evidence
            session.add(
                RecoveryProposalRow(
                    id=proposal.id,
                    case_id=row.id,
                    revision=row.current_revision,
                    document=proposal.model_dump(mode="json"),
                )
            )
            row.proposal_id, row.status, row.missing_inputs = proposal.id, "OPTIONS_READY", []
            await event(session, row, "OPTIONS_READY", {"proposal_id": proposal.id})
    await session.flush()
    result = await detail(session, row)
    receipt.response = result.model_dump(mode="json")
    return result


async def invalidate_pending(session, row, mission):
    if not row.plan_id:
        return
    plan = await session.get(PlanRow, row.plan_id, with_for_update=True)
    if plan and plan.status == "PENDING_APPROVAL":
        plan.status = "SUPERSEDED"
        if mission.current_plan_id == plan.id:
            mission.current_plan_id = None
        if mission.planning_context and mission.planning_context.get("plan_id") == plan.id:
            mission.planning_context = None
    # Already queued/sent Actions retain their association. Send validation fences the revision.


async def revise(session, row, body, principal, key):
    receipt, replay = await command(
        session,
        principal.principal_id,
        "revise_case",
        key,
        {"case_id": row.id, **body.model_dump(mode="json")},
    )
    if replay:
        return CaseDetail.model_validate(receipt.response)
    check_revision(row, body.expected_revision)
    old = await session.get(CaseRevisionRow, (row.id, row.current_revision))
    inputs = dict(old.inputs)
    updates = body.model_dump(mode="json", exclude_unset=True, exclude={"expected_revision"})
    if any(updates.get(k, 0) is None for k in ("objective", "budget_minor")):
        raise AppError(422, "RECOVERY_INPUT_INVALID", "Objective and budget cannot be null")
    inputs.update(updates)
    mission = await session.get(MissionRow, row.mission_id)
    await invalidate_pending(session, row, mission)
    row.current_revision += 1
    row.proposal_id, row.expert_analysis, row.status, row.missing_inputs = None, None, "OPEN", []
    now = await session.scalar(select(func.clock_timestamp()))
    session.add(
        CaseRevisionRow(
            case_id=row.id,
            revision=row.current_revision,
            inputs=inputs,
            evidence=[],
            created_at=now,
        )
    )
    await event(session, row, "CASE_REVISED")
    await session.flush()
    result = await detail(session, row)
    receipt.response = result.model_dump(mode="json")
    return result


async def materialize(session, row, body, principal, key, settings):
    receipt, replay = await command(
        session,
        principal.principal_id,
        "materialize_case",
        key,
        {"case_id": row.id, **body.model_dump(mode="json")},
    )
    if replay:
        return CaseDetail.model_validate(receipt.response)
    check_revision(row, body.expected_revision)
    store, mission = await lock_mission(session, row.mission_id)
    if (
        mission.mission_version != body.expected_mission_version
        or store.state_version != body.expected_state_version
        or mission.current_plan_id != body.expected_current_plan_id
    ):
        raise AppError(409, "PLAN_VERSION_CONFLICT", "Mission, state or current plan changed")
    if row.proposal_id != body.proposal_id:
        raise AppError(409, "PROPOSAL_STALE", "This is not the current recovery proposal")
    saved = await session.get(RecoveryProposalRow, row.proposal_id)
    proposal = RecoveryProposal.model_validate(saved.document)
    if proposal.proposal_hash != body.proposal_hash:
        raise AppError(409, "PROPOSAL_HASH_CONFLICT", "Recovery comparison hash changed")
    now = await session.scalar(select(func.clock_timestamp()))
    if proposal.expires_at <= now:
        raise AppError(409, "PLAN_EXPIRED", "Recovery comparison expired")
    revision = await session.get(CaseRevisionRow, (row.id, row.current_revision))
    snapshot = RecoveryDecisionSnapshot.model_validate(revision.snapshot)
    if digest(snapshot.model_dump(mode="json")) != proposal.snapshot_hash:
        raise AppError(409, "PROPOSAL_INVALID", "Frozen analysis snapshot changed")
    await validate_sources(session, store, mission, snapshot, settings, now)
    if store.active_action_id or mission.current_action_id:
        raise AppError(
            409, "ACTION_IN_PROGRESS", "Reconcile the current purchase before adopting another"
        )
    if row.plan_id:
        previous = await session.scalar(select(ActionRow).where(ActionRow.plan_id == row.plan_id))
        if previous and previous.status == "SUCCEEDED":
            raise AppError(
                409,
                "EMERGENCY_PURCHASE_ALREADY_ACCEPTED",
                "This Case already has its one accepted emergency purchase",
            )
    result = solve(snapshot.recovery)
    if digest(result.model_dump(mode="json")) != proposal.candidate_set_hash:
        raise AppError(409, "PROPOSAL_INVALID", "Recovery candidate comparison changed")
    selected = next((c for c in result.candidates if c.id == body.candidate_id), None)
    if (
        selected is None
        or not selected.feasible
        or not selected.executable
        or selected.quantity == 0
    ):
        raise AppError(
            422,
            "CANDIDATE_NOT_EXECUTABLE",
            "Choose a feasible purchase; waiting uses the separate control",
        )
    offer = next(o for o in snapshot.recovery.offers if o.supplier_id == selected.supplier_id)
    if not offer.valid_from <= now < offer.valid_until:
        raise AppError(409, "OFFER_EXPIRED", "Selected supplier offer expired")
    old = (
        await session.get(PlanRow, mission.current_plan_id, with_for_update=True)
        if mission.current_plan_id
        else None
    )
    if old and old.status == "PENDING_APPROVAL":
        old.status = "SUPERSEDED"
    mission.mission_version += 1
    plan = build_recovery_plan(
        mission, snapshot, proposal, selected.id, principal.principal_id, proposal.expires_at
    )
    session.add(
        PlanRow(
            id=plan.id,
            mission_id=mission.id,
            plan_version=plan.plan_version,
            state_version=plan.state_version,
            input_hash=proposal.snapshot_hash,
            status=plan.status,
            document=plan.model_dump(mode="json"),
            created_at=now,
            expires_at=plan.expires_at,
        )
    )
    mission.plan_counter, mission.current_plan_id = plan.plan_version, plan.id
    mission.planning_context = {
        "kind": "recovery",
        "case_id": row.id,
        "revision": row.current_revision,
        "plan_id": plan.id,
    }
    mission.updated_at = now
    row.plan_id = plan.id
    await event(
        session, row, "PLAN_MATERIALIZED", {"plan_id": plan.id, "candidate_id": selected.id}
    )
    await timeline(
        session,
        mission,
        "PLAN_CREATED",
        plan.explanation,
        actor=principal.principal_id,
        references=[{"type": "plan", "id": plan.id, "version": str(plan.plan_version)}],
    )
    await session.flush()
    response = await detail(session, row)
    receipt.response = response.model_dump(mode="json")
    return response


async def control(session, row, body, principal, key):
    receipt, replay = await command(
        session,
        principal.principal_id,
        "control_case",
        key,
        {"case_id": row.id, **body.model_dump(mode="json")},
    )
    if replay:
        return CaseDetail.model_validate(receipt.response)
    check_revision(row, body.expected_revision)
    mission = await session.get(MissionRow, row.mission_id)
    if body.operation == "refresh":
        from app.operations_cases.schemas import CaseRevise

        response = await revise(
            session,
            row,
            CaseRevise(expected_revision=body.expected_revision),
            principal,
            key + ":refresh",
        )
    else:
        if body.operation in {"enable_followup", "disable_followup"}:
            from app.operations_cases.jobs import cancel_followup, queue_followup

            row.followup_enabled = body.operation == "enable_followup"
            if row.followup_enabled:
                await queue_followup(session, row)
            else:
                await cancel_followup(session, row)
        elif body.operation == "cancel":
            await invalidate_pending(session, row, mission)
            row.status, row.followup_enabled = "CANCELLED", False
            row.expert_analysis = None
            from app.operations_cases.jobs import cancel_followup

            await cancel_followup(session, row)
        else:
            if row.proposal_id is None:
                raise AppError(
                    409, "PROPOSAL_REQUIRED", "Analyze this Case before adopting waiting"
                )
            view = await detail(session, row)
            if view.stale:
                raise AppError(
                    409, "PROPOSAL_STALE", "Analyze a fresh revision before adopting waiting"
                )
            if mission.current_action_id:
                raise AppError(
                    409,
                    "ACTION_IN_PROGRESS",
                    "An existing purchase must be reconciled before adopting waiting",
                )
            await invalidate_pending(session, row, mission)
            row.status = "MONITORING"
        await event(session, row, "CASE_" + body.operation.upper())
        await session.flush()
        response = await detail(session, row)
    receipt.response = response.model_dump(mode="json")
    return response
