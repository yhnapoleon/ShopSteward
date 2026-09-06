from fastapi import APIRouter, Request, Response

from app.api.dependencies import User, authorize_store
from app.core.errors import AppError
from app.execution.models import ActionRow
from app.execution.repository import decide
from app.execution.schemas import Action, DecisionApproved, DecisionRejected, PlanDecision
from app.missions.models import PlanRow
from app.missions.router import Id, require_role, visible_mission
from app.operations.router import Key, errors

router = APIRouter(tags=["Execution"], responses=errors)


@router.post(
    "/api/v1/plans/{plan_id}/decision",
    response_model=DecisionApproved | DecisionRejected,
    operation_id="decide_plan",
    responses={200: {"model": DecisionRejected}, 202: {"model": DecisionApproved}},
)
async def decision(
    request: Request, response: Response, principal: User, plan_id: Id, body: PlanDecision, key: Key
):
    require_role(principal, "approver")
    async with request.app.state.db.session() as session, session.begin():
        row = await session.get(PlanRow, plan_id)
        if row is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Plan does not exist")
        await visible_mission(session, principal, row.mission_id)
        result = await decide(
            session, plan_id, body, principal.principal_id, key, request.app.state.settings
        )
        response.status_code = 202 if result.decision == "approve" else 200
        return result


@router.get("/api/v1/actions/{action_id}", response_model=Action, operation_id="get_action")
async def action(request: Request, principal: User, action_id: Id):
    async with request.app.state.db.session() as session:
        row = await session.get(ActionRow, action_id)
        if row is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Action does not exist")
        authorize_store(principal, row.store_id)
        return Action.model_validate(row)


for route in router.routes:
    route.openapi_extra = {"x-phase": "B0", "x-implementation-status": "implemented"}
