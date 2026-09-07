"""Local three-process B0-04 smoke: python -m app.smoke_alerts [--verify-restart]."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from app.core.config import Settings

DIRECTORY = Path(__file__).resolve().parents[2] / "docs/api"
RESULT = DIRECTORY / "b0-04-alerts-smoke-result.json"


async def run(verify_restart):
    settings = Settings()
    grant = next(g for g in settings.auth_tokens if g.kind == "user" and "admin" in g.roles)
    contract = json.loads((DIRECTORY / "backend.openapi.json").read_text("utf-8"))

    def validate(name, value):
        Draft202012Validator(
            {"$ref": f"#/components/schemas/{name}", "components": contract["components"]},
            format_checker=FormatChecker(),
        ).validate(value)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        timeout=10,
        headers={"Authorization": "Bearer " + grant.token.get_secret_value()},
    ) as client:

        async def request(method, path, expected=200, **kwargs):
            response = await client.request(method, path, **kwargs)
            assert response.status_code == expected, (path, response.status_code, response.text)
            return response.json()

        async def post(path, body, expected=202):
            return await request(
                "POST", path, expected, json=body, headers={"Idempotency-Key": str(uuid4())}
            )

        async def wait_job(identifier):
            for _ in range(100):
                job = await request("GET", "/api/v1/job-runs/" + identifier)
                if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    assert job["status"] == "SUCCEEDED", job
                    return job
                await asyncio.sleep(0.2)
            raise AssertionError("Worker did not finish in 20 seconds")

        await request("GET", "/health/ready")
        runtime = await request("GET", "/openapi.json")
        assert runtime == json.loads(
            (DIRECTORY / "backend.runtime.openapi.json").read_text("utf-8")
        )
        if verify_restart:
            record = json.loads(RESULT.read_text("utf-8"))
            store_id, mission_id = record["store_id"], record["mission_id"]
        else:
            initialized = await wait_job(
                (await post("/dev/v1/scenarios", {"scenario": "SC01"}))["job_run_id"]
            )
            refs = initialized["result"]["references"]
            store_id = next(r["id"] for r in refs if r["type"] == "store")
            run_id = next(r["id"] for r in refs if r["type"] == "scenario")
            for _ in range(100):
                dash = await request("GET", "/api/v1/dashboard", params={"store_id": store_id})
                if dash["freshness"]["status"] == "FRESH":
                    break
                await asyncio.sleep(0.2)
            else:
                raise AssertionError("Initial sync did not catch up")
            catalog = await request("GET", "/api/v1/catalog", params={"store_id": store_id})
            offer = catalog["offers"][0]
            mission = await post(
                "/api/v1/missions",
                {
                    "store_id": store_id,
                    "sku_id": offer["sku_id"],
                    "objective": "B0-04警报验证",
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
            checked = await wait_job(
                (await post(f"/api/v1/missions/{mission_id}/checks", {}))["job_run_id"]
            )
            assert checked["result"]["check_status"] == "ANOMALY"
        filters = {"store_id": store_id, "mission_id": mission_id}
        alerts = await request("GET", "/api/v1/alerts", params=filters)
        validate("AlertList", alerts)
        assert len(alerts["items"]) == 1
        alert = alerts["items"][0]
        dash = await request("GET", "/api/v1/dashboard", params={"store_id": store_id})
        validate("Dashboard", dash)
        if verify_restart:
            assert alert == record["alert"] and dash["state"] == record["dashboard"]["state"]
            record["restart_acknowledgement_preserved"] = True
            record["verified_after_process_restart_at"] = datetime.now(UTC).isoformat()
        else:
            assert alert["type"] == "STOCKOUT_RISK" and alert["status"] == "OPEN"
            assert alert["facts"]["shortage_qty"] == 40
            ack_headers = {"Idempotency-Key": str(uuid4())}
            path = f"/api/v1/alerts/{alert['id']}/acknowledgement"
            ack = await request("POST", path, headers=ack_headers)
            validate("Alert", ack)
            assert ack["status"] == "ACKNOWLEDGED"
            assert await request("POST", path, headers=ack_headers) == ack
            after = await request("GET", "/api/v1/dashboard", params={"store_id": store_id})
            assert after["state"] == dash["state"] and after["active_alert_count"] == 1
            assert after["state"]["cash_minor"] == 100000
            assert after["state"]["stocks"][0]["on_hand"] == 20
            record = {
                "recorded_at": datetime.now(UTC).isoformat(),
                "work_package": "B0-04",
                "store_id": store_id,
                "scenario_run_id": run_id,
                "mission_id": mission_id,
                "alert": ack,
                "dashboard": after,
                "ack_replay_identical": True,
                "ack_does_not_resolve_or_mutate_state": True,
                "runtime_matches_export": True,
                "backend_runtime_operations": 18,
                "scope": "Separate API/worker/simulator; initial risk, acknowledgement, dashboard, "
                "timeline and restart. Recurring dispatch and action alerts await B0-06/05.",
            }
        history = await request(
            "GET", f"/api/v1/missions/{mission_id}/timeline", params={"limit": 100}
        )
        validate("TimelineEntryList", history)
        acks = [entry for entry in history["items"] if entry["type"] == "ALERT_ACKNOWLEDGED"]
        assert len(acks) == 1 and {"type": "alert", "id": alert["id"]} in acks[0]["references"]
        record["timeline"] = history
        RESULT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "alert_status": "ACKNOWLEDGED",
                    "restart_verified": record.get("restart_acknowledgement_preserved", False),
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-restart", action="store_true")
    asyncio.run(run(parser.parse_args().verify_restart))
