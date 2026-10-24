import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from app.agent_bridge import knowledge
from app.agent_bridge.document_evidence import DEFINITIONS as DOCUMENT_TOOLS
from app.agent_bridge.document_evidence import call_document_tool
from app.agent_bridge.jobs import assert_lease, current_principal
from app.agent_bridge.models import AgentRun, Conversation, Message, ToolInvocation
from app.agent_bridge.presentation import (
    deadline_verdicts,
    explicit_memory_intent,
    local_times,
    memory_write_denied,
    money_facts,
    supplier_names_in,
)
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
from app.operations.models import OfferRow, ProductRow
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


class CaseArgs(Empty):
    case_id: str = Field(min_length=1, max_length=128)


class CaseAnalysisArgs(CaseArgs):
    expected_revision: int = Field(strict=True, ge=1)


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
    "get_recovery_cases": (Empty, "读取当前任务关联的供应异常恢复事项，不创建采购或修改约束。"),
    "get_recovery_case": (CaseArgs, "读取已返回case_id的恢复事项、预算、候选、证据和状态。"),
    "analyze_recovery_case": (
        CaseAnalysisArgs,
        "使用现有已确认输入进行确定性恢复分析，生成候选比较；不采纳、不批准、不发送采购。",
    ),
    "get_mission": (Empty, "读取当前任务、正式现金底线和任务状态。"),
    "get_plan": (
        PlanArgs,
        "读取当前或指定真实方案。金额单位为分，审批必须由用户现有审批接口执行。",
    ),
    "get_dashboard": (Empty, "读取真实库存、现金、在途和警报。"),
    "get_forecast": (
        Empty,
        "读取当前任务门店商品的已保存 v6 七日预测、日期、版本、适用范围。"
        "historical_demo对用户称为模型推演，仅供参考；不可用时先补充历史并刷新。",
    ),
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


def catalog(principal, settings=None):
    definitions = dict(DEFINITIONS)
    if settings is not None and settings.knowledge_service_enabled:
        definitions.update(DOCUMENT_TOOLS)
    names = set(definitions)
    if not {"operator", "admin"} & set(principal.roles):
        names -= {"request_check", "revise_plan", "analyze_recovery_case"}
    return {name: definitions[name] for name in sorted(names)}


def tool_schemas(principal, settings=None):
    result = []
    for name, (schema, description) in catalog(principal, settings).items():
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
    if (
        name in {"revise_plan", "memory_edit", "request_check", "analyze_recovery_case"}
        and run.trigger == "USER"
    ):
        from shopsteward_agent.context.intent import classify_intent

        from app.agent_bridge.context_sources import load_history

        history, _ = await load_history(session, conversation, run)
        if (
            name
            in classify_intent([message for message in history if message["role"] == "user"])[
                "denied_tools"
            ]
        ):
            raise AppError(
                422,
                "EXPLICIT_MEMORY_INTENT_REQUIRED"
                if name == "memory_edit"
                else "EXPLICIT_READ_ONLY",
                "The admitted user request forbids saving or changing state; use read-only tools",
            )
    if name in {"get_recovery_cases", "get_recovery_case", "analyze_recovery_case"}:
        from app.operations_cases import repository as cases
        from app.operations_cases.models import CaseRow
        from app.operations_cases.schemas import CaseAnalyze

        if name == "get_recovery_cases":
            rows = (
                await session.scalars(
                    select(CaseRow)
                    .where(
                        CaseRow.mission_id == mission.id, CaseRow.owner_id == principal.principal_id
                    )
                    .order_by(CaseRow.created_at.desc())
                    .limit(10)
                )
            ).all()
            value = {
                "items": [case_summary(encoded(await cases.detail(session, row))) for row in rows],
                "note": "Read one case with get_recovery_case for its options, supplier offers "
                "and analysis.",
            }
            references = [
                {"type": "case", "id": row.id, "version": str(row.current_revision)} for row in rows
            ]
        else:
            row = await cases.visible(session, principal, args.case_id)
            if row.mission_id != mission.id:
                raise AppError(404, "RESOURCE_NOT_FOUND", "Case is outside this Mission")
            if name == "analyze_recovery_case":
                # Gateway already holds store/Mission locks. Lock Case last.
                await session.refresh(row, with_for_update=True)
                value = case_for_agent(
                    encoded(
                        await cases.analyze(
                            session,
                            row,
                            CaseAnalyze(expected_revision=args.expected_revision),
                            principal,
                            digest([run.id, invocation_id]),
                            settings,
                        )
                    )
                )
            else:
                value = case_for_agent(encoded(await cases.detail(session, row)))
            references = [{"type": "case", "id": row.id, "version": str(row.current_revision)}]
    elif name == "get_mission":
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
    elif name == "get_forecast":
        from app.forecast_v6.repository import read_current

        value = await read_current(session, store.id, mission.sku_id, settings)
        history = value.get("history", [])
        model = value.get("model") or {}
        # The product keeps complete input for inspection. The Agent only needs the
        # seven predictions, or why there are none, and input coverage; not 300
        # series or 374 rows, which alone would overflow its context.
        value = {k: v for k, v in value.items() if k not in {"history", "model"}}
        value["input_coverage"] = {
            "days": len(history),
            "start": history[0]["date"] if history else None,
            "end": history[-1]["date"] if history else None,
        }
        value["model"] = {k: v for k, v in model.items() if k != "supported_series"}
        if value["status"] != "READY" or not value.get("forecast"):
            return {
                "ok": False,
                "data": value,
                "references": [],
                "error": {
                    "code": "FORECAST_UNAVAILABLE",
                    "message": value.get("reason") or "Forecast unavailable",
                },
            }
        forecast = value["forecast"]
        references = [
            {
                "type": "forecast",
                "id": forecast["forecast_id"],
                "version": forecast["model_version"],
                "store_id": store.id,
                "sku_id": mission.sku_id,
                "mode": value["mode"],
            }
        ]
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
            from app.work_items.authorization import require_explicit_revision

            require_explicit_revision(source.content)
        value = await evaluate(
            session, settings, mission, store, args, revise=name == "revise_plan"
        )
        if name == "revise_plan":
            value["base_plan_id"] = args.plan_id
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
        if await saved_in_run(session, run, args):
            # One request saves a preference once; a repeat changes nothing and must not
            # count as a second memory.
            raise AppError(
                409,
                "MEMORY_ALREADY_SAVED",
                "这条偏好本轮已经保存成功，已在knowledge里；不要再次保存，直接告诉用户已保存。",
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
        value["product_names"] = await product_names(session, store.id, value)
        suppliers = await supplier_names(session, store.id, value)
        value = deadline_verdicts(supplier_names_in(value, suppliers), datetime.now(UTC))
        if suppliers:
            value["supplier_names"] = suppliers
    return {"ok": True, "data": local_times(value), "references": references}


# What an answer about an emergency case needs. The case page keeps the full record (each
# expert call, every citation, daily rows); in the Agent's context, a case read whole is
# about 36 KB, so two reads filled its 64 KB budget before it could answer.
CASE_FIELDS = (
    "id",
    "sku_id",
    "status",
    "current_revision",
    "objective",
    "budget_minor",
    "max_purchase_qty",
    "daily_demand",
    "supplier_ids",
    "excluded_supplier_ids",
    "plan_id",
    "plan_status",
    "action_id",
    "execution_status",
    "missing_inputs",
    "stale",
    "purchases",
    "routine_paused",
    "recheck_reason",
    "outcome",
    "followup_enabled",
    "created_at",
    "updated_at",
)
SUMMARY_FIELDS = (
    "id",
    "sku_id",
    "status",
    "objective",
    "plan_status",
    "execution_status",
    "purchases",
    "recheck_reason",
    "outcome",
    "created_at",
    "updated_at",
)


def first_short_day(candidate):
    """When this option first leaves demand unserved, from its daily rows."""
    return next(
        (day["settlement_at"] for day in candidate.get("daily") or [] if day.get("lost_qty")),
        None,
    )


def case_for_agent(detail):
    value = {key: detail[key] for key in CASE_FIELDS if key in detail}
    value["evidence"] = [
        {key: item.get(key) for key in ("kind", "id", "status", "summary")}
        for item in detail.get("evidence") or []
    ]
    proposal = detail.get("proposal")
    if proposal:
        value["proposal"] = {
            **{
                key: proposal.get(key)
                for key in (
                    "id",
                    "revision",
                    "recommended_candidate_id",
                    "created_at",
                    "expires_at",
                )
            },
            "candidates": [
                {
                    **{key: item for key, item in candidate.items() if key != "daily"},
                    "first_short_at": first_short_day(candidate),
                }
                for candidate in proposal.get("candidates") or []
            ],
        }
    sourcing = detail.get("sourcing")
    if sourcing:
        value["sourcing"] = {
            "status": sourcing.get("status"),
            "suppliers": [
                {
                    "supplier_id": review.get("supplier_id"),
                    "name": review.get("name"),
                    "read": review.get("status"),
                    **{
                        key: (review.get("card") or {}).get(key)
                        for key in ("status", "offer", "history", "reason")
                    },
                }
                for review in sourcing.get("reviews") or []
            ],
            "left_out": sourcing.get("left_out"),
            "unreviewed": sourcing.get("unreviewed"),
        }
    analysis = detail.get("expert_analysis")
    if analysis:
        merged = analysis.get("merged") or {}
        value["expert_analysis"] = {
            "status": analysis.get("status"),
            "revision": analysis.get("revision"),
            # The reading of the options; the restated figures are in proposal above.
            "findings": [
                claim["statement"][:500]
                for claim in merged.get("claims") or []
                if claim.get("kind") in {"interpretation", "assumption"} and claim.get("statement")
            ][:8],
            "conflicts": (merged.get("conflicts") or [])[:3],
            "missing": [item.get("item") for item in merged.get("missing") or []][:3],
        }
    return value


def case_summary(detail):
    value = {key: detail[key] for key in SUMMARY_FIELDS if key in detail}
    proposal = detail.get("proposal") or {}
    value["recommended_candidate_id"] = proposal.get("recommended_candidate_id")
    return value


async def saved_in_run(session, run, args):
    """Whether this run already saved this preference: an add whose content an earlier
    successful memory_edit of the run left in the same scope."""
    if args.operation != "add":
        return False
    content = args.content.strip()
    for call in await session.scalars(
        select(ToolInvocation).where(
            ToolInvocation.run_id == run.id, ToolInvocation.tool == "memory_edit"
        )
    ):
        data = call.result.get("data") or {}
        if (
            call.result.get("ok")
            and (data.get("kind"), data.get("task_type")) == (args.kind, args.task_type)
            and any(entry.get("content") == content for entry in data.get("entries") or [])
        ):
            return True
    return False


def sku_ids(value):
    if isinstance(value, dict):
        found = {value["sku_id"]} if isinstance(value.get("sku_id"), str) else set()
        return found.union(*(sku_ids(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(sku_ids(item) for item in value))
    return set()


async def product_names(session, store_id, value):
    """The name for every SKU a tool result mentions, so the model names products as the UI does."""
    skus = sku_ids(value)
    if not skus:
        return {}
    rows = await session.execute(
        select(ProductRow.sku_id, ProductRow.document).where(
            ProductRow.store_id == store_id, ProductRow.sku_id.in_(sorted(skus))
        )
    )
    return {sku: document["name"] for sku, document in rows if (document or {}).get("name")}


def supplier_ids(value):
    if isinstance(value, dict):
        found = set()
        for key, item in value.items():
            if key in {"supplier_id", "supplier_override"} and isinstance(item, str):
                found.add(item)
            elif key in {"supplier_ids", "excluded_supplier_ids"} and isinstance(item, list):
                found |= {entry for entry in item if isinstance(entry, str)}
            else:
                found |= supplier_ids(item)
        return found
    if isinstance(value, list):
        return set().union(*(supplier_ids(item) for item in value))
    return set()


async def supplier_names(session, store_id, value):
    """What the owner calls each supplier a tool result mentions: the name on its documents or
    its offer, so the model never writes "supplier B"."""
    ids = supplier_ids(value)
    if not ids:
        return {}
    from app.sourcing.models import SupplierDocumentRow

    names = {
        supplier: document["supplier_name"]
        for supplier, document in await session.execute(
            select(OfferRow.supplier_id, OfferRow.document).where(
                OfferRow.store_id == store_id, OfferRow.supplier_id.in_(sorted(ids))
            )
        )
        if (document or {}).get("supplier_name")
    }
    for supplier, name in await session.execute(
        select(SupplierDocumentRow.supplier_id, SupplierDocumentRow.supplier_name)
        .where(
            SupplierDocumentRow.store_id == store_id,
            SupplierDocumentRow.supplier_id.in_(sorted(ids)),
        )
        .distinct()
    ):
        names.setdefault(supplier, name)
    return dict(sorted(names.items()))


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
    from app.agent_bridge import progress

    enabled(request)
    token = credentials.credentials if credentials else ""
    await progress.start_tool(request, tool_name, body, token)
    try:
        return await _call_core(request, tool_name, body, credentials)
    except Exception:
        try:
            await progress.interrupted_tool(request, body, token)
        except Exception:
            # Preserve the original failure; no false completion can be committed.
            import logging

            logging.getLogger(__name__).warning("Unable to persist interrupted tool progress")
        raise


async def _call_core(
    request: Request,
    tool_name: str,
    body: ToolCall,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(agent_bearer)],
):
    enabled(request)
    settings = request.app.state.settings
    token = credentials.credentials if credentials else ""
    if tool_name in DOCUMENT_TOOLS:
        return await call_document_tool(request, tool_name, body, token)
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
        from app.learning.run_binding import assert_current
        await assert_current(session,conversation,run.id,settings,principal)
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
        from app.agent_bridge.progress import complete_tool

        await complete_tool(session, run, body.invocation_id, result)
        return result
