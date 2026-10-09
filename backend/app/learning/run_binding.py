"""Persist first selection and fence in-flight model output against revocation."""

from app.agent_bridge.models import Receipt
from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.lifecycle import binding
from app.learning.models import AssetRevisionRow, AssetRow, EvaluationRow
from app.learning.quality import decide
from app.learning.repository import policy, scope_id
from app.learning.schemas import LearningScope


def selection_owner(scope):
    return "learning-run:" + scope_id(scope)


async def selection(session, scope, run_id):
    return await session.get(Receipt, (selection_owner(scope), run_id))


async def pin(session, scope, run_id, pol, assets):
    session.add(
        Receipt(
            owner=selection_owner(scope),
            key=run_id,
            args_hash=digest([run_id]),
            result={"policy_version": pol.version, "assets": assets},
        )
    )
    await session.flush()


async def validated(session, *, scope, frozen, settings, principal):
    pol = await policy(session, scope, lock=True)
    if not frozen.result["assets"]:
        return []
    if (
        not settings.learning_enabled
        or pol.mode == "off"
        or pol.version != frozen.result["policy_version"]
    ):
        raise AppError(409, "LEARNING_CONTEXT_CHANGED", "Learning consent changed during this run")
    result = []
    for item in frozen.result["assets"]:
        asset = await session.get(AssetRow, item["asset_id"])
        rev = await session.get(AssetRevisionRow, (asset.id, item["revision"])) if asset else None
        evaluation = await session.get(EvaluationRow, item["evaluation_id"])
        if (
            not asset
            or asset.scope_id != pol.id
            or not rev
            or rev.status not in {"ACTIVE", "SUPERSEDED"}
            or not evaluation
            or (evaluation.asset_id, evaluation.revision) != (asset.id, rev.revision)
        ):
            raise AppError(
                409, "LEARNING_CONTEXT_CHANGED", "A selected skill is no longer admitted"
            )
        try:
            expected = await binding(
                session,
                scope=scope,
                asset=asset,
                revision=rev,
                settings=settings,
                principal=principal,
            )
            passing = decide(evaluation.report, expected)["status"] == "pass"
        except AppError:
            passing = False
        if not passing:
            raise AppError(409, "LEARNING_CONTEXT_CHANGED", "Selected skill evidence changed")
        result.append({**item, "spec": rev.spec})
    return result


async def assert_current(session, conversation, run_id, settings, principal):
    scope = LearningScope(principal_id=conversation.principal_id, store_id=conversation.store_id)
    frozen = await selection(session, scope, run_id)
    if frozen:
        await validated(session, scope=scope, frozen=frozen, settings=settings, principal=principal)


async def reset_after_explicit_edit(session, principal_id, store_id, run_id):
    scope = LearningScope(principal_id=principal_id, store_id=store_id)
    pol = await policy(session, scope, lock=True)
    frozen = await selection(session, scope, run_id)
    if frozen:
        frozen.result = {
            "policy_version": pol.version,
            "assets": [],
            "reason": "explicit_memory_changed",
        }
