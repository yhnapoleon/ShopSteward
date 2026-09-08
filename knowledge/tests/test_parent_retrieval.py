import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from shopsteward_knowledge.contracts import Candidate, SearchScope


def payload(ordinal, **changes):
    text = f"Clause {ordinal}"
    return {
        "document_id": "d1",
        "version_id": "v1",
        "generation_id": "g1",
        "chunk_id": f"c{ordinal}",
        "metadata_revision": 1,
        "store_id": "s1",
        "title": "Policy",
        "text": text,
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "original_sha256": "a" * 64,
        "locator": {"kind": "paragraph", "paragraph_range": [ordinal + 1, ordinal + 1]},
        "parent_id": "p1",
        "source_ordinal": ordinal // 3,
        "ordinal": ordinal,
        **changes,
    }


def candidate(data):
    return Candidate.model_validate({k: v for k, v in data.items() if k in Candidate.model_fields})


def scope(**changes):
    return SearchScope(
        principal_ref="backend-user",
        store_id="s1",
        as_of=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        allowed_versions=[{"version_id": "v1", "generation_id": "g1", "metadata_revision": 1}],
    ).model_copy(update=changes)


def test_hit_beyond_fiftieth_chunk_keeps_own_text_hash_locator_and_neighbours():
    from shopsteward_knowledge.retrieval.parent import select_parent_candidates

    hit = candidate(payload(55))
    before = hit.model_dump(mode="json")
    selected = select_parent_candidates(
        hit, payload(55), [payload(i) for i in range(80)], scope(), radius=2, max_chars=6000
    )
    assert [c.chunk_id for c in selected] == ["c53", "c54", "c55", "c56", "c57"]
    assert selected[2].model_dump(mode="json") == before
    assert hit.model_dump(mode="json") == before
    assert selected[0].locator.paragraph_range == (54, 54)
    assert selected[-1].locator.paragraph_range == (58, 58)


@pytest.mark.parametrize(
    "changes",
    [
        {"parent_id": "other-parent"},
        {"generation_id": "other-generation"},
        {"version_id": "v2"},
        {"metadata_revision": 2},
        {"store_id": "other-store"},
        {"original_sha256": "b" * 64},
        {"document_id": "other-document"},
        {"valid_until": "2000-01-01T00:00:00Z"},
    ],
)
def test_parent_expansion_never_crosses_identity_or_validity(changes):
    from shopsteward_knowledge.retrieval.parent import select_parent_candidates

    selected = select_parent_candidates(
        candidate(payload(55)),
        payload(55),
        [payload(54, **changes)],
        scope(),
        radius=2,
        max_chars=6000,
    )
    assert [c.chunk_id for c in selected] == ["c55"]


def test_small_budget_preserves_whole_hit_and_never_relabels_neighbour_text():
    from shopsteward_knowledge.retrieval.parent import select_parent_candidates

    hit = candidate(payload(55))
    neighbours = [payload(54), payload(56)]
    assert select_parent_candidates(
        hit, payload(55), neighbours, scope(), radius=2, max_chars=1
    ) == [hit]
    selected = select_parent_candidates(
        hit, payload(55), neighbours, scope(), radius=2, max_chars=18
    )
    assert [c.chunk_id for c in selected] == ["c54", "c55"]
    assert [c.text for c in selected] == ["Clause 54", "Clause 55"]


def test_missing_parent_tampered_hit_and_expired_scope_fail_closed():
    from shopsteward_knowledge.retrieval.parent import select_parent_candidates

    hit = candidate(payload(55))
    for anchor in (
        payload(55, parent_id=None),
        {**payload(55), "ordinal": -1},
        payload(55, content_sha256="f" * 64),
        payload(54),
    ):
        assert select_parent_candidates(hit, anchor, [], scope(), radius=2, max_chars=6000) == []
    assert (
        select_parent_candidates(
            hit, payload(55), [], scope(allowed_versions=[]), radius=2, max_chars=6000
        )
        == []
    )
    assert (
        select_parent_candidates(
            hit,
            payload(55),
            [],
            scope(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
            radius=2,
            max_chars=6000,
        )
        == []
    )


async def test_parent_expander_rechecks_projection_after_reading_neighbours():
    from types import SimpleNamespace

    from shopsteward_knowledge.contracts import Projection
    from shopsteward_knowledge.retrieval.parent import PGParentExpander

    projection = Projection(
        document_id="d1", version_id="v1", store_id="s1", title="Policy", metadata_revision=1
    )
    record = SimpleNamespace(**projection.model_dump(), payload=projection.model_dump(mode="json"))

    def row(ordinal):
        item = payload(ordinal)
        return (
            record,
            SimpleNamespace(id="g1"),
            SimpleNamespace(
                chunk_id=item["chunk_id"], content_sha256=item["content_sha256"], payload=item
            ),
        )

    class Rows:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

        def one_or_none(self):
            return self.values[0] if self.values else None

    class Session:
        def __init__(self):
            # Last read represents an archive/revision change committed between window reads.
            self.results = iter([[row(55)], [row(54)], [row(56)], []])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, query):
            return Rows(next(self.results))

    assert await PGParentExpander(Session).expand(candidate(payload(55)), scope()) == []


async def test_runtime_factory_wires_parent_and_relation_callbacks_without_network():
    from shopsteward_knowledge.api import create_app
    from shopsteward_knowledge.config import Settings

    app = create_app(
        Settings(
            database_url=None, opensearch_url="http://search.invalid", service_key="test-secret"
        ),
        session_factory=object(),
    )
    async with app.router.lifespan_context(app):
        service = app.state.search_service
        empty_scope = scope(allowed_versions=[])
        assert await service.parent_expander(candidate(payload(55)), empty_scope) == []
        assert await service.relation_loader([], ["APPLIES_TO"], empty_scope, context={}) == []


@pytest.mark.integration
async def test_pg_parent_window_checks_current_projection_and_exact_generation(pg_sessions):
    from sqlalchemy import update

    from shopsteward_knowledge.contracts import Projection
    from shopsteward_knowledge.models import Chunk, IndexGeneration, Original, ProjectionRecord
    from shopsteward_knowledge.retrieval.parent import PGParentExpander

    projection = Projection(
        document_id="d1", version_id="v1", store_id="s1", metadata_revision=1, title="Policy"
    )
    async with pg_sessions.begin() as session:
        session.add(
            Original(
                version_id="v1",
                sha256="a" * 64,
                storage_key="v1.txt",
                size_bytes=10,
                mime="text/plain",
            )
        )
        session.add(
            ProjectionRecord(
                version_id="v1",
                document_id="d1",
                store_id="s1",
                metadata_revision=1,
                payload_hash="a" * 64,
                payload=projection.model_dump(mode="json"),
            )
        )
        await session.flush()
        for gen in ("g1", "other-generation"):
            session.add(
                IndexGeneration(
                    id=gen,
                    version_id="v1",
                    profile_id="lexical-v1",
                    metadata_revision=1,
                    state="READY",
                    chunk_count=80,
                    manifest_hash="b" * 64,
                )
            )
        await session.flush()
        for gen in ("g1", "other-generation"):
            for ordinal in range(80):
                item = payload(ordinal, generation_id=gen, parent_id="p1" if ordinal < 60 else "p2")
                session.add(
                    Chunk(
                        generation_id=gen,
                        chunk_id=item["chunk_id"],
                        version_id="v1",
                        store_id="s1",
                        metadata_revision=1,
                        content_sha256=item["content_sha256"],
                        payload=item,
                    )
                )
    expand = PGParentExpander(pg_sessions).expand
    result = await expand(candidate(payload(55)), scope())
    assert [c.chunk_id for c in result] == ["c53", "c54", "c55", "c56", "c57"]
    assert {c.generation_id for c in result} == {"g1"}
    result = await expand(candidate(payload(59)), scope())
    assert [c.chunk_id for c in result] == ["c57", "c58", "c59"]
    async with pg_sessions.begin() as session:
        await session.execute(
            update(ProjectionRecord)
            .where(ProjectionRecord.version_id == "v1")
            .values(
                metadata_revision=2,
                payload=projection.model_copy(update={"metadata_revision": 2}).model_dump(
                    mode="json"
                ),
            )
        )
    assert await expand(candidate(payload(55)), scope()) == []
