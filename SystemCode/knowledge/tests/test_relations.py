from datetime import UTC, datetime

import pytest


def edges():
    return [
        {
            "id": "E1",
            "subject": "SKU1",
            "predicate": "APPLIES_TO",
            "object": "DOC1",
            "confirmed": True,
            "conditions": {},
            "evidence_chunk_ids": ["C1"],
            "version_id": "V1",
            "generation_id": "G1",
            "metadata_revision": 1,
        },
        {
            "id": "E2",
            "subject": "DOC1",
            "predicate": "REQUIRES_EVIDENCE",
            "object": "PHOTO",
            "confirmed": True,
            "conditions": {"damage": True},
            "evidence_chunk_ids": ["C2"],
            "version_id": "V1",
            "generation_id": "G1",
            "metadata_revision": 1,
        },
        {
            "id": "E3",
            "subject": "DOC1",
            "predicate": "MENTIONS",
            "object": "SKU2",
            "confirmed": False,
            "conditions": {},
            "evidence_chunk_ids": ["C1"],
            "version_id": "V1",
            "generation_id": "G1",
            "metadata_revision": 1,
        },
    ]


def test_condition_missing_does_not_prove_requirement():
    from shopsteward_knowledge.retrieval.relations import bounded_paths

    paths = bounded_paths(
        edges(),
        ["SKU1"],
        ["APPLIES_TO", "REQUIRES_EVIDENCE"],
        as_of=datetime(2026, 9, 7, tzinfo=UTC),
    )
    assert [p["edge_ids"] for p in paths] == [["E1"]]


@pytest.mark.parametrize("value", [1, 1.0, "true"])
def test_boolean_condition_requires_actual_boolean(value):
    from shopsteward_knowledge.retrieval.relations import bounded_paths

    paths = bounded_paths(
        edges(),
        ["SKU1"],
        ["APPLIES_TO", "REQUIRES_EVIDENCE"],
        as_of=datetime(2026, 9, 7, tzinfo=UTC),
        context={"damage": value},
    )
    assert [p["edge_ids"] for p in paths] == [["E1"]]


def test_condition_supported_returns_provenance_without_reverse_inference():
    from shopsteward_knowledge.retrieval.relations import bounded_paths

    paths = bounded_paths(
        edges(),
        ["SKU1"],
        ["APPLIES_TO", "REQUIRES_EVIDENCE"],
        as_of=datetime(2026, 9, 7, tzinfo=UTC),
        context={"damage": True},
    )
    assert [p["edge_ids"] for p in paths] == [["E1"], ["E1", "E2"]]
    assert paths[-1]["evidence_chunk_ids"] == ["C1", "C2"]
    assert (
        bounded_paths(
            edges(), ["PHOTO"], ["REQUIRES_EVIDENCE"], as_of=datetime(2026, 9, 7, tzinfo=UTC)
        )
        == []
    )


def test_cycles_and_unconfirmed_mentions_are_not_traversed():
    from shopsteward_knowledge.retrieval.relations import bounded_paths

    data = edges() + [edges()[0] | {"id": "loop", "subject": "DOC1", "object": "SKU1"}]
    paths = bounded_paths(
        data, ["SKU1"], ["APPLIES_TO", "MENTIONS"], as_of=datetime(2026, 9, 7, tzinfo=UTC)
    )
    assert [p["edge_ids"] for p in paths] == [["E1"]]


async def test_pg_traversal_starts_at_frontier_not_first_scope_wide_edges():
    from types import SimpleNamespace

    from test_search import request

    from shopsteward_knowledge.retrieval.relations import PGRelationRetriever

    useful = edges()[0] | {"valid_from": None, "valid_until": None}
    unrelated = [
        SimpleNamespace(**(useful | {"id": f"A{i}", "subject": "unrelated"})) for i in range(2001)
    ]

    class Rows:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def scalars(self, query):
            compiled = query.whereclause.compile()
            if "knowledge_relations.subject IN" not in str(compiled):
                return Rows(unrelated)
            if ["SKU1"] in list(compiled.params.values()):
                return Rows([SimpleNamespace(**useful)])
            return Rows([])

    paths = await PGRelationRetriever(Session).relation_paths(
        ["SKU1"], ["APPLIES_TO"], request().scope
    )
    assert [path["edge_ids"] for path in paths] == [["E1"]]
