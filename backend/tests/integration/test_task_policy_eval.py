import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_eval_runner_claims_only_its_own_job(db):
    from app.core.config import Settings
    from app.scheduling.handlers import make_handlers
    from app.scheduling.models import Job
    from app.scheduling.repository import enqueue
    from app.scheduling.runner import Runner

    settings = Settings(_env_file=None)
    async with db.session() as session, session.begin():
        other = await enqueue(session, job_type="worker_probe", dedup_key=str(uuid4()))
        target = await enqueue(session, job_type="worker_probe", dedup_key=str(uuid4()))
        ids = [other.id, target.id]
    try:
        await Runner(db, settings, handlers=make_handlers(settings), job_ids=[target.id]).run_once()
        async with db.session() as session:
            assert (await session.get(Job, other.id)).status == "READY"
            assert (await session.get(Job, target.id)).status == "SUCCEEDED"
    finally:
        async with db.session() as session, session.begin():
            await session.execute(delete(Job).where(Job.id.in_(ids)))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "index,action,quantity",
    [
        (0, "evaluate_plan", 20),
        (10, "revise_plan", 20),
        (11, "revise_plan", 0),
        (13, "revise_plan", 1000000),
        (49, "revise_plan", None),
    ],
)
async def test_real_tool_eval_uses_gateway_and_actual_state(db, index, action, quantity):
    from shopsteward_agent.task_policy.contracts import Decision, DecisionRecord
    from shopsteward_pt.eval.records import EpisodeSpec
    from shopsteward_pt.eval.runner import run_episode
    from shopsteward_pt.eval.scorers import score_episode

    row = json.loads(
        (ROOT / "posttraining/datasets/smoke-50.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[index]
    )
    spec = EpisodeSpec.model_validate(row)

    class FixedHarnessPolicy:
        async def decide(self, context):
            args = {"plan_id": context.plan_id, "max_purchase_qty": quantity}
            if action == "revise_plan":
                args["expected_mission_version"] = context.mission_version
            return DecisionRecord(
                decision=Decision(name=action, arguments=args),
                raw_response={},
                parse_error=None,
                usage=None,
                latency_ms=0.0,
            )

    trace = await run_episode(
        spec,
        "fixed_harness",
        mode="execution",
        config={"app_env_file": str(ROOT / "backend/.env")},
        policy=FixedHarnessPolicy(),
    )
    assert trace.environment_error is None, trace.environment_error
    result = score_episode(spec, trace, {})
    assert result.episode_success is True, (result.model_dump(), trace.receipts)
    assert trace.before_state["cash_minor"] == trace.after_state["cash_minor"]


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [28, 29])
async def test_clarification_then_real_tool_execution(db, index):
    from shopsteward_pt.eval.policies import RulePolicy
    from shopsteward_pt.eval.records import EpisodeSpec
    from shopsteward_pt.eval.runner import run_episode
    from shopsteward_pt.eval.scorers import score_episode

    row = json.loads(
        (ROOT / "posttraining/datasets/smoke-50.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[index]
    )
    spec = EpisodeSpec.model_validate(row)
    question = "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"
    reviews = {
        f"{spec.episode_id}:0": {
            "question": question,
            "slot": "max_purchase_qty",
            "relevant": True,
            "no_guess": True,
            "no_known_id_request": True,
            "reviewer": "test",
        }
    }
    trace = await run_episode(
        spec,
        "B0",
        mode="execution",
        config={"app_env_file": str(ROOT / "backend/.env")},
        policy=RulePolicy(),
        reviews=reviews,
    )
    assert trace.environment_error is None, trace.environment_error
    assert len(trace.steps) == 2 and len(trace.receipts) == 1
    result = score_episode(spec, trace, reviews)
    assert result.episode_success is True, result.model_dump()
    assert result.predicate_results["no_mutation_before_reply"] is True
