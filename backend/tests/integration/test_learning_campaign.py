from datetime import UTC, datetime

import pytest
from test_learning_admission import candidate
from test_learning_storage import enable
from test_missions import environment

pytestmark = pytest.mark.integration


async def test_frozen_campaign_registers_verified_result_but_never_autoactivates(db):
    from app.learning.campaign import complete, prepare
    from app.learning.models import AssetRow
    from app.learning.schemas import LearningScope

    async with environment(db) as (seed, client):
        settings = client._transport.app.state.settings
        principal = next(p for p in settings.auth_tokens if p.principal_id == "admin")
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            rev = await candidate(s, scope)
            cases = [
                {
                    "id": f"test-{i}",
                    "suite": ["normal", "negative", "boundary", "recovery", "composition"][i % 5],
                    "source_ids": [],
                    "origin": "locked_test",
                    "input_hash": f"input-{i}",
                }
                for i in range(200)
            ]
            manifest = await prepare(
                s,
                scope=scope,
                asset_id=rev.asset_id,
                revision=1,
                settings=settings,
                principal=principal,
                cases=cases,
                target="tool_calls_reduction",
            )
            results = [
                {
                    **c,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "artifact_ref": "test-artifact",
                    "baseline": {"success": True, "tool_calls": 10, "corrections": 0},
                    "candidate": {"success": True, "tool_calls": 8, "corrections": 0},
                }
                for c in cases
            ]
            reviews = [
                {
                    "reviewer": name,
                    "dimensions": {
                        f"S{i}": {
                            "score": 3,
                            "reason": "Synthetic test fixture",
                            "evidence_refs": ["test-artifact"],
                        }
                        for i in range(1, 7)
                    },
                }
                for name in ["A", "B"]
            ]
            result = await complete(
                s,
                scope=scope,
                campaign_id=manifest["campaign_id"],
                settings=settings,
                principal=principal,
                results=results,
                reviews=reviews,
                checks={
                    f"H{i}": {"status": "pass", "evidence_refs": ["test-artifact"]}
                    for i in range(1, 7)
                },
                verified_artifacts={"test-artifact": "checksum"},
            )
            assert result["decision"]["status"] == "pass", result
            assert (await s.get(AssetRow, rev.asset_id)).active_revision is None
            with pytest.raises(ValueError, match="fresh"):
                await complete(
                    s,
                    scope=scope,
                    campaign_id=manifest["campaign_id"],
                    settings=settings,
                    principal=principal,
                    results=results,
                    reviews=reviews,
                    checks={},
                    verified_artifacts={},
                )


async def test_only_confirmed_execution_feedback_contributes_to_drift(db):
    from app.core.errors import AppError
    from app.learning.models import ApplicationRow, AssetRow
    from app.learning.monitoring import feedback
    from app.learning.repository import scope_id
    from app.learning.schemas import ApplicationFeedback, LearningScope

    async with environment(db) as (seed, client):
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as s, s.begin():
            await enable(s, scope)
            rev = await candidate(s, scope)
            asset = await s.get(AssetRow, rev.asset_id)
            asset.active_revision = 1
            rev.status = "ACTIVE"
            for i in range(10):
                s.add(
                    ApplicationRow(
                        id=f"{asset.id[:40]}-{i}",
                        scope_id=scope_id(scope),
                        asset_id=asset.id,
                        revision=1,
                        run_id=f"test-run-{i}",
                        stage="selected",
                        outcome={"traces": [{"invocation_id": "trace"}], "status": "unknown"},
                    )
                )
            await s.flush()
            args = ApplicationFeedback(
                expected_feedback_version=0,
                executed=True,
                status="fail",
                attribution="unresolved",
                evidence_ids=["invented"],
            )
            with pytest.raises(AppError, match="evidence"):
                await feedback(s, scope=scope, application_id=f"{asset.id[:40]}-0", body=args)
            for i in range(10):
                await feedback(
                    s,
                    scope=scope,
                    application_id=f"{asset.id[:40]}-{i}",
                    body=args.model_copy(
                        update={"evidence_ids": ["trace"], "status": "fail" if i < 3 else "pass"}
                    ),
                )
            assert asset.active_revision is None
            assert rev.status == "SUSPENDED"
