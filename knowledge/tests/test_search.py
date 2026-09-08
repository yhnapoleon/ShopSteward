import hashlib

import pytest

from shopsteward_knowledge.contracts import Candidate, SearchRequest


def candidate(identifier="C1", version="V1"):
    text = "模拟条款：破损须附收货照片。"
    return Candidate(
        document_id="D1",
        version_id=version,
        generation_id="G1",
        chunk_id=identifier,
        metadata_revision=1,
        store_id="S1",
        title="收货条款",
        text=text,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        locator={"kind": "paragraph", "paragraph_range": [1, 1]},
    )


def request():
    return SearchRequest.model_validate(
        {
            "query": "破损",
            "scope": {
                "principal_ref": "P",
                "store_id": "S1",
                "as_of": "2026-09-07T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
                "allowed_versions": [
                    {"version_id": "V1", "generation_id": "G1", "metadata_revision": 1}
                ],
            },
        }
    )


async def test_search_defends_against_out_of_scope_index_result():
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return [candidate(version="V2"), candidate()]

    result = await SearchService(Index()).search(request())
    assert [c.version_id for c in result.candidates] == ["V1"]


async def test_expired_scope_cannot_query_index():
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            pytest.fail("expired scope reached index")

    query = request()
    query.scope.expires_at = query.scope.as_of
    with pytest.raises(ValueError, match="expired"):
        await SearchService(Index()).search(query)


async def test_failed_dense_preserves_available_lexical_evidence():
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return [candidate()]

    class Embedder:
        async def embed(self, *args, **kwargs):
            raise TimeoutError("model unavailable")

    query = request()
    query.profile_id = "hybrid-v1"
    result = await SearchService(
        Index(),
        embedder=Embedder(),
        embedding_profile={"provider": "test", "model": "fixture", "dimensions": 4},
    ).search(query)
    assert len(result.candidates) == 1
    assert result.degraded and "dense_unavailable" in result.warnings
    assert result.candidates[0].scores.get("dense") is None


async def test_no_match_is_not_answered_with_unrelated_defaults():
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return []

    result = await SearchService(Index()).search(request())
    assert result.candidates == []


async def test_final_scope_recheck_respects_remaining_deadline():
    import asyncio
    import time

    from shopsteward_knowledge.retrieval.search import SearchService

    calls = 0

    async def scope_filter(scope):
        nonlocal calls
        calls += 1
        if calls == 2:
            await asyncio.sleep(0.15)
        return scope

    class Index:
        async def search(self, _):
            return [candidate()]

    query = request()
    query.deadline_ms = 30
    started = time.monotonic()
    result = await SearchService(Index(), scope_filter=scope_filter).search(query)
    assert time.monotonic() - started < 0.12
    assert result.candidates == []
    assert result.degraded


async def test_profile_report_is_identical_to_dense_query_identity():
    from shopsteward_knowledge.retrieval.search import SearchService

    observed = []

    class Index:
        async def search(self, _):
            return []

        async def dense(self, request, vector, profile_id):
            observed.append(profile_id)
            return [candidate()]

    class Embedder:
        async def embed(self, *args, **kwargs):
            return [[1, 0]]

    query = request()
    query.profile_id = "hybrid-v1"
    result = await SearchService(
        Index(),
        embedder=Embedder(),
        embedding_profile={"provider": "test", "model": "fixture", "dimensions": 2},
    ).search(query)
    assert observed == [result.embedding_profile]


async def test_relations_supply_evidence_with_typed_paths_and_conditions():
    from test_relations import edges

    from shopsteward_knowledge.retrieval.relations import bounded_paths
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return []

    async def relations(seeds, predicates, scope, **kwargs):
        return bounded_paths(edges(), seeds, predicates, as_of=scope.as_of, **kwargs)

    async def evidence(scope, ids):
        return [candidate(identifier=i) for i in ids]

    query = request().model_copy(
        update={"entity_ids": ["SKU1"], "relation_context": {"damage": True}}
    )
    result = await SearchService(
        Index(), relation_loader=relations, evidence_loader=evidence
    ).search(query)
    assert {c.chunk_id for c in result.candidates} == {"C1", "C2"}
    assert any(p.edge_ids == ["E1", "E2"] for c in result.candidates for p in c.relation_paths)
    assert all("relations" in c.retrieval_channels for c in result.candidates)


async def test_declared_supply_and_document_lookup_predicates_are_retrievable():
    from test_relations import edges

    from shopsteward_knowledge.retrieval.relations import bounded_paths
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return []

    data = edges()[:2]
    data[0].update(predicate="SUPPLIES", subject="SUP1", object="SKU1")
    data[1].update(predicate="HAS_APPLICABLE_DOCUMENT", subject="SKU1", object="DOC1")

    async def relations(seeds, predicates, scope, **kwargs):
        return bounded_paths(data, seeds, predicates, as_of=scope.as_of, **kwargs)

    async def evidence(scope, ids):
        return [candidate(identifier=i) for i in ids]

    service = SearchService(Index(), relation_loader=relations, evidence_loader=evidence)
    query = request().model_copy(
        update={"entity_ids": ["SUP1"], "relation_context": {"damage": True}}
    )
    result = await service.search(query)
    assert {c.chunk_id for c in result.candidates} == {"C1", "C2"}
    reversed_result = await service.search(query.model_copy(update={"entity_ids": ["DOC1"]}))
    assert reversed_result.candidates == []


async def test_final_scope_drops_path_if_one_edge_loses_authority():
    from test_relations import edges

    from shopsteward_knowledge.retrieval.relations import bounded_paths
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return [candidate()]

    calls = 0

    async def scope_filter(scope):
        nonlocal calls
        calls += 1
        return (
            scope
            if calls == 1
            else scope.model_copy(update={"allowed_versions": scope.allowed_versions[:1]})
        )

    async def relations(seeds, predicates, scope, **kwargs):
        data = edges()
        data[1]["version_id"] = "V2"
        return bounded_paths(data, seeds, predicates, as_of=scope.as_of, **kwargs)

    async def evidence(scope, ids):
        return [candidate(identifier=i, version="V2" if i == "C2" else "V1") for i in ids]

    query = request().model_copy(
        update={"entity_ids": ["SKU1"], "relation_context": {"damage": True}}
    )
    query.scope.allowed_versions.append(
        query.scope.allowed_versions[0].model_copy(update={"version_id": "V2"})
    )
    result = await SearchService(
        Index(), scope_filter=scope_filter, relation_loader=relations, evidence_loader=evidence
    ).search(query)
    assert result.candidates
    assert all(p.edge_ids == ["E1"] for c in result.candidates for p in c.relation_paths)
    assert any(c.relation_paths for c in result.candidates)


async def test_parent_neighbours_keep_individual_locations_and_scope():
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return [candidate()]

    async def expand(hit, scope):
        return [candidate("C2"), candidate("C3", version="V2")]

    result = await SearchService(Index(), parent_expander=expand).search(request())
    assert [c.chunk_id for c in result.candidates] == ["C1", "C2"]
    assert result.candidates[0].context_chunk_ids == ["C2"]
    assert result.candidates[1].text == candidate("C2").text


@pytest.mark.parametrize("fail", [False, True])
async def test_optional_rerank_uses_authorized_rrf_pool_and_preserves_fallback(fail):
    from shopsteward_knowledge.retrieval.search import SearchService

    class Index:
        async def search(self, _):
            return [candidate("C1"), candidate("C2"), candidate("outside", version="V2")]

    class Rerank:
        async def rerank(self, query, values, **kwargs):
            assert [c.chunk_id for c in values] == ["C1", "C2"]
            if fail:
                raise TimeoutError()
            return [c.model_copy(update={"rerank_score": 0.9}) for c in reversed(values)]

    result = await SearchService(Index(), reranker=Rerank()).search(
        request().model_copy(update={"profile_id": "hybrid-v1"})
    )
    assert [c.chunk_id for c in result.candidates] == (["C1", "C2"] if fail else ["C2", "C1"])
    assert ("rerank_timeout" in result.warnings) is fail
