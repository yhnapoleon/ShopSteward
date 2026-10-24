"""Opt-in isolated real LangGraph/model -> backend HTTP -> knowledge HTTP acceptance.

Uses existing configured Agent model, at most four runs, each bounded by Runtime.
Never starts Docker Desktop or changes development services. No embedding calls.
"""

import argparse
import asyncio
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
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
BASE = "http://127.0.0.1:8018"


def main():
    from app.core.config import Settings
    from app.db.session import Database
    from app.operations.repository import mark_caught_up
    from tools.import_knowledge_corpus import import_records, prepare_upload
    from tools.knowledge_test_fixture import seed_fixture

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-test", required=True, action="store_true")
    parser.add_argument("--real-model", required=True, action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-report", type=Path)
    args = parser.parse_args()
    previous = json.loads(args.reuse_report.read_text("utf-8")) if args.reuse_report else None
    if args.output.exists():
        parser.error("use a new report path")
    os.chdir(BACKEND)
    settings = Settings()
    if not settings.agent_api_key_file or not Path(settings.agent_api_key_file).is_file():
        parser.error("existing configured Agent key file required")
    url = make_url(settings.database_url.get_secret_value()).set(database="shopsteward_test")
    if url.host not in {"localhost", "127.0.0.1"}:
        parser.error("dedicated local test database required")
    stamp = datetime.now(UTC).strftime("%m%d%H%M%S")
    if previous:
        task = Path(previous["task_directory"]).resolve()
        if (
            previous.get("database") != "shopsteward_test"
            or not task.is_relative_to((ROOT / "var/precloud").resolve())
            or not task.name.startswith("agent-")
        ):
            parser.error("reuse must identify this isolated test fixture")
        stamp = task.name.removeprefix("agent-")
    else:
        task = ROOT / "var/precloud" / ("agent-" + stamp)
        task.mkdir(parents=True, exist_ok=False)
    token = secrets.token_urlsafe(36)
    private = {}
    for line in (ROOT / "var/knowledge-precloud/private.env").read_text("utf-8-sig").splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            private[k] = v.strip().strip("\"'")
    service_key = private["KNOWLEDGE_SERVICE_KEY"]
    processes, streams = [], []
    result = dict(
        started_at=datetime.now(UTC).isoformat(),
        database="shopsteward_test",
        model=settings.agent_model,
        api_mode=settings.agent_api_mode,
        real_model=True,
        real_http=True,
        runs=[],
        checks=[],
        max_agent_runs=4,
        max_model_calls_per_run=8,
        embedding_calls=0,
        backend_port=8018,
        knowledge_port=8020,
        task_directory=str(task),
    )

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")

    def spawn(name, arguments, env):
        stream = (task / (name + ".log")).open("a", encoding="utf-8")
        streams.append(stream)
        process = subprocess.Popen(
            [sys.executable, *arguments],
            cwd=BACKEND,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        processes.append(process)
        return process

    async def run():
        async with httpx.AsyncClient(timeout=10, trust_env=False) as probe:
            (await probe.get("http://127.0.0.1:8020/health/ready")).raise_for_status()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 8018))
        entities = json.loads(
            (ROOT / "docs/evaluation/knowledge-expanded/entities-fixture.json").read_text("utf-8")
        )
        if previous:
            mapping = json.loads((task / "mapping.json").read_text("utf-8"))
        else:
            mapping = await seed_fixture(
                entities, "agent-" + stamp, url.render_as_string(hide_password=False)
            )
            (task / "mapping.json").write_text(json.dumps(mapping, indent=2), "utf-8")
        root = ROOT / "docs/evaluation/knowledge-expanded"
        manifest = json.loads((root / "manifests/pilot.json").read_text("utf-8"))
        prepared = [prepare_upload(row, root, mapping) for row in manifest["documents"]]
        env = os.environ.copy()
        env.update(
            DATABASE_URL=url.render_as_string(hide_password=False),
            APP_ENV="test",
            AGENT_ENABLED="true",
            AGENT_BACKEND_URL=BASE,
            AGENT_MODEL=settings.agent_model,
            AGENT_API_MODE=settings.agent_api_mode,
            AGENT_BASE_URL=settings.agent_base_url,
            AGENT_API_KEY_FILE=settings.agent_api_key_file,
            KNOWLEDGE_SERVICE_ENABLED="true",
            KNOWLEDGE_SERVICE_URL="http://127.0.0.1:8020",
            KNOWLEDGE_SERVICE_KEY=service_key,
            KNOWLEDGE_RETRIEVAL_PROFILE="lexical-v1",
            KNOWLEDGE_STORAGE_ROOT=str(task / "originals"),
            SOURCE_STALE_SECONDS="3600",
            WORKER_POLL_SECONDS="0.3",
            JOB_LEASE_SECONDS="12",
            JOB_HEARTBEAT_SECONDS="3",
            JOB_TIMEOUT_SECONDS="180",
            PYTHONPATH=str(BACKEND),
        )
        env["AUTH_TOKENS"] = json.dumps(
            [
                dict(
                    token=token,
                    principal_id="agent-evidence-" + stamp,
                    kind="user",
                    roles=["operator", "approver"],
                    store_ids=list(mapping["stores"].values()),
                )
            ]
        )
        spawn(
            "api",
            [
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8018",
                "--no-access-log",
            ],
            env,
        )
        spawn("publisher", ["-m", "app.knowledge.publisher"], env)
        async with httpx.AsyncClient(
            base_url=BASE, timeout=60, trust_env=False, headers={"Authorization": "Bearer " + token}
        ) as client:
            for _ in range(100):
                try:
                    (await client.get("/health/ready")).raise_for_status()
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.3)
            print("isolated_backend_ready", flush=True)
            imported = await import_records(
                client,
                prepared,
                token=token,
                receipts_path=task / "import-receipts.json",
                publish=True,
            )
            result["import"] = imported
            save()
            if imported["failures"] or imported["uploaded_versions"] != 200:
                raise ValueError("pilot_import_incomplete")
            print("pilot_200_uploaded_and_published", flush=True)
            db = Database(url.render_as_string(hide_password=False))
            try:
                async with db.session() as session, session.begin():
                    for store in mapping["stores"]:
                        await mark_caught_up(
                            session, "knowledge-test-agent-" + stamp + "-run-" + store, 0
                        )

                async def request(method, path, data=None):
                    response = await client.request(
                        method, path, json=data, headers={"Idempotency-Key": str(uuid4())}
                    )
                    response.raise_for_status()
                    return response.json()

                store = mapping["stores"]["STORE01"]
                mission = (
                    await request("GET", f"/api/v1/missions/{previous['mission_id']}")
                    if previous
                    else await request(
                        "POST",
                        "/api/v1/missions",
                        dict(
                            store_id=store,
                            sku_id=mapping["skus"]["SKU001"],
                            objective="Synthetic evidence acceptance",
                            policy=dict(
                                cash_floor_minor=30000,
                                candidate_quantities=[0, 20, 40, 80],
                                supplier_id=mapping["suppliers"]["SUP01"],
                            ),
                            check_interval_seconds=3600,
                        ),
                    )
                )
                result["mission_id"], result["store_id"] = mission["id"], store
                if mission["store_id"] != store:
                    raise ValueError("reused_mission_store_mismatch")
                spawn("agent", ["-m", "app.worker", "--profile", "agent"], env)
                # Business checks are not needed to demonstrate stock/document evidence;
                # no purchase, plan revision or business worker is requested by these prompts.
                cid = (
                    await request("POST", f"/api/v1/missions/{mission['id']}/conversations", {})
                )["id"]
                cases = [
                    (
                        "business_only",
                        "不用查文档，只查询当前库存和现金；请用业务工具给出数值。",
                        ["get_dashboard"],
                    ),
                    (
                        "document_clause",
                        f"请查供应商文档：商品{mapping['skus']['SKU017']}与{mapping['skus']['SKU018']}新旧条码并存，供货映射怎样交代才完整？请引用有效资料，勿推断采购许可。",
                        ["search_documents"],
                    ),
                    (
                        "expand_evidence",
                        "请展开上一条引用，核对其原文条件。",
                        ["read_document_evidence"],
                    ),
                    (
                        "mixed",
                        f"结合当前库存与供应商文档：商品{mapping['skus']['SKU017']}与{mapping['skus']['SKU018']}新旧条码并存时，能否直接覆盖删除旧码？分别说明业务事实与条款依据。",
                        ["get_dashboard", "search_documents"],
                    ),
                ]
                queued_expand = None
                for label, prompt, required in cases:
                    sent = (
                        queued_expand
                        if label == "expand_evidence"
                        else await request(
                            "POST", f"/api/v1/conversations/{cid}/messages", {"content": prompt}
                        )
                    )
                    rid = sent["agent_run_id"]
                    if label == "document_clause":
                        queued_expand = await request(
                            "POST",
                            f"/api/v1/conversations/{cid}/messages",
                            {"content": cases[2][1]},
                        )
                        result["expansion_queued_before_previous_answer"] = True
                    for _ in range(300):
                        item = await request("GET", f"/api/v1/agent-runs/{rid}")
                        if item["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "WAITING_INPUT"}:
                            break
                        await asyncio.sleep(0.5)
                    output = item.get("output") or {}
                    completed = output.get("completed_tools", [])
                    ordered = [name for name in completed if name in required] == required
                    actual = [t.get("tool") for t in item.get("tools", [])]
                    passed = (
                        item["status"] == "SUCCEEDED"
                        and ordered
                        and all(t in completed for t in required)
                        and (
                            label != "business_only"
                            or not set(actual) & {"search_documents", "read_document_evidence"}
                        )
                        and (
                            label == "business_only"
                            or any(
                                r.get("type") == "document" for r in output.get("references", [])
                            )
                        )
                    )
                    result["runs"].append(
                        dict(
                            scenario=label,
                            prompt=prompt,
                            expected_tools=required,
                            passed=passed,
                            run=item,
                        )
                    )
                    save()
                    print(label + ": " + ("PASS" if passed else item["status"]), flush=True)
                    if item["status"] not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                        break
            finally:
                await db.dispose()

    try:
        asyncio.run(run())
    except Exception as exc:
        result["execution_error_type"] = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            result["http_error_status"] = exc.response.status_code
        print("acceptance_error:" + type(exc).__name__, flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        for stream in streams:
            stream.close()
        result["passed"] = (
            len(result["runs"]) == 4
            and all(r["passed"] for r in result["runs"])
            and "execution_error_type" not in result
        )
        result["finished_at"] = datetime.now(UTC).isoformat()
        save()
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
