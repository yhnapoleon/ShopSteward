from types import SimpleNamespace

from fastapi import Request

from app.api.dependencies import Id, Key, User, require_role, visible_mission
from app.api.routing import B0Router, errors
from app.core.errors import AppError
from app.missions.models import PlanRow
from app.missions.repository import command, lock_mission
from app.planning.revisions import evaluate
from app.planning.schemas import Plan, PlanRevisionRequest

router = B0Router(tags=["Planning"], responses=errors)


@router.post(
    "/api/v1/plans/{plan_id}/revision",
    response_model=Plan,
    operation_id="revise_plan",
)
async def revise(
    request: Request, principal: User, plan_id: Id, body: PlanRevisionRequest, key: Key
):
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        original = await session.get(PlanRow, plan_id)
        if original is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Plan does not exist")
        await visible_mission(session, principal, original.mission_id)
        store, mission = await lock_mission(session, original.mission_id)
        receipt, replay = await command(
            session,
            principal.principal_id,
            "revise_plan",
            key,
            {"plan_id": plan_id, **body.model_dump()},
        )
        if replay:
            return Plan.model_validate(receipt.response)
        args = SimpleNamespace(plan_id=plan_id, **body.model_dump())
        result = await evaluate(
            session,
            request.app.state.settings,
            mission,
            store,
            args,
            revise=True,
            actor=principal.principal_id,
        )
        receipt.response = result
        return Plan.model_validate(result)
