"""Opt-in real-model process acceptance against a dedicated synthetic database.

Run from backend with ../.venv/Scripts/python.exe tools/verify_agent.py.
Requires the explicitly authorized local key file; never prints configuration secrets.
"""

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

import asyncpg
import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests/integration")]
DB_NAME = "shopsteward_agent_acceptance"
PORT = 8024
BASE = f"http://127.0.0.1:{PORT}"
RESULT = ROOT / "docs/api/agent-v1-process-result.json"
REPORT = ROOT / "docs/reports/agent-v1-process-report.md"


async def prepare(url):
    from test_missions import fresh_seed
    from test_operations import initialize

    from app.db.session import Database
    from app.operations.repository import mark_caught_up

    conn = await asyncpg.connect(
        make_url(url)
        .set(drivername="postgresql", database="postgres")
        .render_as_string(hide_password=False)
    )
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", DB_NAME):
            await conn.execute(f'CREATE DATABASE "{DB_NAME}"')
    finally:
        await conn.close()
    return Database(url), fresh_seed(), initialize, mark_caught_up


def main():
    from app.core.config import Settings

    os.chdir(BACKEND)
    settings = Settings()
    url = (
        make_url(settings.database_url.get_secret_value())
        .set(database=DB_NAME)
        .render_as_string(hide_password=False)
    )
    token = secrets.token_urlsafe(36)
    env = os.environ.copy()
    env.update(
        DATABASE_URL=url,
        APP_ENV="test",
        AGENT_ENABLED="true",
        AGENT_MODEL="gpt-4.1-mini",
        AGENT_BASE_URL="https://api.openai.com/v1",
        AGENT_BACKEND_URL=BASE,
        AGENT_API_KEY_FILE=str(ROOT.parent / "openai.txt"),
        SOURCE_STALE_SECONDS="3600",
        WORKER_POLL_SECONDS="0.3",
        JOB_LEASE_SECONDS="12",
        JOB_HEARTBEAT_SECONDS="3",
        JOB_TIMEOUT_SECONDS="180",
    )
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), str(ROOT / "agent/src")])
    result = {
        "suite": (
            "recovery"
            if "--recovery" in sys.argv
            else "knowledge"
            if "--knowledge-only" in sys.argv
            else "full"
        ),
        "started_at": datetime.now(UTC).isoformat(),
        "database": DB_NAME,
        "model": env["AGENT_MODEL"],
        "endpoint": env["AGENT_BASE_URL"],
        "checks": [],
        "runs": [],
        "limitations": [],
    }
    if RESULT.exists():
        previous = json.loads(RESULT.read_text(encoding="utf-8"))
        result["prior_attempts"] = previous.get("prior_attempts", []) + [
            {k: v for k, v in previous.items() if k != "prior_attempts"}
        ]
    processes, logs = [], []

    def check(name, passed, **evidence):
        result["checks"].append({"name": name, "passed": bool(passed), **evidence})
        print(name + ": " + ("PASS" if passed else "FAIL"), flush=True)

    def spawn(name, args):
        log = (ROOT / "var" / f"agent-acceptance-{name}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(
            [sys.executable, *args],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        processes.append(process)
        return process

    async def execute():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", PORT))
        db, seed, initialize, caught_up = await prepare(url)
        result["store_id"] = seed["store_id"]
        env["AUTH_TOKENS"] = json.dumps(
            [
                {
                    "token": token,
                    "principal_id": "acceptance-owner",
                    "roles": ["operator", "approver"],
                    "store_ids": [seed["store_id"]],
                }
            ]
        )
        migration = spawn("migration", ["-m", "alembic", "upgrade", "head"])
        await asyncio.to_thread(migration.wait, timeout=60)
        if migration.returncode:
            raise RuntimeError("migration_failed")
        await initialize(db, seed)
        async with db.session() as session, session.begin():
            await caught_up(session, seed["scenario_run_id"], 0)
            result["schema_revision"] = await session.scalar(
                text("SELECT version_num FROM alembic_version")
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
                str(PORT),
                "--no-access-log",
            ],
        )
        agent = spawn("worker", ["-m", "app.worker", "--profile", "agent"])
        business = spawn("business", ["-m", "app.worker"])

        async def request(method, path, payload=None):
            # A fresh connection for each request proves the job outlives the request.
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as client:
                response = await client.request(
                    method,
                    path,
                    json=payload,
                    headers={"Authorization": "Bearer " + token, "Idempotency-Key": str(uuid4())},
                )
            if response.is_error:
                raise RuntimeError(f"http_{response.status_code}_{path}: {response.text[:350]}")
            return response.json()

        for _ in range(100):
            try:
                await request("GET", "/health/live")
                break
            except (httpx.HTTPError, RuntimeError):
                await asyncio.sleep(0.3)
        from test_missions import body

        mission = await request("POST", "/api/v1/missions", body(seed))
        mid = mission["id"]
        result["mission_id"] = mid
        for _ in range(100):
            mission = await request("GET", f"/api/v1/missions/{mid}")
            if mission.get("current_plan_id"):
                break
            await asyncio.sleep(0.3)
        business.terminate()
        business.wait(timeout=10)
        check("independent_business_plan", bool(mission.get("current_plan_id")))

        async def conversation():
            return (await request("POST", f"/api/v1/missions/{mid}/conversations", {}))["id"]

        async def poll(rid):
            for _ in range(420):
                run = await request("GET", f"/api/v1/agent-runs/{rid}")
                if run["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "WAITING_INPUT"}:
                    return run
                await asyncio.sleep(0.5)
            raise RuntimeError("run_timeout_" + rid)

        async def ask(label, prompt, cid=None):
            cid = cid or await conversation()
            sent = await request(
                "POST", f"/api/v1/conversations/{cid}/messages", {"content": prompt}
            )
            run = await poll(sent["agent_run_id"])
            result["runs"].append({"scenario": label, "prompt": prompt, **run})
            check(label, run["status"] == "SUCCEEDED", run_id=run["id"], status=run["status"])
            return run

        if result["suite"] == "recovery":

            async def send(cid, prompt):
                return (
                    await request(
                        "POST", f"/api/v1/conversations/{cid}/messages", {"content": prompt}
                    )
                )["agent_run_id"]

            async def running(rid):
                for _ in range(150):
                    run = await request("GET", f"/api/v1/agent-runs/{rid}")
                    if run["status"] == "RUNNING":
                        return True
                    if run["status"] not in {"QUEUED", "RUNNING"}:
                        return False
                    await asyncio.sleep(0.1)
                return False

            async def assistant_count(rid):
                async with db.session() as session:
                    return await session.scalar(
                        text(
                            "SELECT count(*) FROM agent_messages WHERE run_id=:rid "
                            "AND role='assistant'"
                        ),
                        {"rid": rid},
                    )

            cid = await conversation()
            rid = await send(cid, "请读取当前方案和任务，解释40件与80件的区别。")
            observed = await running(rid)
            check("crash_observed_running", observed, run_id=rid)
            if not observed:
                raise RuntimeError("crash_could_not_observe_running")
            agent.kill()
            await asyncio.to_thread(agent.wait, timeout=10)
            await asyncio.sleep(14)
            agent = spawn("worker-restarted", ["-m", "app.worker", "--profile", "agent"])
            recovered = await poll(rid)
            result["runs"].append({"scenario": "worker_kill_lease_recovery", **recovered})
            async with db.session() as session:
                attempts = await session.scalar(
                    text(
                        "SELECT j.attempt_count FROM job_runs j JOIN agent_runs r ON r.job_id=j.id "
                        "WHERE r.id=:rid"
                    ),
                    {"rid": rid},
                )
            check(
                "worker_kill_lease_recovery",
                recovered["status"] == "SUCCEEDED"
                and attempts >= 2
                and await assistant_count(rid) == 1,
                run_id=rid,
                attempt_count=attempts,
                assistant_messages=await assistant_count(rid),
            )

            second = spawn("worker-second", ["-m", "app.worker", "--profile", "agent"])
            cid = await conversation()
            first_id = await send(cid, "请读取当前方案，简短解释推荐采购量。")
            second_id = await send(cid, "请读取当前任务，简短解释现金底线。")
            pair = [await poll(first_id), await poll(second_id)]
            for index, run in enumerate(pair, 1):
                result["runs"].append({"scenario": f"two_workers_message_{index}", **run})
            counts = [await assistant_count(first_id), await assistant_count(second_id)]
            check(
                "two_workers_same_conversation_once_each",
                all(r["status"] == "SUCCEEDED" for r in pair) and counts == [1, 1],
                run_ids=[first_id, second_id],
                assistant_message_counts=counts,
            )
            second.terminate()
            await asyncio.to_thread(second.wait, timeout=10)

            cid = await conversation()
            cancel_id = await send(
                cid, "请读取当前任务、方案和经营仪表盘，详细解释所有候选采购量。"
            )
            observed = await running(cancel_id)
            cancelled = await request("POST", f"/api/v1/agent-runs/{cancel_id}/cancel")
            await asyncio.sleep(4)
            cancelled = await request("GET", f"/api/v1/agent-runs/{cancel_id}")
            result["runs"].append({"scenario": "cancel_running", **cancelled})
            check(
                "cancel_running_no_assistant",
                observed
                and cancelled["status"] == "CANCELLED"
                and await assistant_count(cancel_id) == 0,
                run_id=cancel_id,
                assistant_messages=await assistant_count(cancel_id),
            )

            cid = await conversation()
            clarify_id = await send(
                cid,
                "请先调用clarify工具询问我想查看当前方案还是现金状况。"
                "必须等我回复后再继续，不要猜测选择。",
            )
            paused = await poll(clarify_id)
            result["runs"].append({"scenario": "model_clarification", **paused})
            check(
                "model_requested_clarification",
                paused["status"] == "WAITING_INPUT",
                run_id=clarify_id,
                interrupt_id=paused.get("interrupt_id"),
            )
            if paused["status"] == "WAITING_INPUT":
                await request(
                    "POST",
                    f"/api/v1/agent-runs/{clarify_id}/resume",
                    {
                        "interrupt_id": paused["interrupt_id"],
                        "content": "查看当前方案，请读取真实方案并说明推荐量。",
                    },
                )
                resumed = await poll(clarify_id)
                result["runs"].append({"scenario": "clarification_resumed", **resumed})
                check(
                    "clarification_resume_same_run_once",
                    resumed["status"] == "SUCCEEDED" and await assistant_count(clarify_id) == 1,
                    run_id=clarify_id,
                    assistant_messages=await assistant_count(clarify_id),
                )
            result["limitations"].append(
                "Recovery coverage: owned process kill after observed RUNNING, real lease expiry, "
                "two workers, running cancellation, and model clarification/resume. "
                "Memory commit followed by lost HTTP response was not fault-injected."
            )
            await db.dispose()
            return

        for i in range(0 if result["suite"] == "knowledge" else 3):
            run = await ask(
                f"plan_explanation_{i + 1}",
                "请读取当前真实方案，解释为什么建议买40件而不是80件，列明现金底线和80件被拒原因。",
            )
            cards = (run.get("output") or {}).get("cards", [])
            valid = any(
                c.get("proposed_purchase", {}).get("quantity") == 40
                and any(
                    x["quantity"] == 80 and not x["feasible"] and x["rejection_reasons"]
                    for x in c["candidates"]
                )
                for c in cards
            )
            check(f"authoritative_plan_card_{i + 1}", valid, cards=cards)
        for kind, save, read, correct, delete in [
            (
                "USER",
                "请长期记住我的通用偏好：回答先给一句结论，再列三条理由。",
                "我有什么已保存的通用回答偏好？请按偏好解释当前方案。",
                "请纠正已保存的通用偏好：改成先给结论，再列两条理由。",
                "请删除刚才保存的先给结论再列理由这条通用偏好。",
            ),
            (
                "SKILL",
                "请长期保存补货任务流程：先查现金底线，再解释候选方案。作为SKILL，task_type=replenishment。",
                "我的补货任务流程是什么？请按已保存的流程解释当前方案。",
                "请纠正补货任务SKILL：先看库存，再查现金底线，最后解释候选方案。",
                "请删除刚才保存的补货任务流程SKILL。",
            ),
        ]:
            for phase, prompt in [
                ("save", save),
                ("read_new_conversation", read),
                ("correct", correct),
                ("delete", delete),
            ]:
                knowledge_run = await ask(f"knowledge_{kind}_{phase}", prompt)
                snapshot = await request(
                    "GET", f"/api/v1/stores/{seed['store_id']}/agent-knowledge"
                )
                result.setdefault("knowledge_snapshots", []).append(
                    {"kind": kind, "phase": phase, **snapshot}
                )
                scope = next((s for s in snapshot["items"] if s["kind"] == kind), {})
                if phase == "read_new_conversation":
                    check(
                        f"knowledge_{kind}_read_current_plan",
                        any(
                            t["tool"] == "get_plan" and t["ok"]
                            for t in knowledge_run.get("tools", [])
                        ),
                        run_id=knowledge_run["id"],
                    )
                if phase != "read_new_conversation":
                    check(
                        f"knowledge_{kind}_{phase}_persisted",
                        scope.get("version") == {"save": 1, "correct": 2, "delete": 3}[phase]
                        and bool(scope.get("entries")) == (phase != "delete"),
                    )
        if result["suite"] == "knowledge":
            result["limitations"].append(
                "Focused knowledge rerun; other checks remain in prior_attempts."
            )
            await db.dispose()
            return
        before = await request("GET", f"/api/v1/missions/{mid}")
        cid = await conversation()
        await ask(
            "hypothetical_max20",
            "如果假设这次最多买20件，会怎样？仅做只读试算，不要修改方案。",
            cid,
        )
        after = await request("GET", f"/api/v1/missions/{mid}")
        check("hypothetical_no_mission_mutation", before == after)
        await ask(
            "explicit_revise_max20",
            "现在明确修改这一次的方案：本次最多采购20件，请生成新的待确认版本，不要执行采购。",
            cid,
        )
        revised = await request("GET", f"/api/v1/missions/{mid}")
        check(
            "revision_new_pending_plan",
            revised.get("current_plan_id") != before.get("current_plan_id"),
            before_plan=before.get("current_plan_id"),
            after_plan=revised.get("current_plan_id"),
        )

        # Follow-up uses controlled due timestamps, with a real >=65 second unchanged window.
        from sqlalchemy import func, select

        from app.agent_bridge.models import AgentRun, Conversation
        from app.missions.models import MissionRow  # noqa: F401

        follow = await conversation()
        await request(
            "PATCH",
            f"/api/v1/conversations/{follow}/followup",
            {"enabled": True, "expected_version": 1, "interval_seconds": 60},
        )
        async with db.session() as session, session.begin():
            row = await session.get(Conversation, follow)
            row.next_due = await session.scalar(select(func.clock_timestamp()))
        for _ in range(100):
            async with db.session() as session:
                rid = await session.scalar(
                    select(AgentRun.id).where(AgentRun.conversation_id == follow)
                )
            if rid:
                break
            await asyncio.sleep(0.3)
        if rid:
            run = await poll(rid)
            result["runs"].append({"scenario": "followup_initial", **run})
            check("background_followup", run["status"] == "SUCCEEDED", run_id=rid)
            await asyncio.sleep(35)
            await asyncio.sleep(30)
            async with db.session() as session:
                count = await session.scalar(
                    select(func.count())
                    .select_from(AgentRun)
                    .where(AgentRun.conversation_id == follow)
                )
            check("unchanged_no_repeat_65_seconds", count == 1, run_count=count)
            from test_operations import event, ingest

            await ingest(db, seed, [event(seed, quantity=1)])
            async with db.session() as session, session.begin():
                row = await session.get(Conversation, follow)
                row.next_due = await session.scalar(select(func.clock_timestamp()))
            changed_id = None
            for _ in range(100):
                async with db.session() as session:
                    changed_id = await session.scalar(
                        select(AgentRun.id).where(
                            AgentRun.conversation_id == follow, AgentRun.id != rid
                        )
                    )
                if changed_id:
                    break
                await asyncio.sleep(0.3)
            if changed_id:
                changed = await poll(changed_id)
                result["runs"].append({"scenario": "followup_changed_stock", **changed})
                check(
                    "changed_stock_background_run",
                    changed["status"] == "SUCCEEDED",
                    run_id=changed_id,
                    controlled_due_timestamp=True,
                )
            else:
                check("changed_stock_background_run", False)
        else:
            check("background_followup", False)
        result["limitations"].append(
            "Crash/lease recovery, waiting-input resume, and adversarial failure scenarios "
            "are not covered by this bounded real-model run; consult separate integration tests."
        )
        await db.dispose()

    try:
        asyncio.run(execute())
    except Exception as exc:
        # Never persist raw connection errors or traceback locals.
        result["fatal_error"] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("Acceptance stopped: " + type(exc).__name__, flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        for log in logs:
            log.close()
        result["finished_at"] = datetime.now(UTC).isoformat()
        unique_runs = {r["id"]: r for r in result["runs"]}
        usages = [(r.get("output") or {}).get("usage") for r in unique_runs.values()]
        result["usage_totals"] = {
            k: sum(u.get(k, 0) for u in usages if isinstance(u, dict))
            for k in ("input_tokens", "output_tokens", "total_tokens")
        }
        result["usage_unknown_runs"] = sum(not isinstance(u, dict) for u in usages)
        result["cumulative_usage_totals"] = {
            key: value
            + sum(
                attempt.get("usage_totals", {}).get(key, 0)
                for attempt in result.get("prior_attempts", [])
            )
            for key, value in result["usage_totals"].items()
        }
        result["cumulative_usage_unknown_runs"] = result["usage_unknown_runs"] + sum(
            attempt.get("usage_unknown_runs", 0) for attempt in result.get("prior_attempts", [])
        )
        result["success"] = (
            bool(result["checks"])
            and all(c["passed"] for c in result["checks"])
            and "fatal_error" not in result
        )
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            "# Agent v1 real process acceptance",
            "",
            f"Status: {'PASS' if result['success'] else 'INCOMPLETE / FAIL'}",
            f"Suite: {result['suite']}; retained prior attempts: "
            f"{len(result.get('prior_attempts', []))}",
            f"Model: {result['model']}; database: `{DB_NAME}`",
            "",
            "Independent API, business worker, and Agent worker processes. Synthetic store only. "
            "Each message request closes its connection before durable Run polling.",
            "",
            "| Check | Result |",
            "|---|---|",
        ]
        lines += [
            f"| {c['name']} | {'PASS' if c['passed'] else 'FAIL'} |" for c in result["checks"]
        ]
        lines += ["", *result["limitations"]]
        if "fatal_error" in result:
            lines += ["", "Stopped: " + result["fatal_error"]]
        lines += [
            "",
            "Detailed prompts, Run IDs, model output, authoritative cards, and usage are preserved "
            "in `docs/api/agent-v1-process-result.json`. Owned processes have been stopped; "
            "synthetic data is retained for review.",
        ]
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
