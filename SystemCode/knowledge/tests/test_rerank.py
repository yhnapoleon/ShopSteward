import json

import httpx
import pytest


async def test_rerank_preserves_candidate_text_identity_and_accepts_only_scores():
    from test_search import candidate

    from shopsteward_knowledge.providers.rerank import HttpRerank

    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                ]
            },
        )

    values = [candidate("C1"), candidate("C2")]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await HttpRerank(
            client, "https://model.example/rerank", "test-key", "fixture-model"
        ).rerank("query", values, deadline_ms=500)
    assert [c.chunk_id for c in result] == ["C2", "C1"]
    assert result[0].text == values[1].text
    assert result[0].rerank_score == 0.9
    assert values[1].rerank_score is None
    assert seen[0]["documents"] == [c.text for c in values]


@pytest.mark.parametrize(
    "results",
    [
        [{"index": 2, "relevance_score": 0.9}],
        [{"index": 0, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.8}],
        [{"index": True, "relevance_score": 0.9}],
    ],
)
async def test_rerank_invalid_remote_index_cannot_select_unprovided_evidence(results):
    from test_search import candidate

    from shopsteward_knowledge.providers.rerank import HttpRerank

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": results}))
    ) as client:
        with pytest.raises(ValueError):
            await HttpRerank(client, "https://model.example/rerank", "test-key", "fixture").rerank(
                "query", [candidate()], deadline_ms=500
            )
