from uuid import uuid4

from sqlalchemy import func, select, tuple_

from app.alerts.models import AlertRow
from app.alerts.schemas import Alert, AlertFacts, AlertList
from app.core.errors import AppError
from app.core.hashing import digest
from app.core.pagination import decode_cursor, encode_cursor
from app.missions.repository import command, lock_mission, timeline

SEVERITY = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


async def reconcile(
    session, mission, findings, evaluated_types, state_version, plan_id=None, *, action_id=None
):
    """Caller holds store/Mission locks and commits through the worker lease fence."""
    now = await session.scalar(select(func.clock_timestamp()))
    existing = list(
        await session.scalars(
            select(AlertRow)
            .where(
                AlertRow.mission_id == mission.id,
                AlertRow.status != "RESOLVED",
                AlertRow.type.in_(evaluated_types),
                AlertRow.facts["action_id"].astext == action_id if action_id else True,
            )
            .with_for_update()
        )
    )
    active = {row.scope_key: row for row in existing}
    seen = set()
    for finding in findings:
        if finding.type not in evaluated_types:
            raise ValueError("Finding type was not evaluated")
        facts = AlertFacts.model_validate(finding.facts).model_dump(mode="json", exclude_unset=True)
        key = digest(
            [
                mission.store_id,
                mission.id,
                mission.sku_id,
                finding.type,
                facts.get("action_id") if finding.type == "ACTION_EXCEPTION" else None,
            ]
        )
        seen.add(key)
        row = active.get(key)
        transition = None
        if row is None:
            row = AlertRow(
                id=str(uuid4()),
                store_id=mission.store_id,
                mission_id=mission.id,
                sku_id=mission.sku_id,
                scope_key=key,
                type=finding.type,
                severity=finding.severity,
                status="OPEN",
                first_seen_at=now,
            )
            session.add(row)
            transition = "ALERT_OPENED"
        elif SEVERITY[finding.severity] > SEVERITY[row.severity]:
            row.status = "OPEN"
            transition = "ALERT_ESCALATED"
        row.severity = finding.severity
        row.summary = finding.summary
        row.facts = facts
        row.state_version = state_version
        row.related_plan_id = plan_id
        row.last_seen_at = now
        if transition:
            await timeline(
                session,
                mission,
                transition,
                f"{finding.type}：{finding.summary}",
                references=[
                    {"type": "alert", "id": row.id},
                    {"type": "mission", "id": mission.id, "version": str(mission.mission_version)},
                ],
            )
    for key, row in active.items():
        if key not in seen:
            row.status = "RESOLVED"
            row.resolved_at = now
            # Retain the last observed risk facts and their actual computation version.
            await timeline(
                session,
                mission,
                "ALERT_RESOLVED",
                f"{row.type}：状态版本{state_version}的新鲜输入确认风险已解除。",
                references=[{"type": "alert", "id": row.id}]
                + ([{"type": "plan", "id": plan_id}] if plan_id else []),
            )
    await session.flush()


async def acknowledge(session, alert_id, principal, key):
    initial = await session.get(AlertRow, alert_id)
    if initial is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Alert does not exist")
    _, mission = await lock_mission(session, initial.mission_id)
    row = await session.scalar(
        select(AlertRow)
        .where(AlertRow.id == alert_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    receipt, replay = await command(
        session, principal, "acknowledge_alert", key, {"alert_id": alert_id}
    )
    if replay:
        return Alert.model_validate(receipt.response)
    if row.status == "RESOLVED":
        raise AppError(409, "ALERT_RESOLVED", "Resolved alerts cannot be acknowledged")
    if row.status == "OPEN":
        row.status = "ACKNOWLEDGED"
        row.acknowledged_by = principal
        row.acknowledged_at = await session.scalar(select(func.clock_timestamp()))
        await timeline(
            session,
            mission,
            "ALERT_ACKNOWLEDGED",
            f"已知晓{row.type}；风险尚未解除。",
            actor=principal,
            references=[{"type": "alert", "id": row.id}],
        )
    response = Alert.model_validate(row)
    receipt.response = response.model_dump(mode="json", exclude_unset=True)
    return response


async def list_alerts(session, store_id, mission_id, status, cursor, limit):
    scope = ["alerts", store_id, mission_id, status]
    anchor = decode_cursor(cursor, scope)
    query = select(AlertRow).where(AlertRow.store_id == store_id)
    if mission_id:
        query = query.where(AlertRow.mission_id == mission_id)
    if status:
        query = query.where(AlertRow.status == status)
    if anchor:
        query = query.where(tuple_(AlertRow.first_seen_at, AlertRow.id) < anchor)
    rows = list(
        await session.scalars(
            query.order_by(AlertRow.first_seen_at.desc(), AlertRow.id.desc()).limit(limit + 1)
        )
    )
    return AlertList(
        items=[Alert.model_validate(row) for row in rows[:limit]],
        next_cursor=encode_cursor(scope, rows[limit - 1]) if len(rows) > limit else None,
    )
