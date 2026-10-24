import hashlib

import pytest


def row(tmp_path):
    content = "# 模拟收货\n破损附照片。".encode()
    (tmp_path / "original.md").write_bytes(content)
    return {
        "document_fixture_id": "D1",
        "version_fixture_id": "V1",
        "store_fixture": "S1",
        "original_path": "original.md",
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "title": "模拟收货",
        "synthetic": True,
        "metadata": {"title": "模拟收货", "sku_ids": ["SKU1"]},
    }


def test_import_checks_bytes_before_upload_and_maps_real_entities(tmp_path):
    from tools.import_knowledge_corpus import prepare_upload

    record = row(tmp_path)
    mapping = {"stores": {"S1": "test-store"}, "skus": {"SKU1": "actual-sku"}, "suppliers": {}}
    prepared = prepare_upload(record, tmp_path, mapping)
    assert prepared["store_id"] == "test-store"
    assert prepared["metadata"]["sku_ids"] == ["actual-sku"]
    (tmp_path / "original.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        prepare_upload(record, tmp_path, mapping)


def test_unmapped_store_or_sku_is_not_silently_used(tmp_path):
    from tools.import_knowledge_corpus import prepare_upload

    with pytest.raises(ValueError, match="mapping"):
        prepare_upload(row(tmp_path), tmp_path, {"stores": {}, "skus": {}, "suppliers": {}})


def test_public_source_manifest_upload_uses_normalized_bytes_and_keeps_archive_provenance(tmp_path):
    from tools.import_knowledge_corpus import prepare_upload
    from tools.knowledge_corpus.manifest import build_manifest, normalize_public, validate_manifest

    public = tmp_path / "public"
    public.mkdir()
    archive, normalized = b"raw archive bytes", b"# Normalized source\nActual licensed text.\n"
    (public / "archive.pdf").write_bytes(archive)
    (public / "text.md").write_bytes(normalized)
    source = dict(
        source_family_id="PUBLIC01",
        document_fixture_id="PUB01",
        version_fixture_id="PUB01-v1",
        title="Public source",
        publisher="Publisher",
        url="https://example.org/source",
        language="en",
        jurisdiction="NZ",
        publication_date=None,
        retrieved_at="2026-09-08T00:00:00Z",
        acquisition_status="acquired",
        use_terms_status="reviewed",
        source_kind="official_document",
        synthetic=False,
        original_path="public/archive.pdf",
        mime="application/pdf",
        size_bytes=len(archive),
        content_sha256=hashlib.sha256(archive).hexdigest(),
        normalized_path="public/text.md",
        normalized_mime="text/markdown",
        normalized_size_bytes=len(normalized),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
    )
    manifest = build_manifest([normalize_public(source)], tmp_path)
    assert validate_manifest(manifest, tmp_path)["errors"] == []
    record = manifest["documents"][0]
    prepared = prepare_upload(
        record,
        tmp_path,
        {
            "default_store_fixture": "S1",
            "stores": {"S1": "test-store"},
            "skus": {},
            "suppliers": {},
        },
    )
    assert prepared["path"].read_bytes() == normalized
    assert prepared["content_sha256"] == hashlib.sha256(normalized).hexdigest()
    assert record["sha256"] == hashlib.sha256(normalized).hexdigest()
    assert record["metadata"]["source_original_sha256"] == hashlib.sha256(archive).hexdigest()
    (public / "text.md").write_bytes(b"tampered normalized text")
    assert validate_manifest(manifest, tmp_path)["errors"]
    with pytest.raises(ValueError, match="hash"):
        prepare_upload(record, tmp_path, {"stores": {}, "skus": {}, "suppliers": {}})


def test_source_path_cannot_escape_corpus(tmp_path):
    from tools.import_knowledge_corpus import prepare_upload

    record = row(tmp_path) | {"original_path": "../secret.txt"}
    with pytest.raises(ValueError, match="path"):
        prepare_upload(record, tmp_path, {})


def test_expanded_manifest_maps_fixture_metadata_into_strict_k1_dto(tmp_path):
    from app.knowledge.schemas import UploadMetadata
    from tools.import_knowledge_corpus import prepare_upload

    record = row(tmp_path)
    record["size"] = record.pop("size_bytes")
    record.pop("store_fixture")
    record["metadata"] = {
        "title": "模拟",
        "category": "supplier",
        "store_fixture": "S1",
        "sku_fixture_ids": ["SKU1"],
        "supplier_fixture_ids": ["SUP1"],
        "author": "fixture",
        "generation_method": "authored",
        "provenance": {"synthetic": True, "source_kind": "synthetic_business_document"},
    }
    prepared = prepare_upload(
        record,
        tmp_path,
        {
            "stores": {"S1": "test-store"},
            "skus": {"SKU1": "actual-sku"},
            "suppliers": {"SUP1": "actual-supplier"},
        },
    )
    metadata = UploadMetadata.model_validate(prepared["metadata"])
    assert metadata.sku_ids == ["actual-sku"]
    assert metadata.supplier_ids == ["actual-supplier"]
    assert metadata.provenance.synthetic is True


async def test_append_retry_reuses_original_cas_after_ambiguous_network_failure(tmp_path):
    import json
    import re

    import httpx

    from tools.import_knowledge_corpus import import_records, prepare_upload

    prepared = prepare_upload(
        row(tmp_path),
        tmp_path,
        {"stores": {"S1": "test-store"}, "skus": {"SKU1": "actual-sku"}, "suppliers": {}},
    )
    receipts = tmp_path / "receipts.json"
    receipts.write_text(json.dumps({"documents": {"D1": "actual-doc"}, "versions": {}}))
    accepted = None

    def handler(request):
        nonlocal accepted
        if request.method == "GET":
            return httpx.Response(200, json={"metadata_version": 2 if accepted else 1})
        if request.url.path.endswith("/versions"):
            body = json.loads(re.search(rb"\r\n\r\n(\{.*?\})\r\n--", request.content).group(1))
            if accepted is None:
                accepted = body
                raise httpx.ReadError("reply lost after committed append")
            if body != accepted:
                return httpx.Response(409)
            return httpx.Response(201, json={"id": "actual-doc", "latest_version_id": "actual-v2"})
        return httpx.Response(202, json={"request_id": "J1", "state": "PENDING"})

    async with httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    ) as client:
        first = await import_records(client, [prepared], token="test", receipts_path=receipts)
        assert len(first["failures"]) == 1
        second = await import_records(client, [prepared], token="test", receipts_path=receipts)
        assert second["failures"] == []


def test_documented_direct_cli_resolves_backend_package_from_repo_root(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    record = row(tmp_path)
    manifest, mapping = tmp_path / "manifest.json", tmp_path / "mapping.json"
    manifest.write_text(json.dumps({"documents": [record]}), encoding="utf-8")
    mapping.write_text(
        json.dumps(
            {"stores": {"S1": "actual-store"}, "skus": {"SKU1": "actual-sku"}, "suppliers": {}}
        ),
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "backend/tools/import_knowledge_corpus.py",
            "--target-test",
            "--manifest",
            str(manifest),
            "--root",
            str(tmp_path),
            "--mapping",
            str(mapping),
            "--dry-run",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["validated_original_versions"] == 1
