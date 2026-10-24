from datetime import UTC, datetime

from fastapi import Request, Response

from app.api.dependencies import Id, Key, User, authorize_store, require_role, visible_mission
from app.api.routing import B0Router, errors
from app.core.errors import AppError
from app.execution import assisted
from app.execution.models import ActionRow
from app.execution.repository import decide
from app.execution.schemas import (
    Action,
    ArrivalRecord,
    DecisionApproved,
    DecisionRejected,
    PlanDecision,
    SupplierReplyText,
)
from app.missions.models import PlanRow
from app.operations.models import Store

router = B0Router(tags=["Execution"], responses=errors)


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


async def visible_action(session, principal, action_id):
    row = await session.get(ActionRow, action_id)
    if row is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Action does not exist")
    authorize_store(principal, row.store_id)
    return row


@router.get("/api/v1/actions/{action_id}", response_model=Action, operation_id="get_action")
async def action(request: Request, principal: User, action_id: Id):
    async with request.app.state.db.session() as session:
        return Action.model_validate(await visible_action(session, principal, action_id))


@router.post(
    "/api/v1/actions/{action_id}/supplier-reply",
    response_model=Action,
    operation_id="record_supplier_reply",
)
async def supplier_reply(
    request: Request, principal: User, action_id: Id, body: SupplierReplyText, key: Key
):
    """The reply the owner pasted becomes the receipt, or leaves the order waiting."""
    require_role(principal, "approver")
    state = request.app.state
    async with state.db.session() as session:
        row = await visible_action(session, principal, action_id)
        if row.order_message is None:
            raise AppError(409, "ACTION_NOT_WAITING", "This order was not sent by its owner")
        order = row.order_message
        clock = (await session.get(Store, row.store_id)).simulation_time or datetime.now(UTC)
    # The reader may be a model: it runs between transactions, holding no lock.
    reading, read_by = await assisted.read_reply(
        body.text,
        order,
        clock.astimezone(assisted.BUSINESS_ZONE).date(),
        model=assisted.reader(state.settings),
    )
    async with state.db.session() as session, session.begin():
        return Action.model_validate(
            await assisted.record_reply(
                session, action_id, body.text, reading, read_by, principal.principal_id, key
            )
        )


@router.post(
    "/api/v1/actions/{action_id}/withdrawal",
    response_model=Action,
    operation_id="withdraw_assisted_order",
)
async def withdrawal(request: Request, principal: User, action_id: Id, key: Key):
    require_role(principal, "approver")
    async with request.app.state.db.session() as session, session.begin():
        await visible_action(session, principal, action_id)
        return Action.model_validate(
            await assisted.withdraw(session, action_id, principal.principal_id, key)
        )


@router.post(
    "/api/v1/actions/{action_id}/partial-acceptance",
    response_model=Action,
    operation_id="accept_partial_supply",
)
async def partial_acceptance(request: Request, principal: User, action_id: Id, key: Key):
    """The owner takes the smaller quantity the supplier confirmed; the rest is released."""
    require_role(principal, "approver")
    async with request.app.state.db.session() as session, session.begin():
        await visible_action(session, principal, action_id)
        return Action.model_validate(
            await assisted.accept_partial(session, action_id, principal.principal_id, key)
        )


@router.post(
    "/api/v1/actions/{action_id}/arrival",
    response_model=Action,
    operation_id="record_goods_arrival",
)
async def arrival(request: Request, principal: User, action_id: Id, body: ArrivalRecord, key: Key):
    """Goods of an order sent by hand reach stock when the owner records them."""
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        await visible_action(session, principal, action_id)
        return Action.model_validate(
            await assisted.record_arrival(
                session, action_id, body.quantity, principal.principal_id, key
            )
        )
