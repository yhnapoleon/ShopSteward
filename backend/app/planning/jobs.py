from sqlalchemy import func, select

from app.alerts.repository import reconcile
from app.alerts.rules import evaluate, inconclusive
from app.core.hashing import digest
from app.missions.models import MissionRow, PlanRow
from app.missions.repository import lock_mission, queue_check, timeline
from app.operations.models import ForecastRow, SourceCursor, StockRow, Store
from app.planning.canonical import canonical
from app.planning.engine import build_plan, check_status, input_hash
from app.planning.schemas import DecisionSnapshot
from app.planning.snapshot import prepare, source_fresh
from app.scheduling.handlers import Handler


def intent_hash(snapshot):
    # Rejecting an intent must not be bypassed by a fixed-forecast TTL renewal alone.
    value = canonical(snapshot.model_dump(mode="json"))
    state = value["state"]
    for field in ["state_version", "data_as_of"]:
        state.pop(field)
    for stock in state["stocks"]:
        stock.pop("forecast_version")
    return digest(
        {
            "state": state,
            "policy": value["policy"],
            "offer": value["offer"],
            "forecast": {
                key: value["forecast"][key]
                for key in [
                    "remaining_demand",
                    "horizon_start",
                    "horizon_end",
                    "source",
                    "model_name",
                    "model_version",
                ]
            },
            "rule_version": value["rule_version"],
        }
    )


def result(summary, status, mission, *, plan=None, state_version=None):
    references = [{"type": "mission", "id": mission.id, "version": str(mission.mission_version)}]
    if plan:
        references.append({"type": "plan", "id": plan.id, "version": str(plan.plan_version)})
    value = {"summary": summary, "check_status": status, "references": references}
    if state_version:
        value["output_state_version"] = state_version
    return value


def make_handlers(settings):
    async def run(db, job):
        prepared = await prepare(db, job.mission_id, settings)
        # Pure computation is outside the publication transaction.
        draft = (
            build_plan(
                job.mission_id,
                prepared.plan_counter + 1,
                prepared.snapshot,
                ttl_seconds=settings.plan_ttl_seconds,
            )
            if prepared.snapshot
            else None
        )
        return prepared, draft

    async def apply(session, job, value):
        prepared, draft = value
        store, mission = await lock_mission(session, job.mission_id)
        now = await session.scalar(select(func.clock_timestamp()))
        old = (
            await session.get(PlanRow, mission.current_plan_id, with_for_update=True)
            if mission.current_plan_id
            else None
        )
        if old and old.status == "PENDING_APPROVAL":
            if old.expires_at <= now:
                old.status = "EXPIRED"
                mission.current_plan_id = None
            elif (
                old.state_version != store.state_version
                or old.document["input_snapshot"]["mission_version"] != mission.mission_version
            ):
                old.status = "SUPERSEDED"
                mission.current_plan_id = None
        if mission.status != "ACTIVE" or mission.current_action_id is not None:
            mission.recheck_required = mission.manual_check_requested = False
            return result("Mission inactive or an action is pending", "SKIPPED", mission)
        if (
            store.state_version != prepared.state_version
            or mission.mission_version != prepared.mission_version
            or mission.plan_counter != prepared.plan_counter
        ):
            mission.recheck_required = True
            return result("Inputs changed; a follow-up check was requested", "SKIPPED", mission)
        cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == store.id))
        if prepared.reason or not source_fresh(cursor, now, settings.source_stale_seconds):
            await reconcile(
                session,
                mission,
                [inconclusive(prepared.reason or "DATA_STALE")],
                {"DATA_STALE"},
                store.state_version,
            )
            return result(prepared.reason or "DATA_STALE", "INCONCLUSIVE", mission)
        if draft.expires_at <= now:
            await reconcile(
                session,
                mission,
                [inconclusive("PLAN_INPUT_EXPIRED")],
                {"DATA_STALE"},
                store.state_version,
            )
            return result("PLAN_INPUT_EXPIRED", "INCONCLUSIVE", mission)
        snapshot = prepared.snapshot
        if prepared.renewal:
            stock = await session.get(StockRow, (store.id, mission.sku_id))
            stock.forecast_version = snapshot.forecast.forecast_version
            store.state_version += 1
            session.add(
                ForecastRow(
                    store_id=store.id,
                    sku_id=stock.sku_id,
                    version=stock.forecast_version,
                    source_sequence=cursor.last_sequence,
                    document=prepared.renewal,
                )
            )
        signature = input_hash(snapshot)

        async def publish_alerts(plan_id):
            await reconcile(
                session,
                mission,
                evaluate(snapshot, draft.candidates),
                {"STOCKOUT_RISK", "CASH_CONSTRAINT", "DATA_STALE"},
                store.state_version,
                plan_id,
            )

        if (
            old
            and old.status == "REJECTED"
            and not prepared.manual
            and intent_hash(snapshot)
            == intent_hash(DecisionSnapshot.model_validate(old.document["input_snapshot"]))
        ):
            await publish_alerts(old.id)
            return result(
                "Previously rejected intent suppressed",
                check_status(snapshot),
                mission,
                plan=old,
                state_version=store.state_version,
            )
        if (
            old
            and old.status == "PENDING_APPROVAL"
            and old.expires_at > now
            and old.input_hash == signature
        ):
            if not mission.recheck_required:
                mission.manual_check_requested = False
            await publish_alerts(old.id)
            return result(
                "Existing valid plan reused",
                check_status(snapshot),
                mission,
                plan=old,
                state_version=store.state_version,
            )
        if old and old.status == "PENDING_APPROVAL":
            old.status = "SUPERSEDED"
        row = PlanRow(
            id=draft.id,
            mission_id=mission.id,
            plan_version=draft.plan_version,
            state_version=draft.state_version,
            input_hash=signature,
            status=draft.status,
            document=draft.model_dump(mode="json"),
            created_at=draft.created_at,
            expires_at=draft.expires_at,
        )
        session.add(row)
        mission.plan_counter = draft.plan_version
        mission.current_plan_id = draft.id
        mission.updated_at = now
        if not mission.recheck_required:
            mission.manual_check_requested = False
        await timeline(
            session,
            mission,
            "PLAN_CREATED",
            draft.explanation,
            references=[{"type": "plan", "id": draft.id, "version": str(draft.plan_version)}],
        )
        await session.flush()
        await publish_alerts(row.id)
        return result(
            "Candidate comparison saved",
            check_status(snapshot),
            mission,
            plan=row,
            state_version=store.state_version,
        )

    async def after_complete(session, job, outcome):
        # apply holds store/mission locks; completing the job frees its unique slot.
        mission = await session.get(MissionRow, job.mission_id)
        if mission:
            await timeline(
                session,
                mission,
                "CHECK_COMPLETED",
                f"检查{outcome['check_status']}：{outcome['summary']}（任务{job.id}）",
                references=outcome["references"],
            )
        if mission and mission.status == "ACTIVE" and mission.recheck_required:
            store = await session.get(Store, mission.store_id)
            mission.recheck_required = False
            await queue_check(session, store, mission, key="followup-" + job.id)

    return {
        "check_mission": Handler(run, retry_safe=True, apply=apply, after_complete=after_complete)
    }
