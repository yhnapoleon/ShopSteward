from uuid import uuid4

import pytest
from sqlalchemy import select
from test_learning_storage import enable, event
from test_missions import environment, headers

pytestmark = pytest.mark.integration


async def candidate(session, scope):
    from app.learning.outbox import append
    from app.learning.repository import create_candidate

    source = await append(session, scope=scope, event=event(str(uuid4())))
    spec = dict(
        title="Read before comparison",
        task_family="replenishment",
        summary="Read current plan",
        inputs=["mission"],
        preconditions=["current_mission"],
        exclusions=["unknown_execution"],
        required_tools=["get_plan"],
        procedure=["Read current plan"],
        outputs=["comparison"],
        exceptions=["Ask"],
    )
    return await create_candidate(session, scope=scope, spec=spec, evidence=[source])


async def test_static_evaluation_is_idempotent_and_unknown_cannot_activate(db):
    from app.learning.schemas import LearningScope

    async with environment(db) as (seed, client):
        app = client._transport.app
        app.state.settings.learning_enabled = True
        scope = LearningScope(principal_id="operator", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            rev = await candidate(s, scope)
            aid = rev.asset_id
        root = f"/api/v1/stores/{seed['store_id']}/learning/assets/{aid}"
        key = str(uuid4())
        args = {"expected_version": 1, "revision": 1}
        a = await client.post(root + "/evaluations", json=args, headers=headers(key=key))
        assert a.status_code == 200, a.text
        b = await client.post(root + "/evaluations", json=args, headers=headers(key=key))
        assert a.json() == b.json()
        assert a.json()["decision"]["status"] == "insufficient_evidence"
        assert a.json()["report"]["checks"]["H1"] == "pass"
        assert a.json()["report"]["scores"]["S5"] is None
        rejected = await client.post(
            root + "/transitions",
            headers=headers(),
            json={
                "expected_version": 2,
                "revision": 1,
                "action": "activate",
                "evaluation_id": a.json()["id"],
            },
        )
        assert rejected.status_code == 409


async def test_admission_revalidates_report_and_preferences(db):
    from app.learning.capture import explicit_memory_change
    from app.learning.evaluation import static_evaluate
    from app.learning.lifecycle import transition
    from app.learning.models import ApplicationRow, AssetRow, EvaluationRow
    from app.learning.retrieval import retrieve
    from app.learning.schemas import LearningScope, Transition

    async with environment(db) as (seed, client):
        settings = client._transport.app.state.settings
        settings.learning_enabled = True
        principal = next(p for p in settings.auth_tokens if p.principal_id == "admin")
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            rev = await candidate(s, scope)
            asset = await s.get(AssetRow, rev.asset_id)
            result = await static_evaluate(
                s, scope=scope, asset=asset, revision=rev, settings=settings, principal=principal
            )
            await s.flush()
            evaluation = await s.get(EvaluationRow, result["id"])
            # Synthetic trusted report is only a test fixture, never a shipped evaluation result.
            evidence = ["independent-test-report"]
            evaluation.report = {
                **evaluation.report,
                "checks": {f"H{i}": "pass" for i in range(1, 7)},
                "scores": {f"S{i}": 3 for i in range(1, 7)},
                "measured": True,
                "reviewer_kind": "human_reviewed",
                "reviewed_by": ["test-reviewer-a", "test-reviewer-b"],
                "independent_cases": 200,
                "suite_kinds": ["normal", "negative", "boundary", "recovery", "composition"],
                "evidence_refs": evidence,
                "quality_delta_lower": -0.01,
                "improvement": 0.2,
                "dimension_reviews": {
                    f"S{i}": {"score": 3, "evidence_refs": evidence, "reason": "Test only"}
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
            args = dict(
                scope=scope,
                family="replenishment",
                facts={"current_mission": True, "unknown_execution": False},
                settings=settings,
                principal=principal,
                run_id="test-run",
            )
            assert len(await retrieve(s, **args)) == 1
            assert len(await retrieve(s, **args)) == 1
            assert (
                len(
                    list(
                        await s.scalars(
                            select(ApplicationRow).where(ApplicationRow.asset_id == asset.id)
                        )
                    )
                )
                == 1
            )
            s.info["learning_enabled"] = True
            await explicit_memory_change(s, "admin", scope.store_id)
            assert await retrieve(s, **args) == []
            assert asset.active_revision is None


async def test_forgetting_blocks_renamed_candidate_from_same_sources(db):
    from app.core.errors import AppError
    from app.learning.lifecycle import forget
    from app.learning.repository import create_candidate
    from app.learning.schemas import ForgetRequest, LearningScope

    async with environment(db) as (seed, client):
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            rev = await candidate(s, scope)
            await forget(
                s,
                scope=scope,
                body=ForgetRequest(expected_version=1, asset_id=rev.asset_id),
                key=str(uuid4()),
            )
            with pytest.raises(AppError, match="disabled"):
                await create_candidate(
                    s, scope=scope, spec=rev.spec | {"title": "Renamed"}, evidence=rev.evidence_ids
                )


async def test_late_ordinary_events_do_not_erase_matured_receipt(db):
    from app.learning.collector import consume
    from app.learning.models import EpisodeRow, OutcomeRow
    from app.learning.outbox import append
    from app.learning.schemas import LearningScope

    async with environment(db) as (seed, client):
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            first = event("receipt").model_copy(
                update={
                    "event_type": "EXECUTION_OBSERVED",
                    "payload": {
                        "execution_status": "SUCCEEDED",
                        "business_status": "matured",
                        "metrics": {"received_qty": 5},
                    },
                }
            )
            eid = await consume(s, event_id=await append(s, scope=scope, event=first))
            later = event("receipt").model_copy(
                update={"source_version": 2, "event_type": "PLAN_READY"}
            )
            await consume(s, event_id=await append(s, scope=scope, event=later))
            episode = await s.get(EpisodeRow, eid)
            latest = await s.get(OutcomeRow, (eid, episode.outcome_revision))
            assert latest.document["business_status"] == "matured"
            assert latest.document["metrics"] == {"received_qty": 5}
