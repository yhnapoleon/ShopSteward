from datetime import datetime

from sqlalchemy import select

from app.core.hashing import digest
from app.learning.models import (
    EpisodeEventRow,
    EpisodeRow,
    LearningOutbox,
    LearningPolicyRow,
    OutcomeRow,
)

ELIGIBLE = {
    "OPTIONS_READY",
    "ANALYSIS_BLOCKED",
    "PLAN_MATERIALIZED",
    "PLAN_READY",
    "RESULT_READY",
    "EXECUTION_OBSERVED",
}


async def consume(session, *, event_id):
    event = await session.get(LearningOutbox, event_id)
    if not event:
        return None
    pol = await session.get(LearningPolicyRow, event.scope_id, with_for_update=True)
    await session.refresh(event, with_for_update=True)
    if event.processed:
        link = await session.get(EpisodeEventRow, event.id)
        return link.episode_id if link else None
    if pol.mode == "off" or event.policy_version != pol.version:
        event.processed = True
        return None
    doc = event.document
    identifier = digest([pol.id, doc["intent_key"]])
    row = await session.get(EpisodeRow, identifier)
    if not row:
        row = EpisodeRow(
            id=identifier,
            scope_id=pol.id,
            intent_key=doc["intent_key"],
            task_family=doc["task_family"],
            eligible=False,
            evidence_ids=[],
            outcome_revision=0,
            occurred_at=datetime.fromisoformat(doc["observed_at"]),
        )
        session.add(row)
        await session.flush()
    row.evidence_ids = [*row.evidence_ids, event.id]
    if doc["event_type"] in ELIGIBLE:
        row.eligible = True
    if doc["event_type"] in {"CASE_CANCEL", "CASE_CANCELLED", "CANCELLED"}:
        row.eligible = False
    # Every observation is versioned. A model reply has no business-success semantics.
    payload = doc["payload"]
    outcome = {
        "procedural_status": "fail"
        if doc["event_type"] == "ANALYSIS_BLOCKED"
        else "pass"
        if doc["event_type"] in ELIGIBLE
        else "unknown",
        "decision_status": "pass"
        if doc["event_type"] in {"OPTIONS_READY", "PLAN_READY", "PLAN_MATERIALIZED"}
        else "unknown",
        "business_status": payload.get("business_status", "pending"),
        "execution_status": payload.get("execution_status"),
        "evidence_ids": [event.id],
        "metrics": payload.get("metrics", {}),
        "oracle_version": "learning-observation-v1",
    }
    previous = (
        await session.get(OutcomeRow, (row.id, row.outcome_revision))
        if row.outcome_revision
        else None
    )
    available_at = datetime.fromisoformat(doc["available_at"])
    outcome["cancelled"] = bool(
        (previous and previous.document.get("cancelled"))
        or doc["event_type"] in {"CASE_CANCEL", "CASE_CANCELLED", "CANCELLED"}
    )
    if outcome["cancelled"]:
        row.eligible = False
    if previous and (
        doc["event_type"] != "EXECUTION_OBSERVED" or available_at < previous.available_at
    ):
        # A later plan/chat event cannot erase an authoritative receipt or UNKNOWN observation.
        for key in ("business_status", "execution_status", "metrics"):
            outcome[key] = previous.document[key]
        outcome["evidence_ids"] = list(
            dict.fromkeys([*previous.document["evidence_ids"], event.id])
        )
    if previous:
        available_at = max(available_at, previous.available_at)
    row.outcome_revision += 1
    session.add(
        OutcomeRow(
            episode_id=row.id,
            revision=row.outcome_revision,
            document=outcome,
            available_at=available_at,
        )
    )
    session.add(EpisodeEventRow(event_id=event.id, episode_id=row.id))
    event.processed = True
    if doc["event_type"] == "EXECUTION_OBSERVED" and payload.get("mission_id"):
        from app.learning.monitoring import observe_business

        await observe_business(session, pol.id, payload["mission_id"], outcome, event.id)
    return row.id


async def drain(session, *, limit=100):
    ids = list(
        await session.scalars(
            select(LearningOutbox.id)
            .where(LearningOutbox.processed.is_(False))
            .order_by(LearningOutbox.created_at)
            .limit(limit)
        )
    )
    for identifier in ids:
        await consume(session, event_id=identifier)
    return len(ids)
