import json

import httpx
import pytest


async def test_embedding_reorders_indexes_and_applies_input_instruction():
    from shopsteward_knowledge.contracts import EmbeddingProfile
    from shopsteward_knowledge.providers.embedding import HttpEmbedding

    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = HttpEmbedding(client, "https://model.example/v1/embeddings", "test-key")
        profile = EmbeddingProfile(
            provider="test",
            model="fixture",
            dimensions=2,
            query_instruction="Query: ",
            document_instruction="Doc: ",
        )
        result = await embedder.embed(
            ["甲", "乙"], input_type="query", profile=profile.model_dump(), deadline_ms=500
        )
    assert result == [[1, 0], [0, 1]]
    assert seen[0]["input"] == ["Query: 甲", "Query: 乙"]


async def test_embedding_does_not_accept_wrong_dimensions():
    from shopsteward_knowledge.providers.embedding import HttpEmbedding

    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1]}]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        embedder = HttpEmbedding(client, "https://model.example/v1/embeddings", "test-key")
        with pytest.raises(ValueError, match="dimensions"):
            await embedder.embed(
                ["甲"],
                input_type="document",
                profile={"provider": "test", "model": "fixture", "dimensions": 2},
                deadline_ms=500,
            )


async def test_empty_scope_performs_no_index_io():
    from shopsteward_knowledge.contracts import SearchRequest
    from shopsteward_knowledge.retrieval.opensearch import OpenSearchIndex

    def handler(_):
        pytest.fail("empty scope issued network request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        index = OpenSearchIndex(client, "http://search.example", "test-knowledge")
        request = SearchRequest.model_validate(
            {
                "query": "冷链",
                "scope": {
                    "principal_ref": "P",
                    "store_id": "S",
                    "as_of": "2026-09-07T00:00:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                    "allowed_versions": [],
                },
            }
        )
        assert await index.search(request) == []


async def test_ready_verification_rejects_wrong_searchable_candidate():
    from test_search import candidate

    from shopsteward_knowledge.retrieval.opensearch import OpenSearchIndex, storage_id

    expected = candidate().model_dump(mode="json")
    changed = dict(expected, title="wrong revision title")

    def handler(request):
        if request.url.path.endswith("/_count"):
            return httpx.Response(200, json={"count": 1})
        return httpx.Response(
            200,
            json={
                "hits": {
                    "hits": [{"_id": storage_id("G1", "C1"), "_source": {"candidate": changed}}]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        index = OpenSearchIndex(client, "http://search.example", "test-knowledge")
        assert await index.verify_generation("G1", [expected]) is False


@pytest.mark.parametrize("fault", [{"timed_out": True}, {"_shards": {"failed": 1}}])
async def test_partial_search_is_reported_as_channel_failure(fault):
    from test_search import request

    from shopsteward_knowledge.retrieval.opensearch import OpenSearchIndex
    from shopsteward_knowledge.retrieval.search import SearchService

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"hits": {"hits": []}, **fault})
        )
    ) as client:
        result = await SearchService(
            OpenSearchIndex(client, "http://search.example", "test-k")
        ).search(request())
    assert result.degraded
    assert "lexical_unavailable" in result.warnings


async def test_equal_score_hits_have_stable_channel_order():
    from test_search import candidate, request

    from shopsteward_knowledge.retrieval.opensearch import OpenSearchIndex

    body = {
        "hits": {
            "hits": [
                {"_score": 1, "_source": {"candidate": candidate("B").model_dump(mode="json")}},
                {"_score": 1, "_source": {"candidate": candidate("A").model_dump(mode="json")}},
            ]
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as client:
        values = await OpenSearchIndex(client, "http://search.example", "test-k").search(request())
    assert [c.chunk_id for c in values] == ["A", "B"]


async def test_many_generations_share_index_but_never_overwrite_same_chunk_id():
    from test_search import candidate

    from shopsteward_knowledge.retrieval.opensearch import OpenSearchIndex

    created, ids = set(), set()

    def handler(request):
        if request.method == "PUT":
            created.add(request.url.path)
        if request.url.path == "/_bulk":
            lines = request.content.decode().splitlines()
            ids.add(json.loads(lines[0])["index"]["_id"])
        return httpx.Response(200, json={"errors": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        index = OpenSearchIndex(client, "http://search.example", "test-k")
        for i in range(20):
            c = candidate().model_copy(update={"generation_id": f"G{i}"})
            await index.upsert(c.generation_id, [c.model_dump(mode="json")])
    assert len(created) == 1
    assert len(ids) == 20


async def test_generation_delete_is_scoped_and_cannot_delete_shared_index():
    from shopsteward_knowledge.retrieval.opensearch import OpenSearchIndex

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"deleted": 1, "failures": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await OpenSearchIndex(client, "http://search.example", "test-k").delete_generation("G1")
    assert seen[0].method == "POST" and seen[0].url.path.endswith("/_delete_by_query")
    assert json.loads(seen[0].content)["query"] == {"term": {"generation_id": "G1"}}


async def test_ready_verification_counts_only_requested_generation_and_matches_payload():
    from test_search import candidate

    from shopsteward_knowledge.retrieval.opensearch import OpenSearchIndex, storage_id

    expected = candidate().model_dump(mode="json")

    def handler(request):
        if request.url.path.endswith("/_count"):
            assert json.loads(request.content)["query"] == {"term": {"generation_id": "G1"}}
            return httpx.Response(200, json={"count": 1})
        return httpx.Response(
            200,
            json={
                "hits": {
                    "hits": [{"_id": storage_id("G1", "C1"), "_source": {"candidate": expected}}]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (
            await OpenSearchIndex(client, "http://search.example", "test-k").verify_generation(
                "G1", [expected]
            )
            is True
        )


def test_large_scope_uses_one_terms_filter_with_revision_identity():
    from test_search import request

    from shopsteward_knowledge.retrieval.opensearch import scope_filters

    query = request()
    query.scope.allowed_versions = [
        query.scope.allowed_versions[0].model_copy(update={"generation_id": f"G{i}"})
        for i in range(1500)
    ]
    values = scope_filters(query)[1]["terms"]["authority_key"]
    assert len(set(values)) == 1500
    query.scope.allowed_versions[0].metadata_revision = 2
    assert scope_filters(query)[1]["terms"]["authority_key"][0] != values[0]
