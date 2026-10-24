from uuid import uuid4

import pytest
from test_learning_storage import enable, event
from test_missions import environment, headers

pytestmark = pytest.mark.integration


async def test_learning_routes_default_off_opt_in_and_revision_conflict(db):
    async with environment(db) as (seed, client):
        client._transport.app.state.settings.learning_enabled = True
        path = f"/api/v1/stores/{seed['store_id']}/learning"
        first = await client.get(path, headers=headers())
        assert first.status_code == 200, first.text
        assert first.json()["policy"]["mode"] == "off"
        key = str(uuid4())
        args = {"expected_version": 0, "mode": "suggest"}
        a = await client.patch(path + "/policy", json=args, headers=headers(key=key))
        b = await client.patch(path + "/policy", json=args, headers=headers(key=key))
        assert a.status_code == 200, a.text
        assert a.json() == b.json()
        stale = await client.patch(
            path + "/policy", json={"expected_version": 0, "mode": "off"}, headers=headers()
        )
        assert stale.status_code == 409
        viewer = await client.patch(
            path + "/policy", json={"expected_version": 1, "mode": "off"}, headers=headers("viewer")
        )
        assert viewer.status_code == 403


async def test_candidate_without_independent_quality_cannot_activate(db):
    from app.core.errors import AppError
    from app.learning.lifecycle import transition
    from app.learning.outbox import append
    from app.learning.repository import create_candidate
    from app.learning.schemas import LearningScope, Transition

    async with environment(db) as (seed, client):
        scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
        async with db.session() as session, session.begin():
            await enable(session, scope)
            source = await append(session, scope=scope, event=event())
            spec = dict(
                title="Compare",
                task_family="supply_delay_recovery",
                summary="Compare inbound",
                inputs=["case_id"],
                preconditions=["current_case"],
                exclusions=["unknown_execution"],
                required_tools=["analyze_recovery_case"],
                procedure=["Read", "Compare"],
                outputs=["comparison"],
                exceptions=["Ask ETA"],
            )
            revision = await create_candidate(session, scope=scope, spec=spec, evidence=[source])
            with pytest.raises(AppError, match="evaluation"):
                await transition(
                    session,
                    scope=scope,
                    asset_id=revision.asset_id,
                    body=Transition(expected_version=1, revision=1, action="activate"),
                    key=str(uuid4()),
                    settings=client._transport.app.state.settings,
                    principal=client._transport.app.state.settings.auth_tokens[0],
                )


async def test_case_event_produces_one_episode_across_revisions(db):
    from sqlalchemy import select
    from test_operations_cases import analyze, recovery_case

    from app.learning.collector import drain
    from app.learning.models import EpisodeRow

    async with environment(db) as (seed, client):
        app = client._transport.app
        app.state.settings.learning_enabled = True
        app.state.db.learning_enabled = True
        root = f"/api/v1/stores/{seed['store_id']}/learning"
        response = await client.patch(
            root + "/policy", json={"expected_version": 0, "mode": "suggest"}, headers=headers()
        )
        assert response.status_code == 200, response.text
        case = await analyze(client, await recovery_case(db, seed, client))
        async with db.session() as session, session.begin():
            await drain(session)
            rows = list(
                await session.scalars(
                    select(EpisodeRow).where(EpisodeRow.intent_key == "case:" + case["id"])
                )
            )
            assert len(rows) == 1 and rows[0].eligible
            assert len(rows[0].evidence_ids) >= 2
        view = await client.get(root, headers=headers())
        assert view.json()["progress"]["eligible_episodes"] == 1
