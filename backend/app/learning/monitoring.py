"""Online observations are separate from reviewed causal attribution."""

from sqlalchemy import select

from app.agent_bridge.models import AgentRun, Conversation, ToolInvocation
from app.core.errors import AppError
from app.learning.models import ApplicationRow, AssetRevisionRow, AssetRow
from app.learning.policy import assess_drift
from app.learning.projections import tool_trace
from app.learning.repository import policy


async def observe_run(session, run):
    if not session.info.get("learning_enabled"):
        return
    applications = list(
        await session.scalars(select(ApplicationRow).where(ApplicationRow.run_id == run.id))
    )
    if not applications:
        return
    calls = list(
        await session.scalars(select(ToolInvocation).where(ToolInvocation.run_id == run.id))
    )
    traces = [{"invocation_id": c.invocation_id, **tool_trace(c.tool, {}, c.result)} for c in calls]
    for app in applications:
        app.outcome = {
            **app.outcome,
            "run_status": run.status,
            "tool_count": len(calls),
            "traces": traces,
            "business_status": app.outcome.get("business_status", "pending"),
        }
        # Selection and matching tool names do not prove the procedure was followed.


async def observe_business(session, scope_identifier, mission_id, payload, event_id):
    applications = list(
        await session.scalars(
            select(ApplicationRow)
            .join(AgentRun, AgentRun.id == ApplicationRow.run_id)
            .join(Conversation, Conversation.id == AgentRun.conversation_id)
            .where(
                ApplicationRow.scope_id == scope_identifier, Conversation.mission_id == mission_id
            )
        )
    )
    for app in applications:
        app.outcome = {
            **app.outcome,
            "business_status": payload.get("business_status", "pending"),
            "business_evidence_id": event_id,
            "metrics": payload.get("metrics", {}),
            "attribution": app.outcome.get("attribution", "unresolved"),
        }


async def feedback(session, *, scope, application_id, body):
    pol = await policy(session, scope, lock=True)
    row = await session.get(ApplicationRow, application_id)
    if not row or row.scope_id != pol.id:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Application is not visible")
    if body.expected_feedback_version != row.outcome.get("feedback_version", 0):
        raise AppError(409, "VERSION_CONFLICT", "Feedback changed")
    known = {r["invocation_id"] for r in row.outcome.get("traces", [])}
    if body.executed and (not body.evidence_ids or not set(body.evidence_ids) <= known):
        raise AppError(
            422, "LEARNING_EVIDENCE_INVALID", "Executed feedback requires observed tool evidence"
        )
    row.stage = "executed" if body.executed else "selected"
    row.outcome = {
        **row.outcome,
        "status": body.status if body.executed else "unknown",
        "feedback_version": body.expected_feedback_version + 1,
        "feedback_by": scope.principal_id,
        "feedback_evidence_ids": body.evidence_ids,
        "attribution": body.attribution,
    }
    applications = list(
        await session.scalars(
            select(ApplicationRow)
            .where(ApplicationRow.asset_id == row.asset_id, ApplicationRow.revision == row.revision)
            .order_by(ApplicationRow.created_at.desc())
            .limit(100)
        )
    )
    if assess_drift([{"stage": a.stage, **a.outcome} for a in reversed(applications)]):
        asset = await session.get(AssetRow, row.asset_id)
        rev = await session.get(AssetRevisionRow, (asset.id, row.revision))
        if asset.active_revision == row.revision:
            asset.active_revision = None
            asset.version += 1
            rev.status = "SUSPENDED"
    return {"id": row.id, "stage": row.stage, "outcome": row.outcome}
