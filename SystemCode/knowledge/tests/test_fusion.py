import pytest


def test_rrf_keeps_rank_origin_and_duplicate_channel_ids():
    from shopsteward_knowledge.retrieval.fusion import rrf

    scores = dict(rrf([["A", "B", "B"], ["B"]], c=60))
    assert scores["A"] == 1 / 61
    assert scores["B"] == 1 / 62 + 1 / 61


def test_rrf_ties_are_stable_and_negative_constant_rejected():
    from shopsteward_knowledge.retrieval.fusion import rrf

    assert [key for key, _ in rrf([["B"], ["A"]])] == ["A", "B"]
    with pytest.raises(ValueError):
        rrf([["A"]], c=-1)


def test_lexical_query_with_filters_requires_text_match():
    from shopsteward_knowledge.contracts import SearchRequest
    from shopsteward_knowledge.retrieval.opensearch import build_query

    request = SearchRequest.model_validate(
        {
            "query": "冷链",
            "scope": {
                "principal_ref": "P",
                "store_id": "S",
                "as_of": "2026-09-07T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
                "allowed_versions": [
                    {"version_id": "V", "generation_id": "G", "metadata_revision": 1}
                ],
            },
        }
    )
    query = build_query(request)["query"]["bool"]
    assert query["minimum_should_match"] == 1
    assert query["should"] == [{"match": {"text": "冷链"}}]


def test_empty_scope_query_matches_nothing():
    from shopsteward_knowledge.contracts import SearchRequest
    from shopsteward_knowledge.retrieval.opensearch import build_query

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
    assert build_query(request)["query"] == {"match_none": {}}
