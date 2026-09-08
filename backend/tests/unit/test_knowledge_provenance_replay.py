"""Historical K1 fingerprints, exercised through create/append replay paths."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.errors import AppError
from app.core.hashing import digest
from app.knowledge import repository
from app.knowledge.schemas import AppendMetadata, UploadMetadata


@pytest.fixture(params=["create", "append"])
def replay(request, monkeypatch):
    operation = request.param
    metadata = {"valid_from": None, "valid_until": None}
    if operation == "create":
        metadata.update(
            title="Policy", category="general", sku_ids=[], supplier_ids=[], visibility="store"
        )
    else:
        metadata["expected_metadata_version"] = 1
    content = {
        "metadata": dict(metadata),
        "original_name": "policy.txt",
        "content_sha256": "a" * 64,
        "size_bytes": 6,
        "mime_type": "text/plain",
    }
    if operation == "create":
        content["store_id"] = "S1"
    now = datetime.now(UTC).isoformat()
    saved = SimpleNamespace(
        content_hash=digest(content),
        response={
            "id": "D1",
            "store_id": "S1",
            "owner_principal_id": "P1",
            "title": "Policy",
            "metadata_version": 1,
            "status": "active",
            "latest_version_id": "V1",
            "ingestion_status": "UPLOADED",
            "indexing_status": "NOT_INDEXED",
            "created_at": now,
            "updated_at": now,
        },
    )
    monkeypatch.setattr(repository, "receipt", AsyncMock(return_value=(saved, True)))
    monkeypatch.setattr(repository, "store_scope", AsyncMock())
    monkeypatch.setattr(repository, "visible", AsyncMock(return_value=SimpleNamespace()))
    upload = SimpleNamespace(**{k: v for k, v in content.items() if k != "metadata"})

    async def invoke(provenance):
        body = (UploadMetadata if operation == "create" else AppendMetadata)(
            **metadata, **provenance
        )
        return await getattr(repository, operation)(
            None,
            SimpleNamespace(principal_id="P1"),
            "S1" if operation == "create" else "D1",
            body,
            upload,
            "historic-key",
        )

    return saved, content, invoke


@pytest.mark.parametrize("provenance", [{}, {"provenance": None}])
async def test_legacy_omitted_provenance_receipt_replays(replay, provenance):
    saved, _, invoke = replay
    previous_hash = saved.content_hash
    result = await invoke(provenance)
    assert (result.id, result.latest_version_id) == ("D1", "V1")
    assert saved.content_hash == previous_hash


@pytest.mark.parametrize("provenance", [{}, {"publisher": "new publisher"}])
async def test_explicit_provenance_conflicts_with_legacy_receipt(replay, provenance):
    _, _, invoke = replay
    with pytest.raises(AppError) as raised:
        await invoke({"provenance": provenance})
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


async def test_explicit_provenance_replays_but_changes_conflict(replay):
    from shopsteward_knowledge.contracts import Provenance

    saved, content, invoke = replay
    content["metadata"]["provenance"] = Provenance(publisher="original").model_dump(mode="json")
    saved.content_hash = digest(content)
    assert (await invoke({"provenance": {"publisher": "original"}})).id == "D1"
    for changed in [{}, {"provenance": None}, {"provenance": {"publisher": "changed"}}]:
        with pytest.raises(AppError) as raised:
            await invoke(changed)
        assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.parametrize("provenance", [{}, {"provenance": None}])
async def test_receipts_written_with_null_provenance_also_replay(replay, provenance):
    saved, content, invoke = replay
    content["metadata"]["provenance"] = None
    saved.content_hash = digest(content)
    assert (await invoke(provenance)).id == "D1"
    with pytest.raises(AppError) as raised:
        await invoke({"provenance": {"publisher": "new"}})
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


async def test_provenance_compatibility_does_not_ignore_other_metadata_changes(replay):
    saved, content, invoke = replay
    content["metadata"]["valid_from"] = "2026-01-01T00:00:00Z"
    saved.content_hash = digest(content)
    with pytest.raises(AppError) as raised:
        await invoke({})
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"
