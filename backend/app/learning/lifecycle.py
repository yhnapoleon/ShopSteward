from datetime import UTC, datetime

from sqlalchemy import select

from app.agent_bridge.repository import receipt, replay
from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.models import (
    AssetRevisionRow,
    AssetRow,
    EpisodeEventRow,
    EpisodeRow,
    EvaluationRow,
    OutcomeRow,
)
from app.learning.quality import RUBRIC_VERSION, decide
from app.learning.repository import evidence_rows, get_asset, policy


def policy_dto(row):
    return {
        "version": row.version,
        "mode": row.mode,
        "enabled_at": row.enabled_at.isoformat() if row.enabled_at else None,
    }


async def asset_dto(session, row):
    revisions = list(
        await session.scalars(
            select(AssetRevisionRow)
            .where(AssetRevisionRow.asset_id == row.id)
            .order_by(AssetRevisionRow.revision.desc())
        )
    )
    result = []
    for rev in revisions:
        evaluation = (
            await session.get(EvaluationRow, rev.evaluation_id) if rev.evaluation_id else None
        )
        latest_check = await session.scalar(
            select(EvaluationRow)
            .where(EvaluationRow.asset_id == row.id, EvaluationRow.revision == rev.revision)
            .order_by(EvaluationRow.report["evaluated_at"].astext.desc())
            .limit(1)
        )
        result.append(
            {
                "revision": rev.revision,
                "status": rev.status,
                "spec": rev.spec,
                "content_hash": rev.content_hash,
                "evidence_ids": rev.evidence_ids,
                "evaluation_id": rev.evaluation_id,
                "quality": evaluation.report if evaluation else None,
                "quality_decision": evaluation.decision if evaluation else None,
                "latest_check": {
                    "id": latest_check.id,
                    "decision": latest_check.decision,
                    "evaluated_at": latest_check.report["evaluated_at"],
                }
                if latest_check and (not evaluation or latest_check.id != evaluation.id)
                else None,
            }
        )
    return {
        "id": row.id,
        "version": row.version,
        "kind": row.kind,
        "task_family": row.task_family,
        "active_revision": row.active_revision,
        "revisions": result,
    }


async def change_policy(session, *, scope, body, key):
    pol = await policy(session, scope, lock=True)
    owner = "learning-policy:" + pol.id
    args = body.model_dump()
    old = await replay(session, owner, key, args)
    if old is not None:
        return old
    if pol.version != body.expected_version:
        raise AppError(409, "VERSION_CONFLICT", "Learning policy changed")
    if pol.mode != body.mode:
        pol.mode = body.mode
        pol.version += 1
        pol.enabled_at = datetime.now(UTC) if pol.mode != "off" else None
        # Consent version changes invalidate all previous admission decisions.
        await suspend_scope(session, pol.id, "policy_changed")
    result = policy_dto(pol)
    receipt(session, owner, key, args, result)
    return result


async def suspend_scope(session, scope_identifier, reason):
    rows = list(
        await session.scalars(select(AssetRow).where(AssetRow.scope_id == scope_identifier))
    )
    for row in rows:
        if row.active_revision is not None:
            rev = await session.get(AssetRevisionRow, (row.id, row.active_revision))
            rev.status = "SUSPENDED"
            row.active_revision = None
            row.version += 1


def runtime_hashes(settings, principal):
    from app.agent_bridge.context_repository import configured_profile
    from app.agent_bridge.tools import tool_schemas
    from app.planning.engine import RULE_VERSION

    return {
        "tool_catalog_hash": digest(tool_schemas(principal, settings)),
        "model_profile_hash": digest([configured_profile(settings), settings.agent_base_url]),
        "business_rule_version": RULE_VERSION + ":recovery-v1",
        "rubric_version": RUBRIC_VERSION,
    }


async def binding(session, *, scope, asset, revision, settings, principal):
    pol = await policy(session, scope)
    rows = await evidence_rows(session, scope, revision.evidence_ids)
    if asset.concept_key in pol.blocked_concepts or any(
        "source:" + r.id in pol.blocked_concepts for r in rows
    ):
        raise AppError(409, "LEARNING_FORGOTTEN", "Evidence has been forgotten")
    if any(r.policy_version != pol.version for r in rows):
        raise AppError(409, "LEARNING_EVIDENCE_STALE", "Evidence consent has changed")
    episodes = list(
        await session.scalars(
            select(EpisodeRow)
            .join(EpisodeEventRow, EpisodeEventRow.episode_id == EpisodeRow.id)
            .where(EpisodeEventRow.event_id.in_(revision.evidence_ids))
            .distinct()
        )
    )
    outcomes = []
    for episode in episodes:
        if not episode.eligible:
            raise AppError(409, "LEARNING_EVIDENCE_STALE", "Source episode is no longer eligible")
        outcome = await session.get(OutcomeRow, (episode.id, episode.outcome_revision))
        outcomes.append(
            (episode.id, episode.outcome_revision, outcome.document if outcome else None)
        )
    return {
        "asset_id": asset.id,
        "revision": revision.revision,
        "content_hash": revision.content_hash,
        "evidence_digest": digest([sorted((r.id, r.digest) for r in rows), sorted(outcomes)]),
        "policy_version": pol.version,
        **runtime_hashes(settings, principal),
    }


async def transition(session, *, scope, asset_id, body, key, settings, principal):
    pol = await policy(session, scope, lock=True)
    row = await get_asset(session, scope, asset_id)
    owner = "learning-transition:" + row.id
    args = body.model_dump()
    old = await replay(session, owner, key, args)
    if old is not None:
        return old
    if row.version != body.expected_version:
        raise AppError(409, "VERSION_CONFLICT", "Learning asset changed")
    revision = await session.get(AssetRevisionRow, (row.id, body.revision))
    if not revision:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Skill revision does not exist")
    if revision.status == "REVOKED" or row.concept_key in pol.blocked_concepts:
        raise AppError(409, "LEARNING_FORGOTTEN", "This skill has been revoked")
    action = body.action
    if action in {"activate", "rollback"}:
        if pol.mode == "off":
            raise AppError(409, "LEARNING_DISABLED", "Learning is disabled")
        evaluation = (
            await session.get(EvaluationRow, body.evaluation_id) if body.evaluation_id else None
        )
        if not evaluation or (evaluation.asset_id, evaluation.revision) != (
            row.id,
            revision.revision,
        ):
            raise AppError(409, "LEARNING_QUALITY_REQUIRED", "Independent evaluation is required")
        expected = await binding(
            session,
            scope=scope,
            asset=row,
            revision=revision,
            settings=settings,
            principal=principal,
        )
        decision = decide(evaluation.report, expected)
        if decision["status"] != "pass":
            raise AppError(
                409,
                "LEARNING_QUALITY_REQUIRED",
                "Skill evaluation does not pass: " + ", ".join(decision["reasons"]),
            )
        if row.active_revision and row.active_revision != revision.revision:
            previous = await session.get(AssetRevisionRow, (row.id, row.active_revision))
            previous.status = "SUPERSEDED"
        revision.status = "ACTIVE"
        revision.evaluation_id = evaluation.id
        row.active_revision = revision.revision
    else:
        states = {
            "shadow": "SHADOW",
            "suspend": "SUSPENDED",
            "archive": "ARCHIVED",
            "revoke": "REVOKED",
        }
        if action == "shadow" and revision.status not in {
            "DRAFT",
            "VALIDATING",
            "SUSPENDED",
            "SHADOW",
        }:
            raise AppError(409, "LEARNING_STATE_CONFLICT", "This revision cannot enter shadow")
        revision.status = states[action]
        if row.active_revision == revision.revision:
            row.active_revision = None
        if action == "revoke":
            pol.blocked_concepts = sorted(set([*pol.blocked_concepts, row.concept_key]))
            siblings = list(
                await session.scalars(
                    select(AssetRevisionRow).where(AssetRevisionRow.asset_id == row.id)
                )
            )
            for sibling in siblings:
                sibling.status = "REVOKED"
                pol.blocked_concepts = sorted(
                    set([*pol.blocked_concepts, *("source:" + e for e in sibling.evidence_ids)])
                )
            row.active_revision = None
    row.version += 1
    await session.flush()
    result = await asset_dto(session, row)
    receipt(session, owner, key, args, result)
    return result


async def forget(session, *, scope, body, key):
    pol = await policy(session, scope, lock=True)
    row = await get_asset(session, scope, body.asset_id)
    owner = "learning-forget:" + pol.id
    args = body.model_dump()
    old = await replay(session, owner, key, args)
    if old is not None:
        return old
    if pol.version != body.expected_version:
        raise AppError(409, "VERSION_CONFLICT", "Learning policy changed")
    pol.blocked_concepts = sorted(set([*pol.blocked_concepts, row.concept_key]))
    revs = list(
        await session.scalars(select(AssetRevisionRow).where(AssetRevisionRow.asset_id == row.id))
    )
    for rev in revs:
        rev.status = "REVOKED"
        pol.blocked_concepts = sorted(
            set([*pol.blocked_concepts, *("source:" + e for e in rev.evidence_ids)])
        )
    row.active_revision = None
    row.version += 1
    result = {"asset_id": row.id, "status": "REVOKED", "policy_version": pol.version}
    receipt(session, owner, key, args, result)
    return result
