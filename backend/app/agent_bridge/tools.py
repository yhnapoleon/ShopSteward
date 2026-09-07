import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from app.agent_bridge import knowledge
from app.agent_bridge.jobs import assert_lease, current_principal
from app.agent_bridge.models import AgentRun, Conversation, Message, ToolInvocation
from app.agent_bridge.presentation import explicit_memory_intent, memory_write_denied, money_facts
from app.agent_bridge.router import META, enabled
from app.agent_bridge.schemas import KnowledgeChange, ToolCall, ToolResult
from app.api.routing import B0Router, errors
from app.core.errors import AppError
from app.core.hashing import digest
from app.execution.models import ActionRow
from app.execution.schemas import Action
from app.missions import repository as missions
from app.missions.models import PlanRow
from app.missions.schemas import CheckRequest
from app.planning.revisions import evaluate
from app.reporting import read_repository as reads
from app.reporting import repository as reporting
from app.scheduling.models import Job
from app.scheduling.repository import owned

router = B0Router(tags=["Agent tools"], responses=errors)
agent_bearer = HTTPBearer(scheme_name="AgentRunBearer", auto_error=False)


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanArgs(Empty):
    plan_id: str | None = Field(default=None, max_length=128)


class ActionArgs(Empty):
    action_id: str = Field(min_length=1, max_length=128)


class CheckArgs(Empty):
    reason: str = Field(default="", max_length=1000)


class LimitArgs(Empty):
    limit: int = Field(default=10, ge=1, le=30)


class SalesArgs(Empty):
    days: int = Field(default=7, ge=1, le=90)


class EvaluationArgs(Empty):
    plan_id: str = Field(min_length=1, max_length=128)
    max_purchase_qty: int | None = Field(default=None, strict=True, ge=0, le=1000000)


class RevisionArgs(EvaluationArgs):
    expected_mission_version: int = Field(ge=1)
    source_message_id: str | None = Field(default=None, max_length=128)


DEFINITIONS = {
    "get_mission": (Empty, "读取当前任务、正式现金底线和任务状态。"),
    "get_plan": (
        PlanArgs,
        "读取当前或指定真实方案。金额单位为分，审批必须由用户现有审批接口执行。",
    ),
    "get_dashboard": (Empty, "读取真实库存、现金、在途和警报。"),
    "get_action": (ActionArgs, "读取采购行动及受理/到货状态，受理不等于到货。"),
    "read_timeline": (LimitArgs, "读取当前任务最近业务事件和可引用的记录。"),
    "read_sales_summary": (SalesArgs, "读取当前店铺最近指定天数销售汇总。"),
    "request_check": (CheckArgs, "请求后台重新计算；返回任务受理，不代表已有新方案。"),
    "evaluate_plan": (
        EvaluationArgs,
        "只读试算：假设本次采购数量上限，不改变任务、审批或库存。null表示无额外数量上限。",
    ),
    "revise_plan": (
        RevisionArgs,
        "用户明确要求修改本次方案时，设置临时采购上限并生成新的待确认方案；保留旧版本，不执行采购。不用于假设问题。",
    ),
    "memory_edit": (
        KnowledgeChange,
        "保存/纠正/删除用户明确要求记住的偏好。USER通用偏好；SKILL任务流程及纠正，task_type=replenishment；NOTES稳定背景。来源由后端绑定当前用户消息。动态库存/现金不写记忆。读取系统上下文中的版本和entry_id；成功才可声称记住。",
    ),
    "read_experiences": (LimitArgs, "读取当前用户同店铺已完成的Agent任务摘要和业务引用。"),
}


def catalog(principal):
    names = set(DEFINITIONS)
    if not {"operator", "admin"} & set(principal.roles):
        names -= {"request_check", "revise_plan"}
    return {name: DEFINITIONS[name] for name in sorted(names)}


def tool_schemas(principal):
    result = []
    for name, (schema, description) in catalog(principal).items():
        parameters = schema.model_json_schema()
        # Provenance is the current authenticated user message, injected by backend.
        # Models should choose the intended edit, not manufacture message IDs.
        parameters.get("properties", {}).pop("source_message_id", None)
        result.append(
            {
                "type": "function",
                "function": {"name": name, "description": description, "parameters": parameters},
            }
        )
    return result


def encoded(value):
    return (
        value.model_dump(mode="json", exclude_unset=True) if isinstance(value, BaseModel) else value
    )


async def user_source(session, run, identifier):
    source = (
        await session.get(Message, identifier)
        if identifier
        else await session.scalar(
            select(Message)
            .where(Message.run_id == run.id, Message.role == "user")
            .order_by(Message.seq.desc())
            .limit(1)
        )
    )
    if (
        source is None
        or source.role != "user"
        or source.run_id != run.id
        or source.conversation_id != run.conversation_id
        or run.trigger != "USER"
    ):
        raise AppError(422, "USER_SOURCE_REQUIRED", "Change requires the current user's message")
    return source


async def execute_tool(
    session, settings, principal, conversation, run, mission, store, name, args, invocation_id
):
    references = []
    if name == "get_mission":
        value = encoded(await missions.read_mission(session, mission.id))
        value["task_constraints"] = mission.task_constraints
        references = [
            {"type": "mission", "id": mission.id, "version": str(mission.mission_version)}
        ]
    elif name == "get_plan":
        row = (
            await session.get(PlanRow, args.plan_id or mission.current_plan_id)
            if (args.plan_id or mission.current_plan_id)
            else None
        )
        if row is None:
            value = {"plan": None, "message": "No current plan; request_check if authorized."}
        else:
            if row.mission_id != mission.id:
                raise AppError(404, "RESOURCE_NOT_FOUND", "Plan is outside this mission")
            value = encoded(
                missions.plan_dto(row, await session.scalar(select(func.clock_timestamp())))
            )
            references = [{"type": "plan", "id": row.id, "version": str(row.plan_version)}]
    elif name == "get_dashboard":
        value = encoded(await reporting.dashboard(session, store.id, settings))
        references = [{"type": "store", "id": store.id, "version": str(store.state_version)}]
    elif name == "get_action":
        action = await session.get(ActionRow, args.action_id)
        if action is None or action.mission_id != mission.id:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Action is outside this mission")
        value = encoded(Action.model_validate(action))
        references = [{"type": "action", "id": action.id}]
    elif name == "read_timeline":
        value = encoded(await reporting.list_timeline(session, mission.id, None, args.limit))
        references = [{"type": "mission", "id": mission.id}]
    elif name == "read_sales_summary":
        context = await reads.read_context(session, store.id, settings, sku_id=mission.sku_id)
        end = store.simulation_time or datetime.now(UTC)
        value = encoded(
            await reads.summarize_sales(
                session,
                context,
                sku_id=mission.sku_id,
                start=end - timedelta(days=args.days),
                end=end,
            )
        )
        references = [{"type": "store", "id": store.id}]
    elif name == "request_check":
        value = encoded(
            await missions.request_check(
                session,
                mission.id,
                CheckRequest(reason=args.reason),
                principal.principal_id,
                digest([run.id, invocation_id]),
            )
        )
    elif name in {"evaluate_plan", "revise_plan"}:
        if name == "revise_plan":
            source = await user_source(session, run, args.source_message_id)
            if re.search(r"如果|假设|what if|suppose", source.content, re.I):
                raise AppError(
                    422, "HYPOTHETICAL_ONLY", "Hypothetical requests must use evaluate_plan"
                )
            if not re.search(
                r"修改|改成|上限|最多|限制|调整|revise|change|limit|maximum", source.content, re.I
            ):
                raise AppError(
                    422, "EXPLICIT_REVISION_REQUIRED", "User must request a proposal change"
                )
        value = await evaluate(
            session, settings, mission, store, args, revise=name == "revise_plan"
        )
        if name == "revise_plan":
            references = [
                {"type": "plan", "id": value["id"], "version": str(value["plan_version"])}
            ]
    elif name == "memory_edit":
        source = await user_source(session, run, args.source_message_id)
        origin = await session.scalar(
            select(Message)
            .where(Message.run_id == run.id, Message.role == "user")
            .order_by(Message.seq)
            .limit(1)
        )
        continuing_clarification = (
            run.resume_value is not None
            and origin is not None
            and explicit_memory_intent(origin.content)
            and not memory_write_denied(source.content)
        )
        if not explicit_memory_intent(source.content) and not continuing_clarification:
            raise AppError(
                422,
                "EXPLICIT_MEMORY_INTENT_REQUIRED",
                "This message does not request a lasting preference change",
            )
        value = await knowledge.change(
            session,
            principal.principal_id,
            store.id,
            args,
            invocation_id,
            source={"type": "user_message", "message_id": source.id, "run_id": run.id},
            allowed_tools=catalog(principal),
        )
    elif name == "read_experiences":
        rows = (
            await session.scalars(
                select(AgentRun)
                .join(Conversation, AgentRun.conversation_id == Conversation.id)
                .where(
                    Conversation.principal_id == principal.principal_id,
                    Conversation.store_id == store.id,
                    AgentRun.status == "SUCCEEDED",
                )
                .order_by(AgentRun.created_at.desc())
                .limit(args.limit)
            )
        ).all()
        value = {
            "items": [
                {
                    "run_id": r.id,
                    "content": (r.output or {}).get("content", "")[:1500],
                    "references": (r.output or {}).get("references", []),
                }
                for r in rows
            ]
        }
    else:
        raise AppError(403, "TOOL_NOT_ALLOWED", "Tool is not registered")
    if name not in {"memory_edit", "read_experiences"}:
        value["money_display"] = money_facts(value)
    return {"ok": True, "data": value, "references": references}


@router.post(
    "/internal/v1/agent-tools/{tool_name}",
    response_model=ToolResult,
    operation_id="call_agent_tool",
    openapi_extra=META,
)
async def call(
    request: Request,
    tool_name: str,
    body: ToolCall,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(agent_bearer)],
):
    enabled(request)
    settings = request.app.state.settings
    token = credentials.credentials if credentials else ""
    async with request.app.state.db.session() as session, session.begin():
        run = await session.get(AgentRun, body.run_id)
        if (
            run is None
            or run.token_hash is None
            or not secrets.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), run.token_hash
            )
        ):
            raise AppError(401, "INVALID_AGENT_TOKEN", "Current run credential required")
        conversation = await session.get(Conversation, run.conversation_id)
        principal = current_principal(settings, conversation)
        if tool_name not in catalog(principal):
            raise AppError(403, "TOOL_NOT_ALLOWED", "Tool is not authorized for this user")
        try:
            args = DEFINITIONS[tool_name][0].model_validate(body.arguments)
        except ValidationError:
            raise AppError(
                422, "INVALID_TOOL_ARGUMENTS", "Arguments do not match this tool schema"
            ) from None
        # Global order: store -> mission -> run -> job. Never hold these locks over HTTP.
        store, mission = await missions.lock_mission(session, conversation.mission_id)
        await session.refresh(run, with_for_update=True)
        job = await session.scalar(select(Job).where(*owned(run.job_id, run.token_job_lease)))
        if (
            job is None
            or run.status != "RUNNING"
            or run.id != conversation.active_run_id
            or not secrets.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), run.token_hash or ""
            )
        ):
            raise AppError(401, "INVALID_AGENT_TOKEN", "Run credential expired or was revoked")
        signature = digest([tool_name, body.arguments])
        old = await session.get(ToolInvocation, (run.id, body.invocation_id))
        if old:
            if old.args_hash != signature:
                raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Tool invocation arguments changed")
            await assert_lease(session, job)
            return old.result
        try:
            async with session.begin_nested():
                result = await execute_tool(
                    session,
                    settings,
                    principal,
                    conversation,
                    run,
                    mission,
                    store,
                    tool_name,
                    args,
                    body.invocation_id,
                )
        except AppError as exc:
            result = {
                "ok": False,
                "data": {},
                "error": {"code": exc.code, "message": exc.message},
                "references": [],
            }
        session.add(
            ToolInvocation(
                run_id=run.id,
                invocation_id=body.invocation_id,
                tool=tool_name,
                args_hash=signature,
                result=result,
            )
        )
        await session.flush()
        await assert_lease(session, job)
        return result
