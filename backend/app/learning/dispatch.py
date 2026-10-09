from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.collector import drain
from app.learning.models import BatchRow, EpisodeRow, LearningOutbox, LearningPolicyRow
from app.learning.policy import trigger_candidates
from app.scheduling.repository import enqueue


def current_owner(settings, pol):
    for principal in settings.auth_tokens:
        if principal.kind == "user" and principal.principal_id == pol.principal_id:
            try:
                authorize_store(principal, pol.store_id)
            except AppError:
                continue
            if {"operator", "admin"} & set(principal.roles):
                return principal
    return None


async def enqueue_due(session, *, settings):
    if not settings.learning_enabled:
        return []
    await drain(session)
    if not settings.learning_generation_enabled:
        return []
    now = await session.scalar(select(func.clock_timestamp()))
    day = now.astimezone(ZoneInfo("Asia/Shanghai")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    policies = list(
        await session.scalars(
            select(LearningPolicyRow)
            .where(LearningPolicyRow.mode != "off")
            .order_by(LearningPolicyRow.id)
            .with_for_update(skip_locked=True)
            .limit(100)
        )
    )
    enqueued = []
    for pol in policies:
        if not current_owner(settings, pol):
            continue
        count = await session.scalar(
            select(func.count())
            .select_from(BatchRow)
            .where(BatchRow.scope_id == pol.id, BatchRow.created_at >= day)
        )
        if count >= 3:
            continue
        rows = list(
            await session.scalars(
                select(EpisodeRow)
                .where(EpisodeRow.scope_id == pol.id, EpisodeRow.eligible.is_(True))
                .order_by(EpisodeRow.occurred_at.desc())
                .limit(100)
            )
        )
        episodes = []
        for row in rows:
            sources = list(
                await session.scalars(
                    select(LearningOutbox).where(
                        LearningOutbox.id.in_(row.evidence_ids),
                        LearningOutbox.policy_version == pol.version,
                    )
                )
            )
            if not sources or any("source:" + e.id in pol.blocked_concepts for e in sources):
                continue
            first = min(sources, key=lambda s: s.created_at)
            business_date = first.document.get("payload", {}).get("business_date")
            episodes.append(
                {
                    "id": row.id,
                    "task_family": row.task_family,
                    "eligible": True,
                    "occurred_at": business_date + "T12:00:00+08:00"
                    if business_date
                    else row.occurred_at.isoformat(),
                }
            )
        for trigger in trigger_candidates(episodes, set(pol.consumed)):
            # First-ten is a checkpoint; it does not request unclassified skills.
            if trigger["kind"] == "first_ten":
                pol.consumed = sorted(set([*pol.consumed, "first_ten"]))
                continue
            included = [row for row in rows if row.id in trigger["episode_ids"]]
            evidence_ids = sorted({e for row in included for e in row.evidence_ids})
            evidence = list(
                await session.scalars(
                    select(LearningOutbox).where(
                        LearningOutbox.id.in_(evidence_ids),
                        LearningOutbox.policy_version == pol.version,
                    )
                )
            )
            fingerprint = digest(sorted((e.id, e.digest) for e in evidence))
            trigger = {**trigger, "evidence_ids": sorted(e.id for e in evidence)}
            identifier = digest([pol.id, pol.version, trigger["family"], fingerprint])
            if await session.get(BatchRow, identifier):
                continue
            if count >= 3:
                break
            session.add(
                BatchRow(
                    id=identifier,
                    scope_id=pol.id,
                    policy_version=pol.version,
                    trigger=trigger,
                    evidence_digest=fingerprint,
                    status="QUEUED",
                    usage={},
                )
            )
            await session.flush()
            await enqueue(
                session,
                job_type="learning_batch",
                dedup_key="learn:" + identifier,
                store_id=pol.store_id,
                payload={"batch_id": identifier},
                trigger_source="EVENT",
            )
            enqueued.append(identifier)
            count += 1
    return enqueued
