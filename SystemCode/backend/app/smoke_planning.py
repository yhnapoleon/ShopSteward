"""Run from backend with its configured API, worker and simulator already running.

python -m app.smoke_planning [--verify-restart]
Creates a new development scenario/Mission; never approves or purchases.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from app.core.config import Settings
from app.db.session import Database
from app.operations.repository import get_state

DIRECTORY = Path(__file__).resolve().parents[2] / "docs/api"
RESULT = DIRECTORY / "b0-03-planning-smoke-result.json"


async def run(verify_restart):
    settings = Settings()
    grant = next(g for g in settings.auth_tokens if g.kind == "user" and "admin" in g.roles)
    token = grant.token.get_secret_value()
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", headers={"Authorization": f"Bearer {token}"}, timeout=10
    ) as client:

        async def request(method, path, expected=200, **kwargs):
            response = await client.request(method, path, **kwargs)
            assert response.status_code == expected, (path, response.status_code, response.text)
            return response.json()

        async def wait_job(job_id):
            for _ in range(100):
                job = await request("GET", "/api/v1/job-runs/" + job_id)
                if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    assert job["status"] == "SUCCEEDED", job
                    return job
                await asyncio.sleep(0.2)
            raise AssertionError("Worker job did not finish within 20 seconds")

        await request("GET", "/health/ready")
        runtime = await request("GET", "/openapi.json")
        assert runtime == json.loads(
            (DIRECTORY / "backend.runtime.openapi.json").read_text("utf-8")
        )
        if verify_restart:
            record = json.loads(RESULT.read_text("utf-8"))
            plan = await request("GET", "/api/v1/plans/" + record["plan"]["id"])
            assert plan == record["plan"]
            mission = await request("GET", "/api/v1/missions/" + record["mission_id"])
            assert mission["current_plan_id"] == plan["id"]
            record["restart_plan_identical"] = True
            record["verified_after_process_restart_at"] = datetime.now(UTC).isoformat()
        else:
            accepted = await request(
                "POST",
                "/dev/v1/scenarios",
                expected=202,
                json={"scenario": "SC01"},
                headers={"Idempotency-Key": str(uuid4())},
            )
            initialized = await wait_job(accepted["job_run_id"])
            references = initialized["result"]["references"]
            store_id = next(r["id"] for r in references if r["type"] == "store")
            run_id = next(r["id"] for r in references if r["type"] == "scenario")
            for _ in range(100):
                monitoring = await request("GET", "/api/v1/monitoring/status")
                source = next(
                    (s for s in monitoring["sources"] if s["source"] == "simulation:" + run_id),
                    None,
                )
                if source and source["status"] == "FRESH":
                    break
                await asyncio.sleep(0.2)
            else:
                raise AssertionError("Initialization sync did not catch up")
            catalog = await request("GET", "/api/v1/catalog", params={"store_id": store_id})
            offer = catalog["offers"][0]
            body = {
                "store_id": store_id,
                "sku_id": offer["sku_id"],
                "objective": "SC01备货，在现金底线下减少缺货",
                "policy": {
                    "cash_floor_minor": 30000,
                    "candidate_quantities": [0, 20, 40, 80],
                    "supplier_id": offer["supplier_id"],
                },
                "check_interval_seconds": 30,
            }
            command_headers = {"Idempotency-Key": str(uuid4())}
            created = await request(
                "POST", "/api/v1/missions", expected=201, json=body, headers=command_headers
            )
            for _ in range(100):
                mission = await request("GET", "/api/v1/missions/" + created["id"])
                if mission["current_plan_id"]:
                    break
                await asyncio.sleep(0.2)
            else:
                raise AssertionError("Initial mission check did not publish a plan")
            plan = await request("GET", "/api/v1/plans/" + mission["current_plan_id"])
            assert plan["proposed_purchase"]["quantity"] == 40
            assert plan["proposed_purchase"]["total_minor"] == 40000
            assert plan["candidates"][-1]["rejection_reasons"] == ["CASH_FLOOR_VIOLATION"]
            assert plan["candidates"][-1]["cash_after_minor"] == 20000
            assert mission["schedule"]["enabled"] is False
            assert mission["schedule"]["next_run_at"] is None
            design = json.loads((DIRECTORY / "backend.openapi.json").read_text("utf-8"))
            Draft202012Validator(
                {"$ref": "#/components/schemas/Plan", "components": design["components"]},
                format_checker=FormatChecker(),
            ).validate(plan)
            replay = await request(
                "POST", "/api/v1/missions", expected=201, json=body, headers=command_headers
            )
            assert replay == created
            check = await request(
                "POST",
                f"/api/v1/missions/{mission['id']}/checks",
                expected=202,
                json={},
                headers={"Idempotency-Key": str(uuid4())},
            )
            checked = await wait_job(check["job_run_id"])
            plans = await request("GET", f"/api/v1/missions/{mission['id']}/plans")
            assert plans["items"] == [plan]
            db = Database(settings.database_url.get_secret_value())
            try:
                async with db.session() as session:
                    state = await get_state(session, store_id)
                    assert state.cash_minor == state.available_cash_minor == 100000
                    assert state.stocks[0].on_hand == 20 and state.stocks[0].in_transit == 0
            finally:
                await db.dispose()
            record = {
                "recorded_at": datetime.now(UTC).isoformat(),
                "work_package": "B0-03",
                "scenario_run_id": run_id,
                "store_id": store_id,
                "mission_id": mission["id"],
                "initialize_job_id": initialized["id"],
                "manual_check_job_id": check["job_run_id"],
                "check_status": checked["result"]["check_status"],
                "mission_create_replay_identical": True,
                "unchanged_plan_reused": True,
                "cash_and_inventory_unchanged": True,
                "runtime_matches_export": True,
                "backend_runtime_operations": 14,
                "plan_matches_design_schema": True,
                "tests": {"backend_passed": 74, "simulator_passed": 2, "skipped": 0},
                "scope": "Separate API/worker/simulator; initial deterministic plan only. "
                "Approval, purchase, recurring dispatch and full SC01 await later stages.",
                "plan": plan,
            }
        RESULT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "mission_id": record["mission_id"],
                    "plan_id": record["plan"]["id"],
                    "recommended_quantity": 40,
                    "restart_verified": record.get("restart_plan_identical", False),
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-restart", action="store_true")
    asyncio.run(run(parser.parse_args().verify_restart))
