"""Owner-scoped business tools for the intake processor; never purchase authority."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
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


PERIOD = "用户说了日期或期间时按原话填写（业务时区Asia/Shanghai）；没说时省略，按预测实际期间。"


class ForecastArgs(Empty):
    sku_id: str = Field(min_length=1, max_length=128)
    requested_start: AwareDatetime | None = Field(default=None, description=PERIOD)
    requested_end: AwareDatetime | None = Field(default=None, description=PERIOD)

    @model_validator(mode="after")
    def window(self):
        if (self.requested_start is None) != (self.requested_end is None):
            raise ValueError("Give both requested_start and requested_end, or neither")
        if self.requested_start is not None and self.requested_end <= self.requested_start:
            raise ValueError("Requested period must be ordered")
        return self


class ComparisonArgs(ForecastArgs):
    expected_state_version: int = Field(ge=1)
    supplier_id: str = Field(min_length=1, max_length=128)
    cash_floor_minor: int = Field(strict=True, ge=0, le=10**12)
    candidate_quantities: list[int] = Field(
        min_length=1,
        max_length=20,
        description="要比较的采购件数；系统自动加入0件（不买）作为基线并去重排序。",
    )
    remaining_demand: int | None = Field(default=None, strict=True, ge=0, le=1000000)
    horizon_days: int | None = Field(default=None, strict=True, ge=1, le=90)

    @field_validator("candidate_quantities")
    @classmethod
    def with_no_purchase(cls, quantities):
        # Every comparison and proposed policy keeps "buy nothing" as its baseline.
        # Adding it only widens the options, so a model that omits it is not refused.
        return sorted({0, *quantities})

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
        "读取指定商品当前规划所用的需求预测及其实际期间；所问期间不在其内时不得说能预测该期间。",
    ),
    "compare_quantities": (
        ComparisonArgs,
        "只读数量比较，不修改业务或建立委托。所问期间须落在预测实际期间内，按预测实际期间计算；"
        "人工需求假设只用于比较。金额为分。候选件数总含0件（不买），未给出时系统自动加入。",
    ),
    "propose_mission": (
        ProposalArgs,
        "用户明确要求持续跟进或保证不断货（如帮我盯着、以后都看着、keep an eye on it、"
        "keep milk in stock、make sure it doesn't run out）时提出待用户接受的委托条件；"
        "不会建立Mission或采购。source_quote逐字引用用户要求，金额为分。禁止人工需求假设。"
        "候选件数总含0件（不买），未给出时系统自动加入。",
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


def covers_period(start, end, requested_start, requested_end):
    """The forecast's own days must include every business day asked about.

    A seven-day forecast is never scaled or shifted into another period. A request inside
    it is compared on the whole forecast period, which the result states.
    """
    from app.work_items.authorization import last_day, local_day

    if start is None or end is None:
        return False
    if requested_start is None:
        return True
    return local_day(start) <= local_day(requested_start) and last_day(requested_end) <= last_day(
        end
    )


def quoted(quote, content):
    """A verbatim quote, allowing for the apostrophes, spacing and case a model normalizes."""
    from app.work_items.authorization import plain

    def flat(text):
        return " ".join(plain(text).replace("“", '"').replace("”", '"').split()).casefold()

    return bool(quote.strip()) and flat(quote) in flat(content)


def authorize_quote(args, user_messages):
    if isinstance(args, SourceArgs):
        if not user_messages or not quoted(args.source_quote, user_messages[-1].content):
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
    from app.agent_bridge.presentation import local_times, money_facts
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
        from app.planning.simulations import forecast_reading

        # The demand a comparison or proposal would plan on, not only a v6 model reading.
        value = await forecast_reading(session, work.store_id, args.sku_id, settings)
        forecast = value.get("forecast") or {}
        value["requested_period_matches"] = covers_period(
            forecast.get("horizon_start"),
            forecast.get("horizon_end"),
            args.requested_start,
            args.requested_end,
        )
        value["usable_for_requested_period"] = bool(
            value.get("usable_for_planning") and value["requested_period_matches"]
        )
        value["limitation"] = (
            "仅预测实际期间内有效；无法据七日结果承诺其他期间，人工假设不能作为正式需求。"
        )
        references = [{"type": "store", "id": work.store_id, "label": "预测所属经营数据"}]
    elif name in {"compare_quantities", "propose_mission"}:
        from app.planning.evaluation import evaluate_candidates
        from app.planning.simulations import capture

        value_input = await capture(session, work.store_id, args.request(), settings)
        if not covers_period(
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
            # The period the figures are for; a shorter question inside it gets these figures.
            "planning_period": {
                "start": value_input.horizon_start.isoformat(),
                "end": value_input.horizon_end.isoformat(),
            },
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
    return {"ok": True, "data": local_times(value), "references": references, **extra}
