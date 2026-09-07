import asyncio
import hashlib
import io
import json
from contextlib import asynccontextmanager
from uuid import uuid4
from zipfile import ZipFile

import httpx
import pytest
from sqlalchemy import text
from test_missions import fresh_seed, headers, settings
from test_operations import initialize

pytestmark = pytest.mark.integration


@asynccontextmanager
async def environment(db, tmp_path):
    from app.main import create_app

    seed = fresh_seed()
    await initialize(db, seed)
    config = settings(db, seed, knowledge_storage_root=str(tmp_path))
    app = create_app(config)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield seed, client, app


async def upload(
    client,
    store_id,
    *,
    key=None,
    content=b"original",
    name="notes.txt",
    metadata=None,
    url=None,
    role="operator",
):
    return await client.post(
        url or f"/api/v1/stores/{store_id}/documents",
        headers=headers(role, key),
        data={
            "metadata": json.dumps(
                metadata
                or {"title": "Notes", "sku_ids": ["sku_001"], "supplier_ids": ["supplier_001"]}
            )
        },
        files={"file": (name, content, "application/octet-stream")},
    )


async def test_upload_replay_original_version_and_no_fake_job(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        async with db.session() as session:
            before = await session.scalar(text("SELECT count(*) FROM job_runs"))
        key = str(uuid4())
        first = await upload(client, seed["store_id"], key=key, name="../../中文.txt")
        assert first.status_code == 201, first.text
        doc = first.json()
        assert doc["ingestion_status"] == "UPLOADED"
        assert doc["indexing_status"] == "NOT_INDEXED"
        assert doc["metadata_version"] == 1 and doc["latest_version_id"]
        assert "active_version_id" not in doc and "job_run_id" not in doc
        replay = await upload(client, seed["store_id"], key=key, name="../../中文.txt")
        assert replay.status_code == 201 and replay.json() == doc
        assert (
            await upload(
                client, seed["store_id"], key=key, content=b"changed", name="../../中文.txt"
            )
        ).status_code == 409
        url = f"/api/v1/documents/{doc['id']}"
        versions = await client.get(url + "/versions", headers=headers("viewer"))
        assert versions.status_code == 200
        version = versions.json()["items"][0]
        assert version["version_no"] == 1
        assert version["content_sha256"] == hashlib.sha256(b"original").hexdigest()
        assert version["size_bytes"] == 8 and "raw_key" not in version
        original = await client.get(
            url + f"/versions/{version['id']}/content", headers=headers("viewer")
        )
        assert original.content == b"original"
        assert original.headers["x-content-type-options"] == "nosniff"
        assert original.headers["content-disposition"].startswith("attachment;")
        assert original.headers["cache-control"] == "private, no-store"
        async with db.session() as session:
            assert await session.scalar(text("SELECT count(*) FROM job_runs")) == before
            row = (
                await session.execute(
                    text("SELECT raw_key FROM knowledge_versions WHERE id=:id"),
                    {"id": version["id"]},
                )
            ).scalar_one()
        assert (tmp_path / row).read_bytes() == b"original"
        assert ".." not in row and "中文" not in row


async def test_private_permissions_replay_reauthorization_and_admin_discovery(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        key = str(uuid4())
        result = await upload(client, seed["store_id"], key=key)
        assert result.status_code == 201, result.text
        doc = result.json()
        url = f"/api/v1/documents/{doc['id']}"
        changed = await client.patch(
            url, headers=headers(), json={"expected_metadata_version": 1, "visibility": "private"}
        )
        assert changed.status_code == 200
        for role in ["viewer", "approver"]:
            assert (await client.get(url, headers=headers(role))).status_code == 404
            page = await client.get(
                f"/api/v1/stores/{seed['store_id']}/documents", headers=headers(role)
            )
            assert page.json()["items"] == []
        assert (await client.get(url, headers=headers("admin"))).status_code == 200
        for suffix in ["/versions", f"/versions/{doc['latest_version_id']}/content"]:
            assert (await client.get(url + suffix, headers=headers("admin"))).status_code == 404
        assert (
            await client.patch(
                url,
                headers=headers("admin"),
                json={"expected_metadata_version": 2, "visibility": "store"},
            )
        ).status_code == 404
        # Revoke the uploader's store grant: receipt must not bypass current authorization.
        next(
            g for g in app.state.settings.auth_tokens if g.principal_id == "operator"
        ).store_ids = []
        assert (await upload(client, seed["store_id"], key=key)).status_code == 404
        assert (await client.get(url, headers=headers())).status_code == 404
        assert (await upload(client, seed["store_id"], role="viewer")).status_code == 403


async def test_metadata_cas_archive_restore_and_append(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        first = await upload(client, seed["store_id"])
        assert first.status_code == 201, first.text
        doc = first.json()
        url = f"/api/v1/documents/{doc['id']}"
        patches = await asyncio.gather(
            *(
                client.patch(
                    url, headers=headers(), json={"expected_metadata_version": 1, "title": title}
                )
                for title in ["A", "B"]
            )
        )
        assert sorted(r.status_code for r in patches) == [200, 409]
        append_key = str(uuid4())
        appended = await upload(
            client,
            seed["store_id"],
            url=url + "/versions",
            key=append_key,
            content=b"second",
            metadata={"expected_metadata_version": 2},
        )
        assert appended.status_code == 201, appended.text
        assert appended.json()["metadata_version"] == 3
        assert appended.json()["latest_version_id"] != doc["latest_version_id"]
        assert (
            await upload(
                client,
                seed["store_id"],
                url=url + "/versions",
                key=append_key,
                content=b"second",
                metadata={"expected_metadata_version": 2},
            )
        ).json() == appended.json()
        archived = await client.post(
            url + "/control",
            headers=headers(),
            json={"operation": "archive", "expected_metadata_version": 3},
        )
        assert archived.status_code == 200 and archived.json()["status"] == "archived"
        assert (
            await upload(
                client,
                seed["store_id"],
                url=url + "/versions",
                metadata={"expected_metadata_version": 4},
            )
        ).status_code == 409
        assert (
            await client.get(
                url + f"/versions/{doc['latest_version_id']}/content", headers=headers("viewer")
            )
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/stores/{seed['store_id']}/documents", headers=headers())
        ).json()["items"] == []
        restored = await client.post(
            url + "/control",
            headers=headers(),
            json={"operation": "restore", "expected_metadata_version": 4},
        )
        assert restored.status_code == 200 and restored.json()["metadata_version"] == 5
        old = await client.get(
            url + f"/versions/{doc['latest_version_id']}/content", headers=headers("viewer")
        )
        assert old.content == b"original"


async def test_concurrent_idempotency_append_and_entity_cursor_filters(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        key = str(uuid4())
        created = await asyncio.gather(
            *(upload(client, seed["store_id"], key=key) for _ in range(3))
        )
        assert [r.status_code for r in created] == [201, 201, 201]
        assert len({r.json()["id"] for r in created}) == 1
        doc = created[0].json()
        url = f"/api/v1/documents/{doc['id']}"
        versions = await asyncio.gather(
            *(
                upload(
                    client,
                    seed["store_id"],
                    url=url + "/versions",
                    content=value,
                    metadata={"expected_metadata_version": 1},
                )
                for value in [b"A", b"B"]
            )
        )
        assert sorted(r.status_code for r in versions) == [201, 409]
        for _ in range(2):
            assert (await upload(client, seed["store_id"])).status_code == 201
        list_url = f"/api/v1/stores/{seed['store_id']}/documents"
        params = {"sku_id": "sku_001", "supplier_id": "supplier_001", "limit": 2}
        page = (await client.get(list_url, params=params, headers=headers())).json()
        assert len(page["items"]) == 2 and page["next_cursor"]
        second = (
            await client.get(
                list_url, params=params | {"cursor": page["next_cursor"]}, headers=headers()
            )
        ).json()
        assert len(second["items"]) == 1 and second["next_cursor"] is None
        assert not {d["id"] for d in page["items"]} & {d["id"] for d in second["items"]}
        assert (
            await client.get(
                list_url,
                params=params | {"q": "other", "cursor": page["next_cursor"]},
                headers=headers(),
            )
        ).status_code == 422
        assert (
            await client.get(list_url, params={"sku_id": "unknown"}, headers=headers())
        ).status_code == 404
        assert (
            await upload(client, seed["store_id"], metadata={"title": "x", "sku_ids": ["bad"]})
        ).status_code == 404
        assert (
            await upload(client, seed["store_id"], metadata={"title": "x", "supplier_ids": ["bad"]})
        ).status_code == 404
        assert (await upload(client, "nonexistent", role="admin")).status_code == 404


def office(extension, body=b"<bad"):
    buf = io.BytesIO()
    with ZipFile(buf, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml" if extension == "docx" else "xl/workbook.xml", body)
    return buf.getvalue()


@pytest.mark.parametrize(
    "name,content,status",
    [
        ("bad.txt", b"\xff", 422),
        ("bad.md", b"\x00", 422),
        ("bad.csv", b"\xc0\xaf", 422),
        ("bad.pdf", b"%PDF-1.7\nbroken", 422),
        ("bad.docx", office("docx"), 422),
        ("bad.xlsx", b"PK\x03\x04broken", 422),
        ("evil.exe", b"MZ", 422),
        ("too-big.txt", b"x" * (20 * 1024 * 1024 + 1), 413),
    ],
    ids=["utf8-txt", "nul-md", "utf8-csv", "pdf", "docx", "xlsx", "extension", "size"],
)
async def test_invalid_upload_rejected_without_rows(db, tmp_path, name, content, status):
    async with environment(db, tmp_path) as (seed, client, app):
        result = await upload(client, seed["store_id"], name=name, content=content)
        assert result.status_code == status, result.text
        async with db.session() as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM knowledge_documents WHERE store_id=:id"),
                    {"id": seed["store_id"]},
                )
                == 0
            )


async def test_patch_idempotency_replay_conflict_and_reauthorization(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        first = await upload(client, seed["store_id"])
        assert first.status_code == 201
        doc = first.json()
        url = f"/api/v1/documents/{doc['id']}"
        key = str(uuid4())
        body = {"expected_metadata_version": 1, "title": "Updated"}
        changed = await client.patch(url, headers=headers(key=key), json=body)
        assert changed.status_code == 200
        replay = await client.patch(url, headers=headers(key=key), json=body)
        assert replay.status_code == 200 and replay.json() == changed.json()
        conflict = await client.patch(
            url, headers=headers(key=key), json=body | {"title": "Different"}
        )
        assert conflict.status_code == 409
        next(
            g for g in app.state.settings.auth_tokens if g.principal_id == "operator"
        ).store_ids = []
        denied = await client.patch(url, headers=headers(key=key), json=body)
        assert denied.status_code == 404


async def test_real_ready_and_original_survive_app_restart(db, tmp_path):
    from app.main import create_app

    async with environment(db, tmp_path) as (seed, client, app):
        assert (await client.get("/health/ready")).status_code == 200
        doc = (await upload(client, seed["store_id"])).json()
        config = app.state.settings
    restarted = create_app(config)
    async with (
        restarted.router.lifespan_context(restarted),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted), base_url="http://test"
        ) as client,
    ):
        path = f"/api/v1/documents/{doc['id']}/versions/{doc['latest_version_id']}/content"
        assert (await client.get(path, headers=headers())).content == b"original"
        assert (await client.get("/health/ready")).status_code == 200


async def test_pg_versions_immutable_and_latest_pointer_belongs_to_document(db, tmp_path):
    from sqlalchemy.exc import IntegrityError

    async with environment(db, tmp_path) as (seed, client, app):
        one = (await upload(client, seed["store_id"])).json()
        two = (await upload(client, seed["store_id"])).json()
        for statement in [
            "UPDATE knowledge_versions SET size_bytes=1 WHERE id=:id",
            "DELETE FROM knowledge_versions WHERE id=:id",
        ]:
            with pytest.raises(IntegrityError):
                async with db.session() as session, session.begin():
                    await session.execute(text(statement), {"id": one["latest_version_id"]})
        with pytest.raises(IntegrityError):
            async with db.session() as session, session.begin():
                await session.execute(
                    text("UPDATE knowledge_documents SET latest_version_id=:version WHERE id=:id"),
                    {"id": one["id"], "version": two["latest_version_id"]},
                )
        bad = f"/api/v1/documents/{one['id']}/versions/{two['latest_version_id']}"
        assert (await client.get(bad, headers=headers())).status_code == 404
        assert (await client.get(bad + "/content", headers=headers())).status_code == 404


async def test_concurrent_append_replay_version_pagination_and_validity(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        doc = (await upload(client, seed["store_id"])).json()
        url = f"/api/v1/documents/{doc['id']}"
        key = str(uuid4())
        meta = {
            "expected_metadata_version": 1,
            "valid_from": "2026-10-01T00:00:00Z",
            "valid_until": "2026-11-01T00:00:00Z",
        }
        results = await asyncio.gather(
            *(
                upload(
                    client,
                    seed["store_id"],
                    url=url + "/versions",
                    key=key,
                    metadata=meta,
                    content=b"future",
                )
                for _ in range(3)
            )
        )
        assert [r.status_code for r in results] == [201, 201, 201]
        assert len({r.json()["latest_version_id"] for r in results}) == 1
        page = (await client.get(url + "/versions", params={"limit": 1}, headers=headers())).json()
        assert page["items"][0]["version_no"] == 2
        assert page["items"][0]["valid_from"] == "2026-10-01T00:00:00Z"
        assert page["items"][0]["indexing_status"] == "NOT_INDEXED"
        second = (
            await client.get(
                url + "/versions",
                params={"limit": 1, "cursor": page["next_cursor"]},
                headers=headers(),
            )
        ).json()
        assert second["items"][0]["id"] == doc["latest_version_id"]
        assert second["next_cursor"] is None
        assert (
            await upload(
                client,
                seed["store_id"],
                url=url + "/versions",
                metadata={
                    "expected_metadata_version": 2,
                    "valid_from": "2026-11-01T00:00:00Z",
                    "valid_until": "2026-10-01T00:00:00Z",
                },
            )
        ).status_code == 422
        assert (
            await upload(
                client,
                seed["store_id"],
                url=url + "/versions",
                metadata={"expected_metadata_version": 2, "valid_from": "2026-11-01T00:00:00"},
            )
        ).status_code == 422


async def test_file_stream_holds_no_store_lock(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        started, resume = asyncio.Event(), asyncio.Event()
        template = httpx.Request(
            "POST",
            "http://test",
            data={"metadata": '{"title":"Stream"}'},
            files={"file": ("notes.txt", b"data", "text/plain")},
        )
        raw = template.read()

        async def stream():
            yield raw[: len(raw) // 2]
            started.set()
            await resume.wait()
            yield raw[len(raw) // 2 :]

        task = asyncio.create_task(
            client.post(
                f"/api/v1/stores/{seed['store_id']}/documents",
                headers=headers() | {"Content-Type": template.headers["content-type"]},
                content=stream(),
            )
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            async with db.session() as session, session.begin():
                await session.execute(
                    text("SELECT id FROM stores WHERE id=:id FOR UPDATE NOWAIT"),
                    {"id": seed["store_id"]},
                )
        finally:
            resume.set()
        assert (await task).status_code == 201


async def test_failed_transaction_leaves_only_unreferenced_original_and_retry_succeeds(
    db, tmp_path, monkeypatch
):
    from app.core.errors import AppError
    from app.knowledge import repository

    async with environment(db, tmp_path) as (seed, client, app):
        doc = (await upload(client, seed["store_id"])).json()
        url = f"/api/v1/documents/{doc['id']}"
        original_add = repository.add_version

        async def failing(*args, **kwargs):
            await original_add(*args, **kwargs)
            raise AppError(503, "DEPENDENCY_UNAVAILABLE", "Injected transaction failure")

        key = str(uuid4())
        with monkeypatch.context() as patch:
            patch.setattr(repository, "add_version", failing)
            result = await upload(
                client,
                seed["store_id"],
                url=url + "/versions",
                key=key,
                metadata={"expected_metadata_version": 1},
                content=b"new",
            )
        assert result.status_code == 503
        assert len(list(tmp_path.iterdir())) == 2
        versions = (await client.get(url + "/versions", headers=headers())).json()["items"]
        assert len(versions) == 1 and versions[0]["id"] == doc["latest_version_id"]
        original = await client.get(
            url + f"/versions/{doc['latest_version_id']}/content", headers=headers()
        )
        assert original.content == b"original"
        retried = await upload(
            client,
            seed["store_id"],
            url=url + "/versions",
            key=key,
            metadata={"expected_metadata_version": 1},
            content=b"new",
        )
        assert retried.status_code == 201 and retried.json()["metadata_version"] == 2


async def test_control_patch_race_and_control_replay(db, tmp_path):
    async with environment(db, tmp_path) as (seed, client, app):
        doc = (await upload(client, seed["store_id"])).json()
        url = f"/api/v1/documents/{doc['id']}"
        key = str(uuid4())
        body = {"operation": "archive", "expected_metadata_version": 1}
        archived = await client.post(url + "/control", headers=headers(key=key), json=body)
        assert archived.status_code == 200
        replay = await client.post(url + "/control", headers=headers(key=key), json=body)
        assert replay.status_code == 200 and replay.json() == archived.json()
        racing = await asyncio.gather(
            client.patch(
                url, headers=headers(), json={"expected_metadata_version": 2, "title": "Race"}
            ),
            client.post(
                url + "/control",
                headers=headers(),
                json={"operation": "restore", "expected_metadata_version": 2},
            ),
        )
        assert sorted(r.status_code for r in racing) == [200, 409]


async def test_replay_of_now_private_document_denies_nonowner_before_conflict(db, tmp_path):
    from app.core.config import TokenGrant

    async with environment(db, tmp_path) as (seed, client, app):
        owner_token = "knowledge-owner-credential-00000000000001"
        app.state.settings.auth_tokens.append(
            TokenGrant(
                token=owner_token,
                principal_id="owner",
                roles=["operator"],
                store_ids=[seed["store_id"]],
            )
        )
        created = await client.post(
            f"/api/v1/stores/{seed['store_id']}/documents",
            headers={"Authorization": "Bearer " + owner_token, "Idempotency-Key": str(uuid4())},
            data={"metadata": '{"title":"Owner"}'},
            files={"file": ("notes.txt", b"owner")},
        )
        doc = created.json()
        url = f"/api/v1/documents/{doc['id']}"
        key = str(uuid4())
        meta = {"expected_metadata_version": 1}
        assert (
            await upload(client, seed["store_id"], url=url + "/versions", key=key, metadata=meta)
        ).status_code == 201
        private = await client.patch(
            url,
            headers={"Authorization": "Bearer " + owner_token, "Idempotency-Key": str(uuid4())},
            json={"expected_metadata_version": 2, "visibility": "private"},
        )
        assert private.status_code == 200
        for content in [b"original", b"different"]:
            assert (
                await upload(
                    client,
                    seed["store_id"],
                    url=url + "/versions",
                    key=key,
                    metadata=meta,
                    content=content,
                )
            ).status_code == 404


async def test_version_cursor_rejects_out_of_database_integer_range(db, tmp_path):
    import base64

    async with environment(db, tmp_path) as (seed, client, app):
        doc = (await upload(client, seed["store_id"])).json()
        url = f"/api/v1/documents/{doc['id']}/versions"
        assert (
            await upload(
                client, seed["store_id"], url=url, metadata={"expected_metadata_version": 1}
            )
        ).status_code == 201
        page = (await client.get(url, params={"limit": 1}, headers=headers())).json()
        decoded = json.loads(base64.urlsafe_b64decode(page["next_cursor"]))
        decoded["version_no"] = 2**100
        cursor = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()
        response = await client.get(url, params={"cursor": cursor}, headers=headers())
        assert response.status_code == 422
