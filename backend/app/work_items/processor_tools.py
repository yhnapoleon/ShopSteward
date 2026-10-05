"""Owner-scoped business tools for the intake processor; never purchase authority."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.api.dependencies import require_role, visible_mission
from app.core.errors import AppError
from app.missions import repository as missions
from app.missions.models import MissionRow, PlanRow
from app.missions.schemas import CheckRequest, MissionControl, MissionCreate
from app.operations.models import Store
from app.planning.simulation_schemas import QuantitySimulationRequest


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextArgs(Empty):
    mission_cursor: str | None = None


class MissionArgs(Empty):
    mission_id: str = Field(min_length=1, max_length=128)


class SourceArgs(Empty):
    source_quote: str = Field(min_length=1, max_length=2000)


class PlanArgs(MissionArgs):
    plan_id: str = Field(min_length=1, max_length=128)
    max_purchase_qty: int | None = Field(default=None, strict=True, ge=0, le=1000000)


class RevisionArgs(PlanArgs, SourceArgs):
    expected_mission_version: int = Field(ge=1)


class ControlArgs(MissionArgs, SourceArgs):
    operation: Literal["pause", "resume"]
    expected_mission_version: int = Field(ge=1)


class CheckArgs(MissionArgs, SourceArgs):
    pass


class ForecastArgs(Empty):
    sku_id: str = Field(min_length=1, max_length=128)
    requested_start: AwareDatetime
    requested_end: AwareDatetime


class ComparisonArgs(ForecastArgs):
    expected_state_version: int = Field(ge=1)
    supplier_id: str = Field(min_length=1, max_length=128)
    cash_floor_minor: int = Field(strict=True, ge=0, le=10**12)
    candidate_quantities: list[int] = Field(min_length=2, max_length=20)
    remaining_demand: int | None = Field(default=None, strict=True, ge=0, le=1000000)
    horizon_days: int | None = Field(default=None, strict=True, ge=1, le=90)

    @model_validator(mode="after")
    def window(self):
        if self.requested_end <= self.requested_start:
            raise ValueError("Requested period must be ordered")
        return self

    def request(self):
        return QuantitySimulationRequest.model_validate(
            self.model_dump(
                exclude={"requested_start", "requested_end", "source_quote", "objective"}
            )
        )


class ProposalArgs(ComparisonArgs, SourceArgs):
    objective: str = Field(min_length=1, max_length=2000)


DEFINITIONS = {
    "get_work_context": (
        ContextArgs,
        "读取真实库存现金、数据时点、商品供应商和已有委托。missions分页未读完不能断言没有原任务。",
    ),
    "read_mission": (MissionArgs, "读取指定原任务及当前真实方案；优先在已有任务继续。"),
    "link_mission": (
        MissionArgs,
        "选择用户所指已有委托，结果发布时与原事项合并；没有明确匹配时先澄清。",
    ),
    "read_forecast": (
        ForecastArgs,
        "读取指定商品预测，核对请求日期与预测实际期间；范围不匹配不得说能预测该期间。",
    ),
    "compare_quantities": (
        ComparisonArgs,
        "只读数量比较，不修改业务或建立委托。必须明确实际起止日期；人工需求假设只用于比较。金额为分。",
    ),
    "propose_mission": (
        ProposalArgs,
        "用户明确要求持续跟进时提出待用户接受的委托条件；不会建立Mission或采购。source_quote逐字引用用户要求，金额为分。禁止人工需求假设。",
    ),
    "evaluate_plan": (
        PlanArgs,
        "只读比较原方案的采购数量上限；假设、先看看、如果、仅比较一律使用本工具。",
    ),
    "revise_plan": (
        RevisionArgs,
        "仅用户明确要求实际修改当前待确认方案时调用。source_quote逐字引用当前用户修改授权；生成新待确认版本，绝不采购。",
    ),
    "control_mission": (
        ControlArgs,
        "仅用户明确要求暂停/恢复后续备货跟进时调用；逐字引用当前授权。不会撤回已发订单；含糊的停一下先clarify。",
    ),
    "request_check": (CheckArgs, "用户要求刷新已有关联任务方案时请求业务检查，不代表方案已生成。"),
    "stop_analysis": (
        SourceArgs,
        "用户明确只要停止这次分析时调用；不改变Mission或采购。撤回已下订单不支持。",
    ),
}


def definitions():
    from app.quotations.processor_tools import DEFINITIONS as quotations

    return {**DEFINITIONS, **quotations}


def encoded(value):
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def exact_period(start, end, requested_start, requested_end):
    """Do not silently scale a seven-day forecast into another business period."""
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return start == requested_start and end == requested_end


def authorize_quote(args, user_messages):
    if isinstance(args, SourceArgs):
        if not user_messages or args.source_quote.strip() not in user_messages[-1].content:
            raise AppError(
                422,
                "USER_SOURCE_REQUIRED",
                "请逐字引用当前用户的明确要求；历史材料不能授权这次修改。",
            )


async def scoped_mission(session, principal, work, identifier):
    mission = await visible_mission(session, principal, identifier)
    if mission.store_id != work.store_id or (work.mission_id and work.mission_id != identifier):
        raise AppError(409, "WORK_SCOPE_CONFLICT", "只能处理本事项对应的门店和已关联任务。")
    return mission


async def execute(session, settings, principal, work, name, args, invocation_id):
    from app.agent_bridge.presentation import money_facts
    from app.operations.repository import get_catalog
    from app.reporting.repository import dashboard

    references = []
    extra = {}
    if (
        name in {"link_mission", "revise_plan", "control_mission", "request_check"}
        and not work.mission_id
    ):
        from app.work_items import repository as work_repository

        await scoped_mission(session, principal, work, args.mission_id)
        target = await work_repository.link(session, work, args.mission_id, principal)
        if target.id != work.id:
            return {"ok": True, "redirected_work_id": target.id, "references": []}
    if name == "get_work_context":
        value = {
            "catalog": encoded(await get_catalog(session, work.store_id)),
            "dashboard": encoded(await dashboard(session, work.store_id, settings)),
            "missions": encoded(
                await missions.list_missions(session, work.store_id, None, args.mission_cursor, 30)
            ),
            "linked_mission_id": work.mission_id,
            "current_time": (await session.scalar(select(func.clock_timestamp()))).isoformat(),
        }
        references = [{"type": "store", "id": work.store_id, "label": "实际经营状态"}]
        from app.operations.models import SourceCursor

        cursor = await session.scalar(
            select(SourceCursor).where(SourceCursor.store_id == work.store_id)
        )
        extra["evidence_snapshot"] = {
            "state_version": value["dashboard"]["state"]["state_version"],
            "data_as_of": value["dashboard"]["state"]["data_as_of"],
            "source_type": cursor.source if cursor else None,
        }
    elif name == "read_forecast":
        from app.forecast_v6.repository import read_current

        value = await read_current(session, work.store_id, args.sku_id, settings)
        forecast = value.get("forecast") or {}
        value = {k: v for k, v in value.items() if k not in {"history", "model"}}
        value["requested_period_matches"] = exact_period(
            forecast.get("horizon_start"),
            forecast.get("horizon_end"),
            args.requested_start,
            args.requested_end,
        )
        value["usable_for_requested_period"] = bool(
            value.get("usable_for_planning") and value["requested_period_matches"]
        )
        value["limitation"] = (
            "仅原始预测日期内有效；无法据七日结果承诺其他期间，人工假设不能作为正式需求。"
        )
        references = [{"type": "store", "id": work.store_id, "label": "预测所属经营数据"}]
    elif name in {"compare_quantities", "propose_mission"}:
        from app.planning.evaluation import evaluate_candidates
        from app.planning.simulations import capture

        value_input = await capture(session, work.store_id, args.request(), settings)
        if not exact_period(
            value_input.horizon_start,
            value_input.horizon_end,
            args.requested_start,
            args.requested_end,
        ):
            raise AppError(
                422,
                "FORECAST_PERIOD_MISMATCH",
                "现有需求不覆盖请求期间，不能换算套用；请明确独立需求假设，或更新正式预测。",
            )
        candidates, recommended, arrival = evaluate_candidates(
            state=value_input.state,
            sku_id=value_input.sku_id,
            remaining_demand=value_input.remaining_demand,
            horizon_end=value_input.horizon_end,
            offer=value_input.offer,
            policy=value_input.policy,
            eligible_inbound_qty=value_input.eligible_inbound_qty,
        )
        value = {
            "input": encoded(value_input),
            "candidates": [encoded(c) for c in candidates],
            "recommended_candidate_id": recommended.id if recommended else None,
            "expected_arrival_at": arrival.isoformat() if arrival else None,
            "hypothetical": True,
        }
        extra["evidence_snapshot"] = {
            "state_version": value_input.state.state_version,
            "data_as_of": value_input.state.data_as_of.isoformat()
            if value_input.state.data_as_of
            else None,
            "source_type": value_input.source_type,
        }
        if name == "propose_mission":
            require_role(principal, "operator")
            if value_input.demand_source == "assumption":
                raise AppError(
                    422, "SIMULATION_ASSUMPTION_ONLY", "人工需求假设只能比较，不能建立正式委托。"
                )
            existing = list(
                await session.scalars(
                    select(MissionRow).where(
                        MissionRow.store_id == work.store_id,
                        MissionRow.sku_id == args.sku_id,
                        MissionRow.status.in_(["ACTIVE", "PAUSED"]),
                    )
                )
            )
            if work.mission_id or existing:
                raise AppError(
                    409,
                    "EXISTING_MISSION",
                    "已有同商品委托，先读取并关联原任务，不能重复提出新委托。",
                )
            extra["mission_request"] = MissionCreate(
                store_id=work.store_id,
                sku_id=args.sku_id,
                objective=args.objective,
                policy=value_input.policy,
                check_interval_seconds=30,
            ).model_dump(mode="json")
            value["requires_user_acceptance"] = True
        references = [{"type": "store", "id": work.store_id, "label": "实际经营快照与确定性计算"}]
    elif name == "stop_analysis":
        value = {"stopped_analysis": True, "mission_unchanged": True, "orders_unchanged": True}
        extra["stop_analysis"] = True
    elif name in DEFINITIONS:
        mission = await scoped_mission(session, principal, work, args.mission_id)
        store = await session.get(Store, work.store_id)
        extra["evidence_snapshot"] = {
            "state_version": store.state_version,
            "data_as_of": store.data_as_of.isoformat() if store.data_as_of else None,
        }
        references = [{"type": "mission", "id": mission.id, "label": "原备货委托"}]
        if name in {"read_mission", "link_mission"}:
            value = {"mission": encoded(await missions.read_mission(session, mission.id))}
            plan = (
                await session.get(PlanRow, mission.current_plan_id)
                if mission.current_plan_id
                else None
            )
            value["plan"] = (
                encoded(
                    missions.plan_dto(plan, await session.scalar(select(func.clock_timestamp())))
                )
                if plan
                else None
            )
        elif name in {"evaluate_plan", "revise_plan"}:
            from app.planning.revisions import evaluate

            if name == "revise_plan":
                require_role(principal, "operator")
            value = await evaluate(
                session,
                settings,
                mission,
                store,
                args,
                revise=name == "revise_plan",
                actor=principal.principal_id,
            )
            if name == "revise_plan":
                references.append({"type": "plan", "id": value["id"], "label": "新待确认方案"})
        elif name == "control_mission":
            require_role(principal, "operator")
            value = encoded(
                await missions.control_mission(
                    session,
                    mission.id,
                    MissionControl(
                        operation=args.operation,
                        expected_mission_version=args.expected_mission_version,
                    ),
                    principal.principal_id,
                    invocation_id,
                )
            )
        elif name == "request_check":
            require_role(principal, "operator")
            value = encoded(
                await missions.request_check(
                    session,
                    mission.id,
                    CheckRequest(reason="用户通过事项请求重新检查"),
                    principal.principal_id,
                    invocation_id,
                )
            )
        if name in {"link_mission", "revise_plan", "control_mission", "request_check"}:
            extra["link_mission_id"] = mission.id
    else:
        from app.quotations.processor_tools import execute as quotation_tool

        return await quotation_tool(session, settings, principal, work, name, args, invocation_id)
    value["money_display"] = money_facts(value)
    return {"ok": True, "data": value, "references": references, **extra}
