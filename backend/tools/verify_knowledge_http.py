"""K1 real HTTP/restart acceptance on shopsteward_test only, loopback port 8016.

Does not migrate or start a worker. Stores synthetic acceptance files under var.
Reads backend credentials in-process and never prints them. Stops only its own API.
"""

import asyncio
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.operations.repository import initialize  # noqa: E402
from app.operations.schemas import ScenarioRun  # noqa: E402


def seed():
    spec = json.loads((ROOT / "docs/api/services.openapi.json").read_text("utf-8"))
    initial = spec["paths"]["/sim/v1/runs"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["example"]
    suffix = uuid4().hex
    return json.loads(
        json.dumps(initial)
        .replace("store_001", "k1store_" + suffix)
        .replace("scenario_001", "k1run_" + suffix)
        .replace("forecast_001", "k1forecast_" + suffix)
    )


async def main():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8016))
    config = Settings(_env_file=ROOT / "backend/.env")
    url = make_url(config.database_url.get_secret_value()).set(database="shopsteward_test")
    assert url.database == "shopsteward_test"
    database = Database(url.render_as_string(hide_password=False))
    assert await database.ready(), "Migrate the dedicated test database first"
    initial = seed()
    async with database.session() as session, session.begin():
        await initialize(session, ScenarioRun.model_validate(initial))
    store_id = initial["store_id"]
    artifacts = ROOT / "var" / ("knowledge-http-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    artifacts.mkdir(parents=True)
    tokens = {role: secrets.token_hex(24) for role in ("operator", "viewer", "outsider", "admin")}
    grants = [
        {
            "principal_id": "knowledge-http-" + role,
            "token": token,
            "roles": ["viewer" if role == "outsider" else role],
            "store_ids": [] if role in {"outsider", "admin"} else [store_id],
        }
        for role, token in tokens.items()
    ]
    env = dict(
        os.environ,
        DATABASE_URL=url.render_as_string(hide_password=False),
        APP_ENV="test",
        AUTH_TOKENS=json.dumps(grants),
        AGENT_ENABLED="false",
        KNOWLEDGE_STORAGE_ROOT=str(artifacts / "originals"),
        PYTHONIOENCODING="utf-8",
    )
    processes, logs, checks = [], [], []
    client = httpx.AsyncClient(base_url="http://127.0.0.1:8016", timeout=20, trust_env=False)

    def headers(role="operator", key=None):
        return {"Authorization": "Bearer " + tokens[role], "Idempotency-Key": key or str(uuid4())}

    def check(ok, name):
        assert ok, name
        checks.append(name)

    async def start():
        stream = (artifacts / f"api-{len(processes)}.log").open("wb")
        logs.append(stream)
        process = await asyncio.to_thread(
            subprocess.Popen,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8016",
                "--no-access-log",
            ],
            cwd=ROOT / "backend",
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        processes.append(process)
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Acceptance API exited; inspect its local log")
            try:
                if (await client.get("/health/ready")).status_code == 200:
                    return process
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.1)
        raise RuntimeError("Acceptance API not ready")

    async def upload(payload, key, metadata, path=None, name="验收资料.md"):
        return await client.post(
            path or f"/api/v1/stores/{store_id}/documents",
            headers=headers(key=key),
            data={"metadata": json.dumps(metadata)},
            files={"file": (name, payload, "application/octet-stream")},
        )

    async def counts():
        async with database.session() as session:
            return {
                name: await session.scalar(text("SELECT count(*) FROM " + name))
                for name in ["job_runs", "business_events", "ledger_entries", "actions"]
            }

    try:
        process = await start()
        check(True, "real HTTP readiness on migrated test DB")
        before = await counts()
        original = "# 模拟资料\n部分到货按实收数量签收，未到部分保留待交。\n".encode()
        metadata = {
            "title": "模拟部分到货规则",
            "sku_ids": ["sku_001"],
            "supplier_ids": ["supplier_001"],
        }
        key = str(uuid4())
        created = await upload(original, key, metadata)
        check(created.status_code == 201, "multipart creation 201")
        document = created.json()
        check(
            document["ingestion_status"] == "UPLOADED"
            and document["indexing_status"] == "NOT_INDEXED",
            "honest K1 statuses",
        )
        prefix = f"/api/v1/documents/{document['id']}"
        raw = prefix + f"/versions/{document['latest_version_id']}/content"
        downloaded = await client.get(raw, headers=headers("viewer"))
        check(downloaded.content == original, "authenticated original byte identity")
        check(
            downloaded.headers["content-disposition"].startswith("attachment;")
            and downloaded.headers["x-content-type-options"] == "nosniff",
            "attachment headers",
        )
        check((await client.get(raw)).status_code == 401, "anonymous download denied")
        check(
            (await client.get(raw, headers=headers("outsider"))).status_code == 404,
            "cross-store download denied",
        )
        listing = await client.get(
            f"/api/v1/stores/{store_id}/documents",
            headers=headers("viewer"),
            params={"sku_id": "sku_001", "q": "部分到货"},
        )
        check(
            [d["id"] for d in listing.json()["items"]] == [document["id"]],
            "entity and literal title filters",
        )
        repeat = await upload(original, key, metadata)
        check(repeat.status_code == 201 and repeat.json() == document, "exact upload replay")
        check(
            (await upload(original + b"changed", key, metadata)).status_code == 409,
            "same-key content conflict",
        )
        appended = await upload(
            b"# synthetic version 2\n",
            str(uuid4()),
            {"expected_metadata_version": 1},
            prefix + "/versions",
        )
        check(
            appended.status_code == 201
            and appended.json()["latest_version_id"] != document["latest_version_id"],
            "append immutable version",
        )
        check(
            (await client.get(raw, headers=headers("viewer"))).content == original,
            "old original retained after append",
        )
        changed = await client.patch(
            prefix,
            headers=headers(),
            json={"expected_metadata_version": 2, "visibility": "private"},
        )
        check(changed.status_code == 200, "metadata CAS change")
        check(
            (await client.get(raw, headers=headers("viewer"))).status_code == 404,
            "privacy change immediately affects raw reads",
        )
        check(
            (await client.get(raw, headers=headers("admin"))).status_code == 404,
            "admin cannot read another owner's private body",
        )
        check(
            (await client.get(raw, headers=headers())).content == original,
            "owner retains private access",
        )
        archived = await client.post(
            prefix + "/control",
            headers=headers(),
            json={"operation": "archive", "expected_metadata_version": 3},
        )
        check(
            archived.status_code == 200
            and (await client.get(raw, headers=headers())).status_code == 404,
            "archive revokes raw read",
        )
        restored = await client.post(
            prefix + "/control",
            headers=headers(),
            json={"operation": "restore", "expected_metadata_version": 4},
        )
        check(restored.status_code == 200, "restore with CAS")
        runtime = (await client.get("/openapi.json")).json()
        check(
            runtime
            == json.loads((ROOT / "docs/api/backend.runtime.openapi.json").read_text("utf-8")),
            "runtime matches exported contract",
        )
        process.terminate()
        await asyncio.to_thread(process.wait, 10)
        await start()
        check(
            (await client.get(raw, headers=headers())).content == original,
            "API restart preserves original and authorization",
        )
        repeat = await upload(original, key, metadata)
        check(
            repeat.status_code == 201 and repeat.json() == document,
            "API restart preserves idempotency receipt",
        )
        check(
            await counts() == before,
            "document actions create no business event, ledger, action or fake indexing job",
        )
        result = {
            "status": "passed",
            "ran_at": datetime.now(UTC).isoformat(),
            "database": "shopsteward_test",
            "port": 8016,
            "store_id": store_id,
            "document_id": document["id"],
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "checks_passed": len(checks),
            "checks": checks,
            "model_calls": 0,
            "logs": artifacts.relative_to(ROOT).as_posix(),
            "scope": (
                "real TCP HTTP + PostgreSQL + filesystem + API restart; no UI, worker or "
                "semantic search"
            ),
        }
        (ROOT / "docs/api/knowledge-k1-http-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        print(json.dumps({"status": "passed", "checks": len(checks), "model_calls": 0}))
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                await asyncio.to_thread(process.wait, 10)
        for stream in logs:
            stream.close()
        await client.aclose()
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
