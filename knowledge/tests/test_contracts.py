import hashlib

import pytest
from pydantic import ValidationError


def scope_data():
    return {
        "principal_ref": "P1",
        "store_id": "S1",
        "as_of": "2026-09-07T00:00:00Z",
        "expires_at": "2026-09-07T00:00:30Z",
        "allowed_versions": [],
    }


def test_empty_scope_never_means_all():
    from shopsteward_knowledge.contracts import SearchScope

    assert SearchScope.model_validate(scope_data()).allowed_versions == []


def test_unknown_scope_fields_rejected():
    from shopsteward_knowledge.contracts import SearchScope

    with pytest.raises(ValidationError):
        SearchScope.model_validate(scope_data() | {"all_stores": True})


def test_naive_scope_time_rejected():
    from shopsteward_knowledge.contracts import SearchScope

    with pytest.raises(ValidationError):
        SearchScope.model_validate(scope_data() | {"as_of": "2026-09-07T00:00:00"})


def test_request_budget_is_bounded():
    from shopsteward_knowledge.contracts import SearchRequest

    with pytest.raises(ValidationError):
        SearchRequest(query="条款", scope=scope_data(), deadline_ms=9000)


def test_candidate_requires_reproducible_text_hash_and_locator():
    from shopsteward_knowledge.contracts import Candidate

    text = "模拟条款：破损应在收货时记录。"
    data = dict(
        document_id="D1",
        version_id="V1",
        generation_id="G1",
        chunk_id="C1",
        metadata_revision=1,
        text=text,
        title="收货",
        store_id="S1",
        locator={"kind": "paragraph", "paragraph_range": [1, 1]},
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    assert Candidate.model_validate(data).text == text
    with pytest.raises(ValidationError):
        Candidate.model_validate(data | {"content_sha256": "0" * 64})
    with pytest.raises(ValidationError):
        Candidate.model_validate(data | {"locator": {"kind": "page"}})


def test_profiles_cannot_claim_nonfinite_vectors():
    from shopsteward_knowledge.contracts import EmbeddingProfile, validate_vectors

    profile = EmbeddingProfile(provider="test", model="fixture", dimensions=4)
    with pytest.raises(ValueError):
        validate_vectors([[0.0, float("nan"), 0.0, 1.0]], 1, profile.dimensions)
    with pytest.raises(ValueError):
        validate_vectors([[1.0, 0.0]], 1, profile.dimensions)
