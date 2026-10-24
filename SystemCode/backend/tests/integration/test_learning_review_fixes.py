from uuid import uuid4

import pytest
from sqlalchemy import select
from test_learning_admission import candidate
from test_learning_storage import enable, event
from test_missions import clean_queue, environment, headers  # noqa: F401

pytestmark = pytest.mark.integration


async def approved_fixture(s, scope, settings, principal):
    from app.learning.evaluation import static_evaluate
    from app.learning.lifecycle import transition
    from app.learning.models import AssetRow, EvaluationRow
    from app.learning.schemas import Transition

    rev = await candidate(s, scope)
    asset = await s.get(AssetRow, rev.asset_id)
    result = await static_evaluate(
        s, scope=scope, asset=asset, revision=rev, settings=settings, principal=principal
    )
    await s.flush()
    evaluation = await s.get(EvaluationRow, result["id"])
    evaluation.report = {
        **evaluation.report,
        "checks": {f"H{i}": "pass" for i in range(1, 7)},
        "scores": {f"S{i}": 3 for i in range(1, 7)},
        "measured": True,
        "reviewer_kind": "human_reviewed",
        "reviewed_by": ["test-A", "test-B"],
        "independent_cases": 200,
        "suite_kinds": ["normal", "negative", "boundary", "recovery", "composition"],
        "evidence_refs": ["test-artifact"],
        "quality_delta_lower": -0.01,
        "improvement": 0.2,
        "dimension_reviews": {
            f"S{i}": {"score": 3, "evidence_refs": ["test-artifact"], "reason": "Test only"}
            for i in range(1, 7)
        },
    }
    await transition(
        s,
        scope=scope,
        asset_id=asset.id,
        body=Transition(
            expected_version=1, revision=1, action="activate", evaluation_id=evaluation.id
        ),
        key=str(uuid4()),
        settings=settings,
        principal=principal,
    )
    return asset, rev, evaluation


async def test_static_recheck_does_not_replace_active_release_report(db):
    from app.learning.evaluation import static_evaluate
    from app.learning.schemas import LearningScope

    async with environment(db) as (seed, client):
        cfg = client._transport.app.state.settings
        principal = next(p for p in cfg.auth_tokens if p.principal_id == "admin")
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            asset, rev, evaluation = await approved_fixture(s, scope, cfg, principal)
            await static_evaluate(
                s, scope=scope, asset=asset, revision=rev, settings=cfg, principal=principal
            )
            assert rev.evaluation_id == evaluation.id
            assert asset.active_revision == 1


async def test_run_pins_revision_and_empty_selection_across_publication(db):
    from app.learning.lifecycle import binding, transition
    from app.learning.models import EvaluationRow
    from app.learning.repository import create_candidate
    from app.learning.retrieval import retrieve
    from app.learning.schemas import LearningScope, Transition

    async with environment(db) as (seed, client):
        cfg = client._transport.app.state.settings
        cfg.learning_enabled = True
        principal = next(p for p in cfg.auth_tokens if p.principal_id == "admin")
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            args = dict(
                scope=scope,
                family="replenishment",
                facts={"current_mission": True, "unknown_execution": False},
                settings=cfg,
                principal=principal,
            )
            assert await retrieve(s, **args, run_id="empty-run") == []
            asset, rev, ev = await approved_fixture(s, scope, cfg, principal)
            assert (await retrieve(s, **args, run_id="pinned-run"))[0]["revision"] == 1
            new = await create_candidate(
                s, scope=scope, spec=rev.spec | {"summary": "Updated"}, evidence=rev.evidence_ids
            )
            current = await binding(
                s, scope=scope, asset=asset, revision=new, settings=cfg, principal=principal
            )
            s.add(
                EvaluationRow(
                    id="new-" + asset.id[:50],
                    asset_id=asset.id,
                    revision=2,
                    report=ev.report | {"binding": current},
                    decision={"status": "pass", "reasons": []},
                )
            )
            await s.flush()
            await transition(
                s,
                scope=scope,
                asset_id=asset.id,
                body=Transition(
                    expected_version=asset.version,
                    revision=2,
                    action="activate",
                    evaluation_id="new-" + asset.id[:50],
                ),
                key=str(uuid4()),
                settings=cfg,
                principal=principal,
            )
            assert (await retrieve(s, **args, run_id="pinned-run"))[0]["revision"] == 1
            assert await retrieve(s, **args, run_id="empty-run") == []
            assert (await retrieve(s, **args, run_id="next-run"))[0]["revision"] == 2


async def test_real_goods_update_outcomes_and_replay_once(db):
    from test_execution import Supplier, approve, execute, planned
    from test_operations import event as source_event
    from test_operations import ingest

    from app.learning.collector import drain
    from app.learning.models import EpisodeRow, OutcomeRow
    from app.learning.schemas import LearningScope

    async with environment(db) as (seed, client):
        db.learning_enabled = True
        client._transport.app.state.db.learning_enabled = True
        try:
            async with db.session() as s, s.begin():
                await enable(s, LearningScope(principal_id="operator", store_id=seed["store_id"]))
            mission, plan = await planned(db, seed, client)
            accepted = await approve(client, plan)
            await execute(db, seed, Supplier())
            first = source_event(
                seed, 1, "GOODS_RECEIVED", action_id=accepted["action_id"], quantity=15
            )
            await ingest(db, seed, [first])
            async with db.session() as s, s.begin():
                await drain(s)
                episode = await s.scalar(
                    select(EpisodeRow).where(EpisodeRow.intent_key == "mission:" + mission["id"])
                )
                partial = await s.get(OutcomeRow, (episode.id, episode.outcome_revision))
                assert partial.document["metrics"]["received_qty"] == 15
                assert partial.document["business_status"] == "pending"
            second = source_event(
                seed, 2, "GOODS_RECEIVED", action_id=accepted["action_id"], quantity=25
            )
            await ingest(db, seed, [second])
            await ingest(db, seed, [second])
            async with db.session() as s, s.begin():
                await drain(s)
                episode = await s.get(EpisodeRow, episode.id)
                outcome = await s.get(OutcomeRow, (episode.id, episode.outcome_revision))
                assert outcome.document["business_status"] == "matured"
                assert outcome.document["metrics"]["received_qty"] == 40
        finally:
            db.learning_enabled = False


async def test_cancelled_episode_cannot_be_revived_by_late_receipt(db):
    from app.learning.collector import consume
    from app.learning.models import EpisodeRow
    from app.learning.outbox import append
    from app.learning.schemas import LearningScope

    async with environment(db) as (seed, client):
        scope = LearningScope(principal_id="operator", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            for version, kind in enumerate(["OPTIONS_READY", "CANCELLED", "EXECUTION_OBSERVED"], 1):
                e = event("same").model_copy(update={"source_version": version, "event_type": kind})
                eid = await consume(s, event_id=await append(s, scope=scope, event=e))
            assert (await s.get(EpisodeRow, eid)).eligible is False


async def test_inherited_outcome_never_predates_its_evidence(db):
    from datetime import timedelta

    from app.learning.collector import consume
    from app.learning.models import EpisodeRow, OutcomeRow
    from app.learning.outbox import append
    from app.learning.schemas import LearningScope

    async with environment(db) as (seed, client):
        scope = LearningScope(principal_id="operator", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            earlier = event("late-plan")
            later = earlier.model_copy(
                update={
                    "source_version": 2,
                    "event_type": "EXECUTION_OBSERVED",
                    "available_at": earlier.available_at + timedelta(seconds=1),
                    "payload": {"business_status": "matured", "execution_status": "SUCCEEDED"},
                }
            )
            eid = await consume(s, event_id=await append(s, scope=scope, event=later))
            await consume(s, event_id=await append(s, scope=scope, event=earlier))
            ep = await s.get(EpisodeRow, eid)
            outcome = await s.get(OutcomeRow, (eid, ep.outcome_revision))
            assert outcome.available_at >= later.available_at


async def test_mission_owner_stays_creator_and_real_cancel_removes_eligibility(db):
    from test_planning_jobs import start

    from app.learning.capture import mission_event
    from app.learning.collector import drain
    from app.learning.models import EpisodeRow
    from app.learning.repository import scope_id
    from app.learning.schemas import LearningScope
    from app.missions.models import MissionRow

    async with environment(db) as (seed, client):
        app = client._transport.app
        app.state.db.learning_enabled = True
        owner = LearningScope(principal_id="operator", store_id=seed["store_id"])
        other = owner.model_copy(update={"principal_id": "admin"})
        async with db.session() as s, s.begin():
            await enable(s, owner)
            await enable(s, other)
        mission = await start(client, seed)
        async with db.session() as s, s.begin():
            s.info["learning_enabled"] = True
            row = await s.get(MissionRow, mission["id"])
            await mission_event(s, row, "PLAN_REVISED", str(uuid4()), "admin", [])
            await drain(s)
            episodes = list(
                await s.scalars(
                    select(EpisodeRow).where(EpisodeRow.intent_key == "mission:" + row.id)
                )
            )
            assert len(episodes) == 1 and episodes[0].scope_id == scope_id(owner)
        response = await client.post(
            f"/api/v1/missions/{mission['id']}/control",
            headers=headers("approver"),
            json={"operation": "cancel", "expected_mission_version": mission["mission_version"]},
        )
        assert response.status_code == 200, response.text
        async with db.session() as s, s.begin():
            await drain(s)
            episode = await s.get(EpisodeRow, episodes[0].id)
            assert episode.eligible is False
