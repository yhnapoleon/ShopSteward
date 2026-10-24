import hashlib

import pytest


def fixture(tmp_path):
    text = "# 模拟资料\n\n供应商仅在出示凭证时供应SKU。\n"
    data = text.encode()
    (tmp_path / "source.md").write_bytes(data)
    record = dict(
        document_fixture_id="D1",
        version_fixture_id="V1",
        original_path="source.md",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        mime="text/markdown",
        metadata=dict(title="模拟资料", store_fixture="S1", provenance=dict(synthetic=True)),
    )
    mapping = dict(stores={"S1": "actual-store"}, skus={"SKU1": "actual-sku"}, suppliers={})
    return record, mapping


def test_binding_uses_actual_server_version_and_worker_chunk_profile(tmp_path):
    from shopsteward_knowledge.contracts import OriginalRef
    from shopsteward_knowledge.parsing import parse_original
    from shopsteward_knowledge.parsing.chunking import chunk_blocks

    from tools.import_knowledge_relations import bind_quote

    record, mapping = fixture(tmp_path)
    bound = bind_quote(record, tmp_path, mapping, "server-version", "供应商仅在出示凭证时供应SKU。")
    ref = OriginalRef(
        version_id="server-version",
        sha256=record["sha256"],
        size_bytes=record["size"],
        mime=record["mime"],
        storage_key="source.md",
    )
    expected = chunk_blocks(
        parse_original(ref, (tmp_path / "source.md").read_bytes()).blocks, {"id": "lexical-v1"}
    )
    assert bound == [c for c in expected if "供应商" in c["text"]]
    assert all(c["version_id"] == "server-version" for c in bound)


def test_binding_rejects_unsupported_claim_and_changed_bytes(tmp_path):
    from tools.import_knowledge_relations import bind_quote

    record, mapping = fixture(tmp_path)
    with pytest.raises(ValueError, match="quote"):
        bind_quote(record, tmp_path, mapping, "server-version", "无凭证也可以供应")
    (tmp_path / "source.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        bind_quote(record, tmp_path, mapping, "server-version", "供应商")


def test_relation_requires_explicit_atoms_and_preserves_them():
    from tools.import_knowledge_relations import validate_authored_edge

    row = dict(
        assertion_status="synthetic_verified",
        assertion_scope="synthetic_fact_only_not_real_business_verification",
        condition_semantics="all_equal_required_keys_fail_closed",
        machine_conditions={"proof_available": True},
        evidence_quote="凭证",
        source_version_id="V1",
        relation_id="assertion1",
        relation_type="SUPPLIES",
        from_entity="SUP1",
        to_entity="SKU1",
    )
    edge = dict(
        source_version_fixture_id="V1",
        conditions={"proof_available": True},
        predicate="SUPPLIES",
        evidence_quote="凭证",
        subject="SUP1",
        object="SKU1",
        semantic_relation_id="assertion1",
    )
    validate_authored_edge(row, edge)
    with pytest.raises(ValueError, match="assertion"):
        validate_authored_edge(row, edge | {"object": "SKU2"})
    with pytest.raises(ValueError, match="assertion"):
        validate_authored_edge(row, edge | {"semantic_relation_id": "other"})
    with pytest.raises(ValueError, match="condition"):
        validate_authored_edge(row, edge | {"conditions": {}})
    with pytest.raises(ValueError, match="condition"):
        validate_authored_edge(row, edge | {"conditions": {"proof_available": 1}})
    with pytest.raises(ValueError, match="quote"):
        validate_authored_edge(row, edge | {"evidence_quote": "另一句原文"})
    with pytest.raises(ValueError, match="synthetic"):
        validate_authored_edge(row | {"assertion_status": "pending_human_review"}, edge)


def test_endpoint_is_bound_to_its_service_role():
    from tools.import_knowledge_relations import endpoint

    assert endpoint("http://127.0.0.1:8018/", "backend") == "http://127.0.0.1:8018"
    with pytest.raises(ValueError):
        endpoint("http://127.0.0.1:8020", "backend")
    with pytest.raises(ValueError):
        endpoint("http://127.0.0.1:8018", "knowledge")


def test_evidence_verification_compares_locator_and_original_not_only_text():
    from shopsteward_knowledge.contracts import Candidate

    from tools.import_knowledge_relations import verify_candidate

    text = "凭证"
    chunk = dict(
        chunk_id="c1",
        text=text,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        locator={"kind": "paragraph", "paragraph_range": [1, 1]},
    )
    candidate = Candidate(
        document_id="d",
        version_id="v",
        generation_id="g",
        store_id="s",
        metadata_revision=2,
        title="模拟",
        synthetic=True,
        original_sha256="a" * 64,
        **chunk,
    )
    identity = dict(
        document_id="d",
        version_id="v",
        generation_id="g",
        store_id="s",
        metadata_revision=2,
        original_sha256="a" * 64,
    )
    verify_candidate(candidate, chunk, identity)
    with pytest.raises(ValueError, match="evidence"):
        verify_candidate(
            candidate.model_copy(update={"original_sha256": "b" * 64}), chunk, identity
        )
    with pytest.raises(ValueError, match="evidence"):
        verify_candidate(candidate.model_copy(update={"synthetic": False}), chunk, identity)


@pytest.mark.parametrize("mismatch", [False, True])
async def test_http_import_requires_current_publication_and_exact_remote_chunk(tmp_path, mismatch):
    import httpx
    from shopsteward_knowledge.contracts import Candidate

    from tools.import_knowledge_relations import bind_quote, import_edge

    record, mapping = fixture(tmp_path)
    quote = "供应商仅在出示凭证时供应SKU。"
    row = dict(
        assertion_status="synthetic_verified",
        assertion_scope="synthetic_fact_only_not_real_business_verification",
        condition_semantics="all_equal_required_keys_fail_closed",
        evidence_quote=quote,
        machine_conditions={"proof_available": True},
        source_version_id="V1",
        effective_interval={"from": None, "until": None},
        relation_id="assertion1",
        relation_type="APPLIES_TO",
        from_entity="V1",
        to_entity="SKU1",
    )
    edge = dict(
        subject="SKU1",
        object="V1",
        predicate="HAS_APPLICABLE_DOCUMENT",
        source_version_fixture_id="V1",
        conditions={"proof_available": True},
        evidence_quote=quote,
        semantic_relation_id="assertion1",
    )
    chunk = bind_quote(record, tmp_path, mapping, "server-v", quote)[0]
    hit = Candidate(
        document_id="server-d",
        version_id="server-v",
        generation_id="server-g",
        metadata_revision=2,
        store_id="actual-store",
        title="模拟",
        synthetic=True,
        original_sha256="b" * 64 if mismatch else record["sha256"],
        **{k: chunk[k] for k in ("chunk_id", "text", "content_sha256", "locator")},
    )
    pub = dict(
        version_id="server-v",
        generation_id="server-g",
        metadata_revision=2,
        manifest_hash="c" * 64,
        valid_from=None,
        valid_until=None,
    )
    receipts = {
        "versions": {
            "V1": dict(
                document_id="server-d",
                version_id="server-v",
                source_sha256=record["sha256"],
                publication_receipt=pub,
                index_profile_id="lexical-v1",
            )
        }
    }
    posted = []

    def handler(request):
        import json

        if request.url.path == "/api/v1/documents/server-d":
            return httpx.Response(
                200,
                json=dict(
                    id="server-d",
                    store_id="actual-store",
                    status="active",
                    metadata_version=99,
                    evidence_revision=2,
                    publications=[pub],
                ),
            )
        if request.url.path == "/internal/v1/evidence":
            assert (
                json.loads(request.content)["scope"]["allowed_versions"][0]["metadata_revision"]
                == 2
            )
            return httpx.Response(
                200,
                json=dict(
                    request_id="r",
                    retrieval_profile="lexical-v1",
                    candidates=[hit.model_dump(mode="json")],
                ),
            )
        if request.url.path == "/internal/v1/relations":
            posted.append(json.loads(request.content))
            return httpx.Response(200, json=dict(generation_id="server-g", relation_ids=["edge"]))
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    ) as client:
        if mismatch:
            with pytest.raises(ValueError, match="evidence"):
                await import_edge(client, client, row, edge, record, tmp_path, mapping, receipts)
            assert posted == []
        else:
            await import_edge(client, client, row, edge, record, tmp_path, mapping, receipts)
            assert posted[0]["edges"][0]["conditions"] == {"proof_available": True}
            assert posted[0]["edges"][0]["subject"] == "actual-sku"
            assert posted[0]["edges"][0]["object"] == "server-v"
            assert posted[0]["edges"][0]["confirmed"] is True
