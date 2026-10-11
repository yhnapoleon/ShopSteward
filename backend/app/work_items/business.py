"""Read-only business state for every card, independent of the open task/UI."""

from datetime import timedelta

from sqlalchemy import func, select

from app.execution.models import ActionRow
from app.missions.models import InboundRow, MissionRow, PlanRow, ScheduleRow
from app.missions.repository import mission_dto
from app.operations.models import OfferRow, SourceCursor, StockRow, Store
from app.planning.canonical import canonical
from app.planning.engine import proposal_hash
from app.planning.schemas import Plan
from app.planning.snapshot import source_fresh
from app.work_items.schemas import WorkBusinessState


def classify(
    mission, plan_row, action, store, cursor, in_transit, now, settings, offer=None, stock=None
):
    base = dict(
        state_version=store.state_version,
        mission_version=mission.mission_version,
        plan_id=mission.current_plan_id,
        plan_version=plan_row.plan_version if plan_row else None,
        action_id=action.id if action else None,
        observed_at=now,
    )

    def status(
        code,
        label,
        detail,
        priority,
        action_label="查看备货",
        tone="blue",
        can_confirm=False,
        valid_until=None,
    ):
        return WorkBusinessState(
            **base,
            code=code,
            label=label,
            detail=detail,
            priority=priority,
            action_label=action_label,
            tone=tone,
            needs_attention=priority < 40,
            can_confirm=can_confirm,
            valid_until=valid_until,
        )

    if action and action.status in {"QUEUED", "EXECUTING", "UNKNOWN"}:
        if action.status == "UNKNOWN":
            return status(
                "UNKNOWN",
                "采购结果待核实",
                "采购可能已受理，正在核对原回执；不要重复提交。",
                0,
                "查看采购回执",
                "amber",
            )
        return status(
            action.status,
            "采购排队中" if action.status == "QUEUED" else "采购执行中",
            "确认已受理，采购及付款结果以实际回执为准。",
            45,
            "查看采购进度",
        )
    if mission.status in {"COMPLETED", "CANCELLED"}:
        return status(
            mission.status,
            "备货委托已结束" if mission.status == "COMPLETED" else "备货委托已取消",
            "决定与已提交的采购记录仍保留。",
            90,
            tone="gray",
        )
    if mission.status == "PAUSED":
        return status(
            "PAUSED",
            "备货跟进已暂停",
            "后续主动检查已暂停；已提交采购的核实和到货仍会继续。",
            65,
            "查看暂停安排",
            "gray",
        )
    if not source_fresh(cursor, now, settings.source_stale_seconds):
        return status(
            "DATA_STALE",
            "数据待同步",
            "取得最新经营数据后，再核对方案。",
            20,
            "查看数据状态",
            "amber",
        )
    fresh_until = cursor.last_success_at + timedelta(seconds=settings.source_stale_seconds)
    if plan_row and plan_row.status in {"PENDING_APPROVAL", "EXPIRED", "SUPERSEDED"}:
        plan = Plan.model_validate(plan_row.document)
        snapshot = plan.input_snapshot
        deadline = min(
            plan_row.expires_at,
            plan.expires_at,
            snapshot.forecast.valid_until,
            snapshot.offer.valid_until,
        )
        stale = (
            plan_row.status != "PENDING_APPROVAL"
            or deadline <= now
            or plan.state_version != store.state_version
            or snapshot.mission_version != mission.mission_version
            or plan.policy_version != mission.policy_version
            or snapshot.policy.model_dump(mode="json") != mission.policy
            or snapshot.task_constraints != mission.task_constraints
            or offer is None
            or canonical(offer.document) != canonical(snapshot.offer.model_dump(mode="json"))
            or stock is None
            or stock.forecast_version != plan.forecast_version
            or proposal_hash(plan_row.document) != plan.proposal_hash
        )
        if stale:
            return status(
                "PLAN_STALE",
                "方案待更新",
                "经营数据、条件或有效期已变化，旧方案不能确认。",
                15,
                "查看并重新检查",
                "amber",
            )
        if plan.proposed_purchase:
            if store.active_action_id or mission.current_action_id:
                return status(
                    "STORE_BUSY",
                    "等待已有采购核实",
                    "门店已有采购在处理，核实完成后再决定下一笔。",
                    25,
                    "查看备货状态",
                    "amber",
                )
            return status(
                "PENDING_APPROVAL",
                "等待你确认",
                "先核对数量、现金底线和依据，再确认这笔采购。",
                10,
                "核对采购方案",
                "amber",
                True,
                min(deadline, fresh_until),
            )
    if in_transit:
        return status(
            "IN_TRANSIT",
            "等待到货",
            f"本委托还有{in_transit}件在途，到货后更新。",
            50,
            "查看到货进度",
        )
    return status("FOLLOWING", "持续跟进中", "等待下一次业务检查；有新的可行方案时再请你确认。", 70)


async def load(session, rows, settings):
    ids = {row.mission_id for row in rows if row.mission_id}
    if not ids:
        return {}
    pairs = (
        await session.execute(
            select(MissionRow, ScheduleRow)
            .join(ScheduleRow, ScheduleRow.mission_id == MissionRow.id)
            .where(MissionRow.id.in_(ids))
        )
    ).all()
    missions = [m for m, _ in pairs]
    stores = {
        s.id: s
        for s in await session.scalars(
            select(Store).where(Store.id.in_({m.store_id for m in missions}))
        )
    }
    cursors = {
        c.store_id: c
        for c in await session.scalars(
            select(SourceCursor).where(SourceCursor.store_id.in_(stores))
        )
    }
    plans = {
        p.id: p
        for p in await session.scalars(
            select(PlanRow).where(
                PlanRow.id.in_({m.current_plan_id for m in missions if m.current_plan_id})
            )
        )
    }
    actions = {
        a.id: a
        for a in await session.scalars(
            select(ActionRow).where(
                ActionRow.id.in_({m.current_action_id for m in missions if m.current_action_id})
            )
        )
    }
    offers = {
        (o.store_id, o.sku_id, o.supplier_id): o
        for o in await session.scalars(select(OfferRow).where(OfferRow.store_id.in_(stores)))
    }
    stocks = {
        (s.store_id, s.sku_id): s
        for s in await session.scalars(select(StockRow).where(StockRow.store_id.in_(stores)))
    }
    inbound = dict(
        (
            await session.execute(
                select(
                    ActionRow.mission_id, func.sum(InboundRow.ordered_qty - InboundRow.received_qty)
                )
                .join(InboundRow, InboundRow.action_id == ActionRow.id)
                .where(ActionRow.mission_id.in_(ids))
                .group_by(ActionRow.mission_id)
            )
        ).all()
    )
    now = await session.scalar(select(func.clock_timestamp()))
    return {
        m.id: (
            mission_dto(m, schedule),
            classify(
                m,
                plans.get(m.current_plan_id),
                actions.get(m.current_action_id),
                stores[m.store_id],
                cursors.get(m.store_id),
                inbound.get(m.id, 0),
                now,
                settings,
                offers.get((m.store_id, m.sku_id, m.policy["supplier_id"])),
                stocks.get((m.store_id, m.sku_id)),
            ),
        )
        for m, schedule in pairs
    }
