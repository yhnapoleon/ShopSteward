from fastapi import Request
from pydantic import BaseModel

from app.agent_bridge.context_repository import inspect_context
from app.api.dependencies import Id, User
from app.api.routing import B0Router, errors

router = B0Router(tags=["Agent"], responses=errors)


class ContextInspection(BaseModel):
    run_id: str
    config: dict | None
    frames: list[dict]
    calls: list[dict]
    manifests: list[dict]


@router.get(
    "/api/v1/agent-runs/{run_id}/context",
    response_model=ContextInspection,
    operation_id="inspect_agent_context",
    openapi_extra={"x-phase": "B2-A", "x-implementation-status": "implemented"},
)
async def inspect(request: Request, principal: User, run_id: Id):
    async with request.app.state.db.session() as session:
        return await inspect_context(session, principal, run_id)
