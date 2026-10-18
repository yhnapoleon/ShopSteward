from datetime import UTC, datetime

import pytest
from test_missions import fresh_seed
from test_operations import initialize

pytestmark = pytest.mark.integration


async def enable(session, scope):
    from app.learning.repository import policy

    row = await policy(session, scope, lock=True)
    row.mode, row.version, row.enabled_at = "suggest", 1, datetime.now(UTC)
    await session.flush()


def event(identifier="case"):
    from app.learning.schemas import LearningEvent

    now = datetime.now(UTC)
    return LearningEvent(
        source_kind="case",
        source_id=identifier,
        source_version=1,
        event_type="OPTIONS_READY",
        intent_key="case:" + identifier,
        task_family="supply_delay_recovery",
        observed_at=now,
        available_at=now,
    )


async def test_outbox_transaction_rollback_dedupe_and_scope(db):
    from app.learning.collector import consume
    from app.learning.models import EpisodeRow, LearningOutbox
    from app.learning.outbox import append
    from app.learning.schemas import LearningScope

    seed = fresh_seed()
    await initialize(db, seed)
    scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
    async with db.session() as session, session.begin():
        await enable(session, scope)
    e = event()
    async with db.session() as session, session.begin():
        first = await append(session, scope=scope, event=e)
        assert first == await append(session, scope=scope, event=e)
    async with db.session() as session, session.begin():
        ep = await consume(session, event_id=first)
        assert ep == await consume(session, event_id=first)
        row = await session.get(EpisodeRow, ep)
        assert row.eligible and len(row.evidence_ids) == 1 and row.outcome_revision == 1
    async with db.session() as session:
        await session.begin()
        rolled = await append(session, scope=scope, event=event("rolled"))
        await session.rollback()
    async with db.session() as session:
        assert await session.get(LearningOutbox, rolled) is None


async def test_default_off_collects_nothing(db):
    from app.learning.outbox import append
    from app.learning.schemas import LearningScope

    seed = fresh_seed()
    await initialize(db, seed)
    async with db.session() as session, session.begin():
        assert (
            await append(
                session,
                scope=LearningScope(principal_id="admin", store_id=seed["store_id"]),
                event=event(),
            )
            is None
        )


async def test_revision_is_immutable_and_forbids_cross_scope_evidence(db):
    from sqlalchemy.exc import DBAPIError

    from app.core.errors import AppError
    from app.learning.models import AssetRevisionRow
    from app.learning.outbox import append
    from app.learning.repository import create_candidate
    from app.learning.schemas import LearningScope

    seed = fresh_seed()
    await initialize(db, seed)
    scope = LearningScope(principal_id="admin", store_id=seed["store_id"])
    other = scope.model_copy(update={"principal_id": "other"})
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
    async with db.session() as session, session.begin():
        await enable(session, scope)
        evidence = await append(session, scope=scope, event=event())
        rev = await create_candidate(session, scope=scope, spec=spec, evidence=[evidence])
        rid = (rev.asset_id, rev.revision)
    async with db.session() as session, session.begin():
        await enable(session, other)
        with pytest.raises(AppError, match="Evidence"):
            await create_candidate(session, scope=other, spec=spec, evidence=[evidence])
    with pytest.raises(DBAPIError, match="immutable"):
        async with db.session() as session, session.begin():
            rev = await session.get(AssetRevisionRow, rid)
            rev.spec = rev.spec | {"title": "Mutated"}
            await session.flush()
