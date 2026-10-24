from collections import Counter

from fastapi import Request
from sqlalchemy import select

from app.api.dependencies import Id, Key, User, authorize_store, require_role
from app.api.routing import B0Router, errors
from app.core.errors import AppError
from app.learning import lifecycle
from app.learning.models import AssetRevisionRow, AssetRow, EpisodeRow, LearningOutbox
from app.learning.repository import get_asset, policy
from app.learning.schemas import (
    ApplicationFeedback,
    EvaluationRequest,
    ForgetRequest,
    LearningScope,
    LearningView,
    PolicyChange,
    Transition,
)
from app.operations.models import Store

router = B0Router(tags=["Learning"], responses=errors)


@router.post(
    "/api/v1/stores/{store_id}/learning/applications/{application_id}/feedback",
    response_model=dict,
    operation_id="review_learning_application",
)
async def application_feedback(
    request: Request,
    principal: User,
    store_id: Id,
    application_id: Id,
    body: ApplicationFeedback,
    key: Key,
):
    from app.agent_bridge.repository import receipt, replay
    from app.learning.monitoring import feedback

    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        pol = await policy(session, scope, lock=True)
        owner = "learning-feedback:" + pol.id + ":" + application_id
        old = await replay(session, owner, key, body.model_dump())
        if old is not None:
            return old
        result = await feedback(session, scope=scope, application_id=application_id, body=body)
        receipt(session, owner, key, body.model_dump(), result)
        return result


@router.get(
    "/api/v1/stores/{store_id}/learning/applications",
    response_model=dict,
    operation_id="list_learning_applications",
)
async def applications(request: Request, principal: User, store_id: Id):
    from app.learning.models import ApplicationRow

    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        pol = await policy(session, scope)
        rows = list(
            await session.scalars(
                select(ApplicationRow)
                .where(ApplicationRow.scope_id == pol.id)
                .order_by(ApplicationRow.created_at.desc())
                .limit(100)
            )
        )
        return {
            "items": [
                {
                    "id": r.id,
                    "asset_id": r.asset_id,
                    "revision": r.revision,
                    "run_id": r.run_id,
                    "stage": r.stage,
                    "outcome": r.outcome,
                }
                for r in rows
            ]
        }


async def scope_for(request, session, principal, store_id):
    if not request.app.state.settings.learning_enabled:
        raise AppError(503, "LEARNING_DISABLED", "Learning is not enabled on this server")
    authorize_store(principal, store_id)
    store = await session.get(Store, store_id)
    if not store:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Store is not visible")
    # Existing stores all have a simulator scenario. Never accept source domain from an LLM/client.
    return LearningScope(
        principal_id=principal.principal_id, store_id=store.id, source_domain="simulation"
    )


@router.get(
    "/api/v1/stores/{store_id}/learning", response_model=LearningView, operation_id="get_learning"
)
async def overview(request: Request, principal: User, store_id: Id):
    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        pol = await policy(session, scope)
        episodes = list(
            await session.scalars(select(EpisodeRow).where(EpisodeRow.scope_id == pol.id))
        )
        assets = list(
            await session.scalars(
                select(AssetRow).where(AssetRow.scope_id == pol.id).order_by(AssetRow.id).limit(100)
            )
        )
        current_ids = set(
            await session.scalars(
                select(LearningOutbox.id).where(
                    LearningOutbox.scope_id == pol.id, LearningOutbox.policy_version == pol.version
                )
            )
        )
        counts = Counter(
            e.task_family for e in episodes if e.eligible and set(e.evidence_ids) & current_ids
        )
        return LearningView(
            policy=lifecycle.policy_dto(pol),
            enabled=True,
            progress={
                "eligible_episodes": sum(counts.values()),
                "first_checkpoint": 10,
                "categories": dict(counts),
                "source_domain": scope.source_domain,
                "quality_calibrated": False,
            },
            assets=[await lifecycle.asset_dto(session, row) for row in assets],
        )


@router.patch(
    "/api/v1/stores/{store_id}/learning/policy",
    response_model=dict,
    operation_id="update_learning_policy",
)
async def update_policy(
    request: Request, principal: User, store_id: Id, body: PolicyChange, key: Key
):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        return await lifecycle.change_policy(session, scope=scope, body=body, key=key)


@router.get(
    "/api/v1/stores/{store_id}/learning/assets/{asset_id}",
    response_model=dict,
    operation_id="get_learning_asset",
)
async def detail(request: Request, principal: User, store_id: Id, asset_id: Id):
    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        return await lifecycle.asset_dto(session, await get_asset(session, scope, asset_id))


@router.post(
    "/api/v1/stores/{store_id}/learning/assets/{asset_id}/transitions",
    response_model=dict,
    operation_id="transition_learning_asset",
)
async def transition(
    request: Request, principal: User, store_id: Id, asset_id: Id, body: Transition, key: Key
):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        return await lifecycle.transition(
            session,
            scope=scope,
            asset_id=asset_id,
            body=body,
            key=key,
            settings=request.app.state.settings,
            principal=principal,
        )


@router.post(
    "/api/v1/stores/{store_id}/learning/forget",
    response_model=dict,
    operation_id="forget_learning_asset",
)
async def forget(request: Request, principal: User, store_id: Id, body: ForgetRequest, key: Key):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        return await lifecycle.forget(session, scope=scope, body=body, key=key)


@router.post(
    "/api/v1/stores/{store_id}/learning/assets/{asset_id}/evaluations",
    response_model=dict,
    operation_id="evaluate_learning_asset",
)
async def evaluate(
    request: Request, principal: User, store_id: Id, asset_id: Id, body: EvaluationRequest, key: Key
):
    from app.agent_bridge.repository import receipt, replay
    from app.learning.evaluation import static_evaluate

    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        scope = await scope_for(request, session, principal, store_id)
        await policy(session, scope, lock=True)
        asset = await get_asset(session, scope, asset_id)
        owner = "learning-evaluation:" + asset.id
        old = await replay(session, owner, key, body.model_dump())
        if old is not None:
            return old
        if asset.version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Learning asset changed")
        rev = await session.get(AssetRevisionRow, (asset.id, body.revision))
        if not rev or rev.status == "REVOKED":
            raise AppError(409, "LEARNING_STATE_CONFLICT", "Revision cannot be evaluated")
        result = await static_evaluate(
            session,
            scope=scope,
            asset=asset,
            revision=rev,
            settings=request.app.state.settings,
            principal=principal,
        )
        asset.version += 1
        receipt(session, owner, key, body.model_dump(), result)
        return result
