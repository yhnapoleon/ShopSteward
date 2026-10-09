"""Fresh business fixtures, real jobs and authenticated in-process tool requests."""

import json
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from shopsteward_agent.task_policy.contracts import Decision, PolicyContext, decision_tool_schemas
from sqlalchemy import select
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[4]


def fresh_seed():
    contract = json.loads((ROOT / "docs/api/services.openapi.json").read_text(encoding="utf-8"))
    sample = contract["paths"]["/sim/v1/runs"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["example"]
    suffix = uuid4().hex
    seed = json.loads(
        json.dumps(sample)
        .replace("store_001", "eval_store_" + suffix)
        .replace("scenario_001", "eval_run_" + suffix)
        .replace("forecast_001", "eval_forecast_" + suffix)
    )
    now = datetime.now(UTC)
    seed["simulation_time"] = now.isoformat()
    seed["initial_state"].update(data_as_of=now.isoformat(), simulation_time=now.isoformat())
    seed["initial_forecast"].update(
        data_as_of=now.isoformat(),
        horizon_start=now.isoformat(),
        horizon_end=(now + timedelta(days=7)).isoformat(),
        valid_until=(now + timedelta(hours=1)).isoformat(),
    )
    for offer in seed["initial_catalog"]["offers"]:
        offer.update(
            valid_from=(now - timedelta(minutes=1)).isoformat(),
            valid_until=(now + timedelta(days=1)).isoformat(),
        )
    return seed


class Fixture:
    def __init__(self, app, client, token, seed):
        self.app, self.client, self.token, self.seed = app, client, token, seed
        self.db = app.state.db
        self.history = []
        self.baseline_plan_id = None

    async def post(self, path, body):
        response = await self.client.post(
            path,
            json=body,
            headers={"Authorization": "Bearer " + self.token, "Idempotency-Key": str(uuid4())},
        )
        if response.status_code >= 400:
            raise ValueError(
                f"fixture request {path}: HTTP {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    async def run_job(self, job_id, handlers):
        from app.scheduling.models import Job
        from app.scheduling.runner import Runner

        await Runner(
            self.db, self.app.state.settings, handlers=handlers, job_ids=[job_id]
        ).run_once()
        async with self.db.session() as session:
            job = await session.get(Job, job_id)
            if job.status != "SUCCEEDED":
                raise ValueError(
                    f"fixture job failed: {job.job_type}/{job.status}/{job.error_code}"
                )

    async def initialize(self, spec):
        from app.operations.repository import initialize, mark_caught_up
        from app.operations.schemas import ScenarioRun
        from app.planning.jobs import make_handlers
        from app.scheduling.models import Job

        async with self.db.session() as session, session.begin():
            await initialize(session, ScenarioRun.model_validate(self.seed))
            await mark_caught_up(session, self.seed["scenario_run_id"], 0)
        mission = await self.post(
            "/api/v1/missions",
            {
                "store_id": self.seed["store_id"],
                "sku_id": "sku_001",
                "objective": "Cash floor and demand coverage",
                "policy": {
                    "cash_floor_minor": 30000,
                    "candidate_quantities": [0, 20, 40, 80],
                    "supplier_id": "supplier_001",
                },
                "check_interval_seconds": 30,
            },
        )
        self.mission_id = mission["id"]
        async with self.db.session() as session:
            job_id = await session.scalar(
                select(Job.id).where(
                    Job.mission_id == self.mission_id, Job.job_type == "check_mission"
                )
            )
        if not job_id:
            raise ValueError("fixture initial planning job missing")
        await self.run_job(job_id, make_handlers(self.app.state.settings))
        self.conversation_id = (
            await self.post(f"/api/v1/missions/{self.mission_id}/conversations", {})
        )["id"]
        initial = await self.snapshot()
        self.historical_plan_id = initial["current_plan_id"]
        # Reach each requested version through actual revisions, including history turns.
        prior_revisions = sum(h.action == "revise_plan" for h in spec.history)
        for _ in range(spec.fixture_mission_version - 1 - prior_revisions):
            context = await self.context("将本次采购上限修改为20件。")
            decision = Decision(
                name="revise_plan",
                arguments={
                    "plan_id": context.plan_id,
                    "expected_mission_version": context.mission_version,
                    "max_purchase_qty": 20,
                },
            )
            outcome = await self.invoke("将本次采购上限修改为20件。", decision)
            if not outcome["receipt"]["result"].get("ok"):
                raise ValueError("fixture preparatory revision rejected")
        self.history = []
        for prior in spec.history:
            context = await self.context(prior.user_message)
            args = {
                "plan_id": context.plan_id
                if prior.plan_reference == "$current_plan_id"
                else self.historical_plan_id,
                "max_purchase_qty": prior.max_purchase_qty,
            }
            if prior.action == "revise_plan":
                args["expected_mission_version"] = context.mission_version
            outcome = await self.invoke(
                prior.user_message, Decision(name=prior.action, arguments=args)
            )
            if not outcome["receipt"]["result"].get("ok"):
                raise ValueError("fixture historical interaction rejected")
            self.history.extend(
                [
                    {"role": "user", "content": prior.user_message},
                    {"role": "assistant", "content": outcome["delivery"]["content"]},
                ]
            )
        snapshot = await self.snapshot()
        if snapshot["mission_version"] != spec.fixture_mission_version:
            raise ValueError("fixture mission version does not match recipe")
        self.baseline_plan_id = snapshot["current_plan_id"]

    async def snapshot(self):
        from app.execution.models import ActionRow
        from app.missions.models import MissionRow, PlanRow
        from app.operations.repository import get_state

        async with self.db.session() as session:
            mission = await session.get(MissionRow, self.mission_id)
            plan = (
                await session.get(PlanRow, mission.current_plan_id)
                if mission.current_plan_id
                else None
            )
            old = (
                await session.get(PlanRow, self.baseline_plan_id) if self.baseline_plan_id else plan
            )
            state = await get_state(session, self.seed["store_id"])
            actions = list(
                await session.scalars(
                    select(ActionRow.id)
                    .where(ActionRow.mission_id == self.mission_id)
                    .order_by(ActionRow.id)
                )
            )
            return {
                "current_plan_id": mission.current_plan_id,
                "mission_version": mission.mission_version,
                "mission_status": mission.status,
                "task_constraints": dict(mission.task_constraints),
                "policy": dict(mission.policy),
                "plan_document": plan.document if plan else None,
                "old_plan_document": old.document if old else None,
                "plan_status": plan.status if plan else None,
                "cash_minor": state.cash_minor,
                "stocks": [s.model_dump(mode="json") for s in state.stocks],
                "purchase_action_ids": actions,
                "historical_plan_id": getattr(self, "historical_plan_id", None),
            }

    async def context(self, message):
        snapshot = await self.snapshot()
        return PolicyContext(
            messages=[*self.history, {"role": "user", "content": message}],
            mission_id=self.mission_id,
            plan_id=snapshot["current_plan_id"],
            mission_version=snapshot["mission_version"],
            quantity_unit="件",
            quantity_cap=snapshot["task_constraints"].get("max_purchase_qty"),
            tool_schemas=decision_tool_schemas(),
            context_version="replenishment-real-v1",
        )

    async def invoke(self, message, decision):
        from app.agent_bridge.jobs import make_handlers
        from app.agent_bridge.models import AgentRun

        outcome = {}

        async def execute(context):
            delivery = {"kind": decision.name}
            if decision.name in {"evaluate_plan", "revise_plan"}:
                response = await self.client.post(
                    f"/internal/v1/agent-tools/{decision.name}",
                    headers={"Authorization": "Bearer " + context["token"]},
                    json={
                        "run_id": context["run_id"],
                        "invocation_id": str(uuid4()),
                        "arguments": decision.arguments,
                    },
                )
                result = response.json()
                outcome["receipt"] = {
                    "tool": decision.name,
                    "arguments": decision.arguments,
                    "result": result,
                    "http_status": response.status_code,
                    "run_id": context["run_id"],
                }
                data = result.get("data") or {}
                cap = (
                    data.get("input_snapshot", {}).get("task_constraints", {})
                    if decision.name == "revise_plan"
                    else data.get("task_constraints", {})
                ).get("max_purchase_qty")
                delivery.update(
                    plan_id=data.get("id", data.get("base_plan_id")),
                    max_purchase_qty=cap,
                    content=json.dumps(
                        {
                            "action": decision.name,
                            "ok": result.get("ok"),
                            "plan_id": data.get("id", data.get("base_plan_id")),
                            "max_purchase_qty": cap,
                        },
                        ensure_ascii=False,
                    ),
                )
            else:
                delivery["content"] = decision.arguments.get(
                    "question", decision.arguments.get("reason", "")
                )
            outcome["delivery"] = delivery
            return {"status": "SUCCEEDED", "content": delivery["content"], "references": []}

        result = await self.post(
            f"/api/v1/conversations/{self.conversation_id}/messages", {"content": message}
        )
        async with self.db.session() as session:
            run = await session.get(AgentRun, result["agent_run_id"])
            job_id = run.job_id
        if not job_id:
            raise ValueError("fixture agent run was not scheduled")
        await self.run_job(job_id, make_handlers(self.app.state.settings, executor=execute))
        return outcome


@asynccontextmanager
async def fixture_for(spec, config):
    from app.core.config import Settings
    from app.main import create_app

    source = Settings(_env_file=config["app_env_file"])
    url = make_url(source.database_url.get_secret_value()).set(database="shopsteward_test")
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "shopsteward_test":
        raise ValueError("eval fixture requires the local dedicated test database")
    seed, token = fresh_seed(), secrets.token_urlsafe(32)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=url.render_as_string(hide_password=False),
        agent_enabled=True,
        source_stale_seconds=3600,
        plan_ttl_seconds=3600,
        auth_tokens=[
            {
                "token": token,
                "principal_id": "eval_operator",
                "roles": ["operator"],
                "store_ids": [seed["store_id"]],
            }
        ],
    )
    app = create_app(settings)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://eval"
        ) as client:
            fixture = Fixture(app, client, token, seed)
            await fixture.initialize(spec)
            yield fixture
    finally:
        await app.state.db.dispose()
