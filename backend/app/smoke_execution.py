"""Run the B0-05 three-process SC01 acceptance: python -m app.smoke_execution."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import Database
from app.operations.client import SimulationClient

DIRECTORY = Path(__file__).resolve().parents[2] / "docs/api"
RESULT = DIRECTORY / "b0-05-execution-smoke-result.json"


async def run(verify_restart):
    settings = Settings()
    grant = next(g for g in settings.auth_tokens if g.kind == "user" and "admin" in g.roles)
    contract = json.loads((DIRECTORY / "backend.openapi.json").read_text("utf-8"))
    db = Database(settings.database_url.get_secret_value())
    sim = SimulationClient(settings)

    def validate(name, data):
        Draft202012Validator(
            {"$ref": f"#/components/schemas/{name}", "components": contract["components"]},
            format_checker=FormatChecker(),
        ).validate(data)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        timeout=10,
        headers={"Authorization": "Bearer " + grant.token.get_secret_value()},
    ) as client:

        async def request(method, path, expected=200, **kwargs):
            response = await client.request(method, path, **kwargs)
            assert response.status_code == expected, (path, response.status_code, response.text)
            return response.json()

        async def post(path, body, expected=202, key=None):
            return await request(
                "POST", path, expected, json=body, headers={"Idempotency-Key": key or str(uuid4())}
            )

        async def wait_job(identifier):
            for _ in range(150):
                job = await request("GET", "/api/v1/job-runs/" + identifier)
                if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    assert job["status"] == "SUCCEEDED", job
                    return job
                await asyncio.sleep(0.2)
            raise AssertionError("Worker did not complete job within 30 seconds")

        async def caught_up(store_id, run_id, sequence):
            for _ in range(150):
                async with db.session() as session:
                    current = await session.scalar(
                        text("SELECT last_sequence FROM source_cursors WHERE scenario_run_id=:id"),
                        {"id": run_id},
                    )
                dash = await request("GET", "/api/v1/dashboard", params={"store_id": store_id})
                if current >= sequence and dash["freshness"]["status"] == "FRESH":
                    validate("Dashboard", dash)
                    return dash["state"]
                await asyncio.sleep(0.2)
            raise AssertionError("Source did not catch up")

        await request("GET", "/health/ready")
        runtime = await request("GET", "/openapi.json")
        assert runtime == json.loads(
            (DIRECTORY / "backend.runtime.openapi.json").read_text("utf-8")
        )
        if verify_restart:
            record = json.loads(RESULT.read_text("utf-8"))
            store_id, run_id = record["store_id"], record["scenario_run_id"]
            for original in record["actions"]:
                current = await request("GET", "/api/v1/actions/" + original["id"])
                assert current == original
                queried = await sim.get_purchase(original["id"])
                async with db.session() as session:
                    body = await session.scalar(
                        text("SELECT request_snapshot FROM actions WHERE id=:id"),
                        {"id": original["id"]},
                    )
                assert await sim.purchase(original["id"], body) == queried == original["receipt"]
            after = (await request("GET", "/api/v1/dashboard", params={"store_id": store_id}))[
                "state"
            ]
            assert after == record["final_state"]
            record["restart_verified_at"] = datetime.now(UTC).isoformat()
            record["restart_action_and_supplier_receipt_identical"] = True
            record["supplier_purchase_replay_does_not_duplicate_effect"] = True
        else:
            initialized = await wait_job(
                (await post("/dev/v1/scenarios", {"scenario": "SC01"}))["job_run_id"]
            )
            refs = initialized["result"]["references"]
            store_id = next(r["id"] for r in refs if r["type"] == "store")
            run_id = next(r["id"] for r in refs if r["type"] == "scenario")
            await caught_up(store_id, run_id, 0)
            catalog = await request("GET", "/api/v1/catalog", params={"store_id": store_id})
            offer = catalog["offers"][0]
            mission = await post(
                "/api/v1/missions",
                {
                    "store_id": store_id,
                    "sku_id": offer["sku_id"],
                    "objective": "B0-05完整SC01采购入账",
                    "policy": {
                        "cash_floor_minor": 30000,
                        "candidate_quantities": [0, 20, 40, 80],
                        "supplier_id": offer["supplier_id"],
                    },
                    "check_interval_seconds": 30,
                },
                201,
            )
            mission_id = mission["id"]

            async def purchase(quantity):
                await wait_job(
                    (await post(f"/api/v1/missions/{mission_id}/checks", {}))["job_run_id"]
                )
                mission = await request("GET", "/api/v1/missions/" + mission_id)
                plan = await request("GET", "/api/v1/plans/" + mission["current_plan_id"])
                assert plan["proposed_purchase"]["quantity"] == quantity, plan
                validate("Plan", plan)
                decision = {
                    "decision": "approve",
                    "expected_plan_version": plan["plan_version"],
                    "expected_state_version": plan["state_version"],
                    "proposal_hash": plan["proposal_hash"],
                }
                path, key = f"/api/v1/plans/{plan['id']}/decision", str(uuid4())
                accepted = await post(path, decision, key=key)
                assert await post(path, decision, key=key) == accepted
                validate("DecisionApproved", accepted)
                await wait_job(accepted["job_run_id"])
                action = await request("GET", "/api/v1/actions/" + accepted["action_id"])
                validate("Action", action)
                assert action["status"] == "SUCCEEDED", action
                return action

            first = await purchase(40)
            await caught_up(store_id, run_id, 1)
            advance = f"/dev/v1/scenarios/{run_id}/advance"
            key = str(uuid4())
            accepted = await post(advance, {"steps": 1}, key=key)
            assert await post(advance, {"steps": 1}, key=key) == accepted
            await wait_job(accepted["job_run_id"])
            first_goods = await caught_up(store_id, run_id, 2)
            assert first_goods["stocks"][0]["on_hand"] == 60
            await wait_job((await post(advance, {"steps": 2}))["job_run_id"])
            revised = await caught_up(store_id, run_id, 4)
            assert revised["stocks"][0]["on_hand"] == 50
            assert revised["stocks"][0]["remaining_demand"] == 70
            second = await purchase(20)
            await caught_up(store_id, run_id, 5)
            await wait_job((await post(advance, {"steps": 1}))["job_run_id"])
            final = await caught_up(store_id, run_id, 6)
            assert (
                final["cash_minor"],
                final["reserved_cash_minor"],
                final["receivables_minor"],
                final["stocks"][0]["on_hand"],
                final["stocks"][0]["in_transit"],
            ) == (40000, 0, 20000, 70, 0)
            record = {
                "recorded_at": datetime.now(UTC).isoformat(),
                "work_package": "B0-05",
                "scenario_run_id": run_id,
                "store_id": store_id,
                "mission_id": mission_id,
                "actions": [first, second],
                "final_state": final,
                "runtime_matches_export": True,
                "backend_runtime_operations": 21,
                "approval_and_advance_replay_identical": True,
                "scope": "Separate API, worker and simulator processes; explicit SC01 advance. "
                "Fault and lease cases use PostgreSQL tests with controlled transports; "
                "recurring dispatch remains B0-06.",
            }
        async with db.session() as session:
            counts = dict(
                (
                    await session.execute(
                        text(
                            "SELECT effect_type,count(*) FROM ledger_entries "
                            "WHERE store_id=:id GROUP BY effect_type"
                        ),
                        {"id": store_id},
                    )
                ).all()
            )
        assert counts == {
            "INIT": 1,
            "PURCHASE_ACCEPTED": 2,
            "GOODS_RECEIVED": 2,
            "SALE_RECORDED": 1,
            "DEMAND_REVISED": 1,
        }, counts
        record["ledger_effect_counts"] = counts
        RESULT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "store_id": store_id,
                    "cash_minor": 40000,
                    "on_hand": 70,
                    "restart_verified": "restart_verified_at" in record,
                }
            )
        )
    await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-restart", action="store_true")
    asyncio.run(run(parser.parse_args().verify_restart))
