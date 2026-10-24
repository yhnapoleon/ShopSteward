from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.models import (
    AssetRevisionRow,
    AssetRow,
    EvidenceLinkRow,
    LearningOutbox,
    LearningPolicyRow,
)
from app.learning.schemas import LearningScope, SkillSpec


def scope_id(scope):
    return digest(LearningScope.model_validate(scope).model_dump())


async def policy(session, scope, *, lock=False):
    scope = LearningScope.model_validate(scope)
    identifier = scope_id(scope)
    await session.execute(
        insert(LearningPolicyRow)
        .values(
            id=identifier,
            **scope.model_dump(),
            version=0,
            mode="off",
            blocked_concepts=[],
            consumed=[],
        )
        .on_conflict_do_nothing()
    )
    return await session.get(
        LearningPolicyRow, identifier, with_for_update=lock, populate_existing=lock
    )


async def get_asset(session, scope, identifier):
    asset = await session.get(AssetRow, identifier)
    if asset is None or asset.scope_id != scope_id(scope):
        raise AppError(404, "RESOURCE_NOT_FOUND", "Learning asset is not visible")
    return asset


async def evidence_rows(session, scope, evidence):
    if not evidence or len(evidence) != len(set(evidence)):
        raise AppError(422, "LEARNING_EVIDENCE_INVALID", "Unique evidence is required")
    rows = list(
        await session.scalars(
            select(LearningOutbox).where(
                LearningOutbox.id.in_(evidence), LearningOutbox.scope_id == scope_id(scope)
            )
        )
    )
    if len(rows) != len(evidence):
        raise AppError(422, "LEARNING_EVIDENCE_INVALID", "Evidence is missing or outside scope")
    return rows


async def create_candidate(session, *, scope, spec, evidence, kind="SKILL", idempotency_key=None):
    if kind != "SKILL":
        raise AppError(
            422, "LEARNING_KIND_UNSUPPORTED", "Only skill candidates are currently supported"
        )
    spec = SkillSpec.model_validate(spec).model_dump()
    pol = await policy(session, scope, lock=True)
    if pol.mode == "off":
        raise AppError(409, "LEARNING_DISABLED", "Learning is disabled")
    rows = await evidence_rows(session, scope, evidence)
    if any(r.policy_version != pol.version for r in rows):
        raise AppError(
            409, "LEARNING_POLICY_CHANGED", "Evidence predates the current learning consent"
        )
    concept = digest([spec["task_family"], spec["title"].strip().casefold()])
    if concept in pol.blocked_concepts or any(
        "source:" + r.id in pol.blocked_concepts for r in rows
    ):
        raise AppError(409, "LEARNING_FORGOTTEN", "This concept has been disabled")
    identifier = digest([pol.id, concept])
    content = digest(spec)
    provenance = digest(sorted((r.id, r.digest) for r in rows))
    asset = await session.get(AssetRow, identifier)
    if asset:
        latest = await session.get(AssetRevisionRow, (identifier, asset.latest_revision))
        if latest.content_hash == content and latest.evidence_digest == provenance:
            return latest
        asset.latest_revision += 1
        asset.version += 1
    else:
        asset = AssetRow(
            id=identifier,
            scope_id=pol.id,
            kind=kind,
            task_family=spec["task_family"],
            concept_key=concept,
            version=1,
            latest_revision=1,
        )
        session.add(asset)
        await session.flush()
    revision = AssetRevisionRow(
        asset_id=identifier,
        revision=asset.latest_revision,
        spec=spec,
        content_hash=content,
        evidence_digest=provenance,
        evidence_ids=sorted(evidence),
        status="DRAFT",
    )
    session.add(revision)
    for row in rows:
        session.add(
            EvidenceLinkRow(
                event_id=row.id, asset_id=identifier, revision=revision.revision, relation="support"
            )
        )
    await session.flush()
    return revision
