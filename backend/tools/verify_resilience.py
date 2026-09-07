"""B0-07 owned-process acceptance; run with the repository's .venv Python.

Requires migrated development databases and ignored backend/simulation .env files.
Creates a new SC01 world, retains its data and logs, and stops only owned processes.
Faults live in this harness's forwarding proxies; production services are unmodified.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.operations.client import SimulationClient  # noqa: E402

RESULT = ROOT / "docs/api/b0-07-process-result.json"
API = "http://127.0.0.1:8010"
SIM = "http://127.0.0.1:8011"
OVERRIDES = {
    "SIMULATION_BASE_URL": SIM,
    "JOB_LEASE_SECONDS": "6",
    "JOB_HEARTBEAT_SECONDS": "2",
    "WORKER_POLL_SECONDS": "0.2",
    "WORKER_CONCURRENCY": "4",
    "SOURCE_STALE_SECONDS": "8",
}


class CheckFailed(RuntimeError):
    """Only literal, credential-free explanations are written to the evidence."""


def require(condition, explanation):
    if not condition:
        raise CheckFailed(explanation)


class SourceBarrier:
    def __init__(self):
        self.lock = threading.Lock()
        self.reached = threading.Event()
        self.release = threading.Event()
        self.run_id = None
        self.worker = None

    def intercept(self, worker, path):
        with self.lock:
            chosen = (
                self.run_id is not None
                and path.startswith(f"/sim/v1/runs/{self.run_id}/events?")
                and not self.reached.is_set()
            )
            if chosen:
                self.worker = worker
                self.reached.set()
        if chosen:
            # Bounded even when the acceptance fails before explicitly releasing it.
            self.release.wait(15)


def proxy_handler(worker, barrier):
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log Authorization headers or HTTP bodies.

        def forward(self):
            barrier.intercept(worker, self.path)
            connection = HTTPConnection("127.0.0.1", 8011, timeout=12)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else None
                headers = {
                    key: value
                    for key, value in self.headers.items()
                    if key.lower() not in {"host", "connection", "transfer-encoding"}
                }
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (OSError, TimeoutError):
                try:
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except OSError:
                    pass
            finally:
                connection.close()

        do_GET = forward
        do_POST = forward

    return Proxy


class Processes:
    def __init__(self, record):
        self.record = record
        self.live = {}
        self.all = []
        self.streams = []
        self.logs = ROOT / "var" / ("b0-07-" + uuid4().hex)
        self.logs.mkdir(parents=True)
        record["logs_directory"] = str(self.logs)
        record["owned_processes"] = []

    def start(self, name):
        require(name not in self.live, "Attempt to start an already owned process")
        env = os.environ.copy()
        env.update(OVERRIDES)
        if name.startswith("worker"):
            port = 8012 if name == "worker1" else 8013
            env["SIMULATION_BASE_URL"] = f"http://127.0.0.1:{port}"
            command, directory = ["-m", "app.worker"], "backend"
        else:
            module, port, directory = (
                ("app.main:app", 8010, "backend")
                if name == "api"
                else ("simulator.main:app", 8011, "simulation")
            )
            command = [
                "-m",
                "uvicorn",
                module,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ]
        stream = (self.logs / f"{len(self.all):02d}-{name}.log").open("w", encoding="utf-8")
        self.streams.append(stream)
        process = subprocess.Popen(
            [sys.executable, *command],
            cwd=ROOT / directory,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        row = {"name": name, "pid": process.pid, "started_at": datetime.now(UTC).isoformat()}
        self.record["owned_processes"].append(row)
        self.all.append((process, row))
        self.live[name] = process

    async def stop(self, name, *, kill=False):
        process = self.live.pop(name, None)
        if process is None:
            return
        if process.poll() is None:
            process.kill() if kill else process.terminate()
        try:
            await asyncio.to_thread(process.wait, timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait, timeout=5)
        row = next(row for item, row in self.all if item is process)
        row.update(stopped_at=datetime.now(UTC).isoformat(), exit_code=process.returncode)
        if kill:
            row["fault_kill"] = True

    async def close(self):
        for name in list(reversed(self.live)):
            await self.stop(name)
        for stream in self.streams:
            stream.close()
        self.record["owned_processes_stopped_after_acceptance"] = all(
            process.poll() is not None for process, _ in self.all
        )


async def until(predicate, description, seconds=30):
    try:
        async with asyncio.timeout(seconds):
            while True:
                found = await predicate()
                if found:
                    return found
                await asyncio.sleep(0.2)
    except TimeoutError:
        raise CheckFailed("Timed out waiting for " + description) from None


async def acceptance(record, processes, barrier):
    settings = Settings(
        _env_file=ROOT / "backend/.env", simulation_base_url=SIM, source_stale_seconds=8
    )
    require(settings.database_url is not None, "Development database is not configured")
    grant = next((g for g in settings.auth_tokens if g.kind == "user" and "admin" in g.roles), None)
    require(grant is not None, "Configured admin credential is required")
    db = Database(settings.database_url.get_secret_value())
    sim = SimulationClient(settings)

    async def rows(sql, **params):
        async with db.session() as session:
            return [dict(row) for row in (await session.execute(text(sql), params)).mappings()]

    try:
        require(await db.ready(), "Development backend migrations are not at the expected head")
        existing = await rows(
            "SELECT worker_id FROM worker_heartbeats WHERE status='RUNNING' "
            "AND heartbeat_at > clock_timestamp() - interval '12 seconds'"
        )
        require(not existing, "An existing worker is active; no existing process was stopped")
        for name in ("simulator", "api", "worker1", "worker2"):
            processes.start(name)
        async with httpx.AsyncClient(
            base_url=API,
            timeout=10,
            trust_env=False,
            headers={"Authorization": "Bearer " + grant.token.get_secret_value()},
        ) as client:

            async def ready():
                require(
                    all(p.poll() is None for p in processes.live.values()),
                    "An owned service exited unexpectedly; inspect retained local logs",
                )
                try:
                    return all(
                        response.status_code == 200
                        for response in await asyncio.gather(
                            client.get(API + "/health/ready"), client.get(SIM + "/health/ready")
                        )
                    )
                except httpx.HTTPError:
                    return False

            async def request(method, path, expected=200, **kwargs):
                response = await client.request(method, path, **kwargs)
                require(
                    response.status_code == expected,
                    f"Unexpected HTTP status {response.status_code} for {method} {path}",
                )
                return response.json()

            async def post(path, body, expected=202, key=None):
                return await request(
                    "POST",
                    path,
                    expected,
                    json=body,
                    headers={"Idempotency-Key": key or str(uuid4())},
                )

            async def wait_job(identifier):
                async def done():
                    job = await request("GET", "/api/v1/job-runs/" + identifier)
                    require(job["status"] not in {"FAILED", "CANCELLED"}, "A required job failed")
                    return job if job["status"] == "SUCCEEDED" else None

                return await until(done, "job completion")

            await until(ready, "service readiness")
            record["phase"] = "initialize"
            job = await wait_job(
                (await post("/dev/v1/scenarios", {"scenario": "SC01"}))["job_run_id"]
            )
            refs = job["result"]["references"]
            store_id = next(r["id"] for r in refs if r["type"] == "store")
            run_id = next(r["id"] for r in refs if r["type"] == "scenario")
            record.update(store_id=store_id, scenario_run_id=run_id)
            active_started = time.monotonic()
            record["activity_started_at"] = datetime.now(UTC).isoformat()

            async def dashboard():
                return await request("GET", "/api/v1/dashboard", params={"store_id": store_id})

            async def caught_up(sequence):
                async def fresh():
                    cursor = (
                        await rows(
                            "SELECT last_sequence FROM source_cursors WHERE scenario_run_id=:id",
                            id=run_id,
                        )
                    )[0]
                    dash = await dashboard()
                    if (
                        cursor["last_sequence"] >= sequence
                        and dash["freshness"]["status"] == "FRESH"
                    ):
                        return dash["state"]
                    return None

                return await until(fresh, "fresh source catch-up")

            await caught_up(0)
            catalog = await request("GET", "/api/v1/catalog", params={"store_id": store_id})
            offer = catalog["offers"][0]
            mission = await post(
                "/api/v1/missions",
                {
                    "store_id": store_id,
                    "sku_id": offer["sku_id"],
                    "objective": "B0-07 concurrent approvals and owned-process resilience",
                    "policy": {
                        "cash_floor_minor": 30000,
                        "candidate_quantities": [0, 20, 40, 80],
                        "supplier_id": offer["supplier_id"],
                    },
                    "check_interval_seconds": 5,
                },
                201,
            )
            mission_id = mission["id"]
            record["mission_id"] = mission_id
            record["manual_check_requests"] = 0
            record["concurrent_approval_rounds"] = []

            async def purchase(quantity):
                async def proposed():
                    current = await request("GET", "/api/v1/missions/" + mission_id)
                    if not current["current_plan_id"]:
                        return None
                    plan = await request("GET", "/api/v1/plans/" + current["current_plan_id"])
                    if (
                        plan["status"] == "PENDING_APPROVAL"
                        and plan["proposed_purchase"]
                        and plan["proposed_purchase"]["quantity"] == quantity
                    ):
                        return plan
                    return None

                plan = await until(proposed, "automatic purchase proposal")
                body = {
                    "decision": "approve",
                    "expected_plan_version": plan["plan_version"],
                    "expected_state_version": plan["state_version"],
                    "proposal_hash": plan["proposal_hash"],
                }
                key, started = str(uuid4()), time.monotonic()
                gate = asyncio.Event()

                async def approve():
                    await gate.wait()
                    return await post(f"/api/v1/plans/{plan['id']}/decision", body, key=key)

                calls = [asyncio.create_task(approve()) for _ in range(8)]
                gate.set()
                approvals = await asyncio.gather(*calls)
                require(
                    all(a == approvals[0] for a in approvals), "Exact concurrent approvals diverged"
                )
                accepted = approvals[0]
                record["concurrent_approval_rounds"].append(
                    {
                        "quantity": quantity,
                        "requests": 8,
                        "identical_responses": True,
                        "plan_id": plan["id"],
                        "action_id": accepted["action_id"],
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    }
                )
                await wait_job(accepted["job_run_id"])
                action = await request("GET", "/api/v1/actions/" + accepted["action_id"])
                require(action["status"] == "SUCCEEDED", "Approved purchase did not succeed")
                return action

            record["phase"] = "automatic_sc01"
            first = await purchase(40)
            record["actions"] = [first]
            await caught_up(1)
            advance = f"/dev/v1/scenarios/{run_id}/advance"
            await wait_job((await post(advance, {"steps": 1}))["job_run_id"])
            first_goods = await caught_up(2)
            require(first_goods["stocks"][0]["on_hand"] == 60, "First goods receipt was incorrect")
            await wait_job((await post(advance, {"steps": 2}))["job_run_id"])
            revised = await caught_up(4)
            require(
                (revised["stocks"][0]["on_hand"], revised["stocks"][0]["remaining_demand"])
                == (50, 70),
                "Sale and demand revision were not applied",
            )
            second = await purchase(20)
            record["actions"].append(second)
            await caught_up(5)
            await wait_job((await post(advance, {"steps": 1}))["job_run_id"])
            final = await caught_up(6)
            require(
                (
                    final["cash_minor"],
                    final["reserved_cash_minor"],
                    final["receivables_minor"],
                    final["stocks"][0]["on_hand"],
                    final["stocks"][0]["in_transit"],
                )
                == (40000, 0, 20000, 70, 0),
                "SC01 final accounting is incorrect",
            )
            record["final_state"] = final

            record["phase"] = "running_source_worker_kill"
            barrier.run_id = run_id

            async def intercepted():
                return barrier.reached.is_set()

            await until(intercepted, "target source request at test barrier", seconds=15)
            killed_job = await rows(
                "SELECT id,status,attempt_count,lease_until,lease_token FROM job_runs "
                "WHERE store_id=:id AND job_type='sync_events' AND status='RUNNING'",
                id=store_id,
            )
            require(len(killed_job) == 1, "Barrier did not identify exactly one RUNNING source job")
            original = killed_job[0]
            killed_at = datetime.now(UTC)
            killed_started = time.monotonic()
            worker = barrier.worker
            await processes.stop(worker, kill=True)
            barrier.release.set()

            async def recovered():
                row = (
                    await rows(
                        "SELECT id,status,attempt_count,finished_at,error_code "
                        "FROM job_runs WHERE id=:id",
                        id=original["id"],
                    )
                )[0]
                require(row["status"] != "FAILED", "Killed source job exhausted its retries")
                return row if row["status"] == "SUCCEEDED" else None

            restored_job = await until(recovered, "expired lease recovery", seconds=20)
            require(
                restored_job["attempt_count"] > original["attempt_count"],
                "Original job was not retried",
            )
            require(
                restored_job["finished_at"] >= original["lease_until"],
                "Job recovered before lease expiry",
            )
            record["worker_kill"] = {
                "worker": worker,
                "job_id": original["id"],
                "observed_status": original["status"],
                "killed_at": killed_at,
                "lease_until": original["lease_until"],
                "attempts_before": original["attempt_count"],
                "recovered_job": restored_job,
                "elapsed_seconds": round(time.monotonic() - killed_started, 3),
                "same_job_id_recovered_by_surviving_worker": True,
            }
            processes.start(worker)
            await caught_up(6)

            record["phase"] = "simulator_outage"
            outage_started = time.monotonic()
            await processes.stop("simulator", kill=True)

            async def stale():
                dash = await dashboard()
                alerts = await request("GET", "/api/v1/alerts", params={"store_id": store_id})
                active = [
                    a
                    for a in alerts["items"]
                    if a["type"] == "DATA_STALE" and a["status"] != "RESOLVED"
                ]
                if dash["freshness"]["status"] == "STALE" and active:
                    return {"freshness": dash["freshness"], "alert_ids": [a["id"] for a in active]}
                return None

            stale_evidence = await until(stale, "STALE dashboard and DATA_STALE alert", seconds=25)
            # The actual stopped duration, rather than last_success_at age, exceeds the threshold.
            await asyncio.sleep(max(0, 8.5 - (time.monotonic() - outage_started)))
            record["source_outage"] = {
                "stopped_seconds": round(time.monotonic() - outage_started, 3),
                "source_stale_seconds": 8,
                "stale_evidence": stale_evidence,
            }
            processes.start("simulator")
            await until(ready, "simulator restart readiness")
            await caught_up(6)

            async def alerts_recovered():
                alerts = await request("GET", "/api/v1/alerts", params={"store_id": store_id})
                target = [a for a in alerts["items"] if a["id"] in stale_evidence["alert_ids"]]
                return target if target and all(a["status"] == "RESOLVED" for a in target) else None

            resolved = await until(alerts_recovered, "fresh evidence resolves DATA_STALE")
            record["source_outage"]["resolved_alert_ids"] = [a["id"] for a in resolved]
            record["source_outage"]["freshness_after"] = (await dashboard())["freshness"]

            record["phase"] = "both_workers_down"
            await processes.stop("worker1", kill=True)
            await processes.stop("worker2", kill=True)
            schedule = (await rows("SELECT * FROM schedules WHERE mission_id=:id", id=mission_id))[
                0
            ]
            downtime_started = time.monotonic()
            await asyncio.sleep(11.5)
            stopped_schedule = (
                await rows("SELECT * FROM schedules WHERE mission_id=:id", id=mission_id)
            )[0]
            require(
                stopped_schedule == schedule, "Schedule advanced with both owned workers stopped"
            )
            restart_at = datetime.now(UTC)
            stopped_seconds = time.monotonic() - downtime_started
            for name in ("worker1", "worker2"):
                processes.start(name)

            async def schedule_resumed():
                current = (
                    await rows(
                        "SELECT *,clock_timestamp() AS observed_at "
                        "FROM schedules WHERE mission_id=:id",
                        id=mission_id,
                    )
                )[0]
                return current if current["next_run_at"] > current["observed_at"] else None

            following = await until(schedule_resumed, "schedule resumes at future fixed anchor")
            jump = (following["next_run_at"] - schedule["next_run_at"]).total_seconds()
            require(
                jump >= 10 and abs(jump % 5) < 0.001,
                "Downtime recovery changed the five-second anchor",
            )
            occurrences = await rows(
                "SELECT id,scheduled_for,status FROM job_runs WHERE mission_id=:id "
                "AND trigger_source='INTERVAL' AND scheduled_for >= :anchor "
                "AND scheduled_for < :restart ORDER BY scheduled_for",
                id=mission_id,
                anchor=schedule["next_run_at"],
                restart=restart_at,
            )
            require(
                len(occurrences) <= 1, "Downtime replayed each missed interval instead of merging"
            )
            record["worker_downtime"] = {
                "stopped_seconds": round(stopped_seconds, 3),
                "elapsed_including_restart_seconds": round(time.monotonic() - downtime_started, 3),
                "schedule_before": schedule,
                "schedule_after": following,
                "anchor_jump_seconds": jump,
                "missed_interval_job_rows": occurrences,
                "schedule_unchanged_while_stopped": True,
                "fixed_anchor_preserved": True,
            }
            await caught_up(6)

            record["phase"] = "continuous_observation"
            samples = []
            while time.monotonic() - active_started < 90:
                dash = await dashboard()
                state = dash["state"]
                require(state == final, "Business state changed during continuous observation")
                require(
                    all(p.poll() is None for p in processes.live.values()),
                    "Owned service exited during observation",
                )
                counts = await rows(
                    "SELECT job_type,count(*) AS count FROM job_runs WHERE store_id=:id "
                    "AND trigger_source='INTERVAL' AND status='SUCCEEDED' GROUP BY job_type",
                    id=store_id,
                )
                samples.append(
                    {
                        "elapsed_seconds": round(time.monotonic() - active_started, 3),
                        "freshness": dash["freshness"]["status"],
                        "completed_interval_jobs": counts,
                    }
                )
                await asyncio.sleep(1)
            completed = await rows(
                "SELECT id,job_type,scheduled_for,started_at,finished_at "
                "FROM job_runs WHERE store_id=:id "
                "AND trigger_source='INTERVAL' AND status='SUCCEEDED' ORDER BY scheduled_for",
                id=store_id,
            )
            checks = [row for row in completed if row["job_type"] == "check_mission"]
            syncs = [row for row in completed if row["job_type"] == "sync_events"]
            require(
                len(checks) >= 10 and len(syncs) >= 8,
                "Insufficient periodic progress over continuous run",
            )
            record["continuous_activity"] = {
                "wall_seconds": round(time.monotonic() - active_started, 3),
                "minimum_wall_seconds": 90,
                "completed_mission_checks": len(checks),
                "completed_source_syncs": len(syncs),
                "samples": samples,
                "interval_jobs": completed,
                "max_observed_final_attempt_start_lag_seconds": round(
                    max((r["started_at"] - r["scheduled_for"]).total_seconds() for r in completed),
                    3,
                ),
                "final_attempt_start_lag_description": (
                    "Final recorded started_at minus scheduled_for; includes worker downtime "
                    "and retry delays because retries overwrite started_at. "
                    "This is not a measurement of dispatch delay alone."
                ),
            }

            async def ledger():
                return await rows(
                    "SELECT id,effect_type,source_event_id,state_version,document "
                    "FROM ledger_entries "
                    "WHERE store_id=:id ORDER BY id",
                    id=store_id,
                )

            ledger_before = await ledger()
            history_before = (await sim.events(run_id, 0)).model_dump(mode="json")
            record["supplier_event_history"] = {"before_restart_and_replay": history_before}
            require(
                len(history_before["events"]) == 6
                and [event["sequence"] for event in history_before["events"]] == list(range(1, 7))
                and history_before["last_sequence"] == 6
                and history_before["source_head_sequence"] == 6
                and history_before["has_more"] is False,
                "Supplier SC01 history does not contain exactly six contiguous events",
            )
            record["phase"] = "full_restart_and_replay"
            for name in ("worker1", "worker2", "api", "simulator"):
                await processes.stop(name, kill=name.startswith("worker"))
            for name in ("simulator", "api", "worker1", "worker2"):
                processes.start(name)
            await until(ready, "full service restart readiness")
            for original in record["actions"]:
                current = await request("GET", "/api/v1/actions/" + original["id"])
                require(current == original, "Action changed after service restart")
                snapshot = (
                    await rows(
                        "SELECT request_snapshot FROM actions WHERE id=:id", id=original["id"]
                    )
                )[0]["request_snapshot"]
                queried = await sim.get_purchase(original["id"])
                replayed = await sim.purchase(original["id"], snapshot)
                require(
                    queried == replayed == original["receipt"],
                    "Supplier replay changed the receipt",
                )
            await caught_up(6)
            # Wait through another source interval so duplicate external effects could surface.
            await asyncio.sleep(6)
            history_after = (await sim.events(run_id, 0)).model_dump(mode="json")
            record["supplier_event_history"]["after_restart_and_replay"] = history_after
            require(
                history_after == history_before,
                "Restart replay changed supplier events or source head",
            )
            record["supplier_event_history"].update(
                exact_six_events_unchanged=True, source_head_unchanged=True
            )
            require((await dashboard())["state"] == final, "Restart replay changed business state")
            require(await ledger() == ledger_before, "Restart replay changed exact ledger rows")
            counts = {
                effect: sum(r["effect_type"] == effect for r in ledger_before)
                for effect in {r["effect_type"] for r in ledger_before}
            }
            require(
                counts
                == {
                    "INIT": 1,
                    "PURCHASE_ACCEPTED": 2,
                    "GOODS_RECEIVED": 2,
                    "SALE_RECORDED": 1,
                    "DEMAND_REVISED": 1,
                },
                "Unexpected ledger effect counts",
            )
            action_rows = await rows("SELECT id FROM actions WHERE store_id=:id", id=store_id)
            require(
                {row["id"] for row in action_rows} == {a["id"] for a in record["actions"]},
                "Scenario has extra purchase Actions",
            )
            record.update(
                ledger_effect_counts=counts,
                ledger_rows=ledger_before,
                restart_action_and_supplier_receipt_identical=True,
                supplier_purchase_replay_does_not_duplicate_effect=True,
                restart_exact_ledger_rows_unchanged=True,
                unique_action_count=len(action_rows),
                phase="complete",
                status="PASS",
            )
    finally:
        await db.dispose()


async def main():
    record = {
        "work_package": "B0-07",
        "status": "RUNNING",
        "phase": "preflight",
        "recorded_at": datetime.now(UTC).isoformat(),
        "runtime_overrides": OVERRIDES,
        "scope": "New development SC01, real API/simulator/two workers, automatic checks, "
        "concurrent exact approvals, source-job kill, source outage, downtime, restart replay.",
        "limitations": [
            "Read-only backend SQL is used to inspect leases, schedules, and ledger evidence.",
            "Processes share configured development databases; only the new scenario is asserted.",
            "Purchase lost-response injection belongs to separate integration acceptance.",
            "Observed local timing is not a production SLA or sustained-load benchmark.",
            "Fault intervals interrupt service; continuous activity means one bounded "
            "wall-clock acceptance run including recovery, not uninterrupted service uptime.",
            "All development data is retained; no database cleanup is performed.",
        ],
    }
    processes, servers = None, []
    barrier = SourceBarrier()
    failure = None
    started = time.monotonic()
    try:
        ports = {}
        for port in (8000, 8001, 8010, 8011, 8012, 8013):
            with socket.socket() as sock:
                sock.settimeout(0.3)
                ports[str(port)] = sock.connect_ex(("127.0.0.1", port)) == 0
        record["ports_occupied_before_start"] = ports
        require(
            not any(ports[str(p)] for p in (8010, 8011, 8012, 8013)),
            "Acceptance ports are occupied",
        )
        for name, port in (("worker1", 8012), ("worker2", 8013)):
            server = ThreadingHTTPServer(("127.0.0.1", port), proxy_handler(name, barrier))
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
        processes = Processes(record)
        async with asyncio.timeout(240):
            await acceptance(record, processes, barrier)
    except BaseException as exc:
        failure = exc
        record["status"] = "FAIL"
        record["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc)
            if isinstance(exc, CheckFailed)
            else "Inspect retained local logs; exception details omitted to protect credentials",
        }
    finally:
        barrier.release.set()
        if processes is not None:
            await processes.close()
        for server in servers:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
        record["total_wall_seconds"] = round(time.monotonic() - started, 3)
        record["finished_at"] = datetime.now(UTC).isoformat()
        RESULT.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )
    if failure is not None:
        raise SystemExit(
            f"B0-07 process acceptance failed in {record['phase']}; sanitized evidence: {RESULT}"
        )
    print(f"B0-07 process acceptance passed; owned processes stopped; evidence: {RESULT}")


if __name__ == "__main__":
    asyncio.run(main())
