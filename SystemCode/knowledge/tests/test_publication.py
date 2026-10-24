import hashlib

import pytest

from shopsteward_knowledge.contracts import OriginalRef
from shopsteward_knowledge.publication import (
    manifest_hash,
    projection_decision,
    retry_delay,
    verify_original,
)


def test_delayed_projection_cannot_restore_archived_metadata():
    assert (
        projection_decision(
            {"metadata_revision": 3, "payload_hash": "archive"},
            {"metadata_revision": 2, "payload_hash": "active"},
        )
        == "stale"
    )


def test_equal_revision_is_replay_only_for_identical_payload():
    prior = {"metadata_revision": 3, "payload_hash": "archive"}
    assert projection_decision(prior, prior) == "replay"
    with pytest.raises(ValueError):
        projection_decision(prior, {**prior, "payload_hash": "active"})
    assert projection_decision(None, prior) == "apply"
    assert projection_decision(prior, {**prior, "metadata_revision": 4}) == "apply"


def test_original_verification_rejects_hash_and_size_mismatch():
    ref = OriginalRef(
        version_id="v1",
        sha256=hashlib.sha256(b"abc").hexdigest(),
        size_bytes=3,
        mime="text/plain",
        storage_key="originals/v1",
    )
    verify_original(ref, b"abc")
    for content in (b"abd", b"abc\n"):
        with pytest.raises(ValueError):
            verify_original(ref, content)


def test_manifest_binds_every_field_and_is_order_independent():
    chunks = [{"chunk_id": "a", "text": "first"}, {"chunk_id": "b", "text": "second"}]
    assert manifest_hash(chunks) == manifest_hash(chunks[::-1])
    assert manifest_hash(chunks) != manifest_hash([chunks[0], {**chunks[1], "text": "changed"}])
    with pytest.raises(ValueError):
        manifest_hash([])
    with pytest.raises(ValueError):
        manifest_hash([chunks[0], chunks[0]])


def test_retry_delay_is_bounded_and_honors_retry_after():
    assert [retry_delay(i) for i in (1, 2, 3, 4, 8)] == [1, 2, 4, 8, 60]
    assert retry_delay(1, 20) == 20
    assert retry_delay(1, 10000) == 60


def test_real_parser_chunk_payload_preserves_original_provenance_and_parent():
    from types import SimpleNamespace

    from shopsteward_knowledge.contracts import IngestionRequest
    from shopsteward_knowledge.parsing import parse_original
    from shopsteward_knowledge.parsing.chunking import chunk_blocks
    from shopsteward_knowledge.worker import candidate_chunks

    content = b"Refunds require a receipt."
    request = IngestionRequest.model_validate(
        {
            "original": {
                "version_id": "v1",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "storage_key": "v1.txt",
                "mime": "text/plain",
            },
            "projection": {
                "version_id": "v1",
                "document_id": "d1",
                "store_id": "s1",
                "title": "Refund policy",
                "metadata_revision": 3,
                "provenance": {"synthetic": True, "source_url": "https://example.org/policy"},
            },
        }
    )
    claim = SimpleNamespace(
        projection=request.projection.model_dump(mode="json"),
        request=request.model_dump(mode="json"),
        generation_id="g1",
    )
    parsed = parse_original(request.original, content)
    chunks = candidate_chunks(claim, parsed, chunk_blocks(parsed.blocks, {"id": "lexical-v1"}))
    item = chunks[0]
    assert item["text"] == content.decode()
    assert item["metadata_revision"] == 3 and item["generation_id"] == "g1"
    assert item["synthetic"] is True and item["source_url"] == "https://example.org/policy"
    assert item["parent_id"] and item["ordinal"] == 0
    assert item["locator"]["paragraph_range"] == [1, 1]
    parsed.status = "PARTIAL"
    parsed.warnings = ["UNPARSED_CHART"]
    raw_chunks = chunk_blocks(parsed.blocks, {"id": "lexical-v1"})
    assert candidate_chunks(claim, parsed, raw_chunks)[0]["ocr_status"] == "NOT_REQUIRED"
    parsed.warnings = ["PDF_NO_TEXT_LAYER:2:OCR_REQUIRED"]
    assert candidate_chunks(claim, parsed, raw_chunks)[0]["ocr_status"] == "NOT_RUN"


async def test_invalid_ingestion_profile_is_rejected_before_blob_or_database_access():
    from shopsteward_knowledge.contracts import IngestionRequest
    from shopsteward_knowledge.ingestion import IngestionService

    request = IngestionRequest.model_validate(
        {
            "original": {
                "version_id": "v1",
                "sha256": hashlib.sha256(b"abc").hexdigest(),
                "size_bytes": 3,
                "storage_key": "v1.txt",
                "mime": "text/plain",
            },
            "projection": {
                "version_id": "v1",
                "document_id": "d1",
                "store_id": "s1",
                "title": "Policy",
                "metadata_revision": 1,
            },
            "profile_id": "unknown-v1",
        }
    )
    with pytest.raises(ValueError, match="profile"):
        await IngestionService(None, None).accept(request, b"abc", "key1")


async def test_document_embedding_batches_and_profile_identity_synthetic_protocol_only():
    from shopsteward_knowledge.contracts import EmbeddingProfile
    from shopsteward_knowledge.retrieval.search import profile_key
    from shopsteward_knowledge.worker import index_rows

    class Embedder:
        def __init__(self):
            self.batches = []

        async def embed(self, texts, *, input_type, profile, deadline_ms):
            assert input_type == "document" and profile["model"] == "synthetic-test-only"
            self.batches.append(len(texts))
            return [[1.0, float(text[1:]) + 1] for text in texts]

    chunks = [{"chunk_id": f"c{i}", "text": f"t{i}"} for i in range(65)]
    profile = EmbeddingProfile(
        provider="test", model="synthetic-test-only", dimensions=2
    ).model_dump()
    embedder = Embedder()
    rows = await index_rows(chunks, "hybrid-v1", embedder, profile)
    assert embedder.batches == [64, 1]
    assert rows[64]["vector"] == [1.0, 65.0]
    assert rows[0]["embedding_profile"] == profile_key(profile)
    assert chunks[0]["embedding_profile_config"]["model"] == "synthetic-test-only"
    assert chunks[0]["embedding_input_type"] == "document"


async def test_lexical_index_never_invokes_embedding_and_unknown_profiles_fail():
    from shopsteward_knowledge.worker import index_rows

    class Forbidden:
        async def embed(self, *args, **kwargs):
            raise AssertionError("lexical ingestion must not call a model")

    chunks = [{"chunk_id": "c1", "text": "policy"}]
    assert await index_rows(chunks, "lexical-v1", Forbidden(), None) == chunks
    for profile_id in ("unknown-v1", "hybrid-v1"):
        with pytest.raises(ValueError):
            await index_rows(chunks, profile_id, None, None)


@pytest.mark.parametrize("blank", ["", " \t\n"])
def test_blank_embedding_environment_keeps_lexical_service_enabled(monkeypatch, blank):
    from shopsteward_knowledge.config import Settings, create_embedding

    for name in ("URL", "API_KEY", "MODEL", "DIMENSIONS", "REVISION"):
        monkeypatch.setenv("KNOWLEDGE_EMBEDDING_" + name, blank)
    settings = Settings()
    assert settings.enabled_profiles() == {"lexical-v1"}
    assert settings.embedding_profile() is None
    assert create_embedding(settings, None) is None
    assert settings.embedding_revision is None


@pytest.mark.parametrize("missing", ["url", "api_key", "model", "dimensions"])
def test_blank_embedding_field_still_rejects_partial_configuration(missing):
    from shopsteward_knowledge.config import Settings

    values = {
        "embedding_url": "https://embedding.invalid/v1/embeddings",
        "embedding_api_key": "explicit-test-key",
        "embedding_model": "test-model",
        "embedding_dimensions": "2",
        "embedding_revision": "",
    }
    values["embedding_" + missing] = " "
    with pytest.raises(ValueError, match="complete explicit"):
        Settings(**values)


def test_blank_revision_is_optional_for_complete_embedding_configuration():
    from shopsteward_knowledge.config import Settings

    settings = Settings(
        embedding_url="https://embedding.invalid/v1/embeddings",
        embedding_api_key="explicit-test-key",
        embedding_model="test-model",
        embedding_dimensions="2",
        embedding_revision=" \t",
    )
    assert settings.embedding_profile()["revision"] is None
    assert settings.embedding_profile()["dimensions"] == 2
    assert settings.enabled_profiles() == {"lexical-v1", "hybrid-v1"}


def test_manual_retry_budget_never_resets_or_exceeds_total_attempt_limit():
    from shopsteward_knowledge.publication import retry_attempt_limit

    assert retry_attempt_limit(5, 5, 15) == 10
    assert retry_attempt_limit(14, 5, 15) == 15
    assert retry_attempt_limit(1, 5, 15) == 6
    with pytest.raises(ValueError, match="exhausted"):
        retry_attempt_limit(15, 5, 15)


def test_retry_total_configuration_cannot_be_smaller_than_initial_window():
    from shopsteward_knowledge.config import Settings

    with pytest.raises(ValueError, match="total"):
        Settings(max_attempts=5, max_total_attempts=4)


@pytest.mark.parametrize("blank", ["", " \t"])
def test_blank_rerank_configuration_is_disabled_without_provider_calls(monkeypatch, blank):
    from shopsteward_knowledge.config import Settings, create_reranker

    for field in ("URL", "API_KEY", "MODEL"):
        monkeypatch.setenv("KNOWLEDGE_RERANK_" + field, blank)
    settings = Settings()
    assert create_reranker(settings, None) is None
    assert settings.enabled_profiles() == {"lexical-v1"}


@pytest.mark.parametrize("missing", ["url", "api_key", "model"])
def test_partial_rerank_configuration_is_rejected(missing):
    from shopsteward_knowledge.config import Settings

    values = {
        "rerank_url": "https://rerank.invalid/v1/rerank",
        "rerank_api_key": "test-key",
        "rerank_model": "test-model",
    }
    values["rerank_" + missing] = " "
    with pytest.raises(ValueError, match="rerank requires complete"):
        Settings(**values)


async def test_api_runtime_wires_explicit_rerank_configuration(monkeypatch):
    import json

    import httpx

    from shopsteward_knowledge.api import create_app
    from shopsteward_knowledge.config import Settings
    from shopsteward_knowledge.contracts import Candidate

    def provider(request):
        assert str(request.url) == "https://rerank.invalid/v1/rerank"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert json.loads(request.content)["model"] == "test-model"
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.75}]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(provider), **kwargs),
    )
    settings = Settings(
        database_url=None,
        opensearch_url="http://search.invalid",
        service_key="test",
        rerank_url="https://rerank.invalid/v1/rerank",
        rerank_api_key="test-key",
        rerank_model="test-model",
    )
    app = create_app(settings, session_factory=object())
    hit = Candidate(
        document_id="d1",
        version_id="v1",
        generation_id="g1",
        chunk_id="c1",
        metadata_revision=1,
        text="policy",
        title="Policy",
        store_id="s1",
        locator={"kind": "paragraph", "paragraph_range": [1, 1]},
        content_sha256=hashlib.sha256(b"policy").hexdigest(),
    )
    async with app.router.lifespan_context(app):
        result = await app.state.search_service.reranker.rerank("policy", [hit], deadline_ms=1000)
    assert result[0].rerank_score == 0.75 and result[0].text == hit.text


def test_worker_refuses_an_index_without_visibility_proof():
    import asyncio
    from types import SimpleNamespace

    from shopsteward_knowledge.config import Settings
    from shopsteward_knowledge.worker import ingest_once

    with pytest.raises(RuntimeError, match="verify_generation"):
        asyncio.run(
            ingest_once(
                Settings(),
                session_factory=object(),
                blob=object(),
                index=SimpleNamespace(),
                parser=lambda: None,
                chunker=lambda: None,
            )
        )
