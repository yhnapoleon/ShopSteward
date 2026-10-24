"""Real HTTP acceptance; creates and preserves new synthetic development scenarios.

Uses an existing configured backend admin for explicit simulated Plan approval.
Requires simulator console8001, backend8000 and business worker. No model calls.
--verify-restart only reads saved run and replays its original trigger key.
"""

import asyncio
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "docs/api/simulator-console-acceptance-result.json"
sys.path.insert(0, str(ROOT / "simulation"))
from simulator.schemas import State  # noqa: E402


async def main():
    grants = json.loads(dotenv_values(ROOT / "backend/.env")["AUTH_TOKENS"])
    token = next(
        g["token"]
        for g in grants
        if g.get("kind", "user") == "user" and "admin" in g.get("roles", [])
    )
    result = {
        "started_at": datetime.now(UTC).isoformat(),
        "checks": [],
        "scenarios": [],
        "agent_enabled": False,
        "data_source": "synthetic",
        "approval": "explicit backend API, simulated purchases only",
    }

    def check(name, passed, **evidence):
        result["checks"].append({"name": name, "passed": bool(passed), **evidence})
        print(name + (": PASS" if passed else ": FAIL"), flush=True)
        if not passed:
            raise AssertionError(name)

    async with (
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8001/console/api/",
            timeout=15,
            trust_env=False,
            headers={"X-Simulator-Console": "1"},
        ) as sim,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:8000",
            timeout=15,
            trust_env=False,
            headers={"Authorization": "Bearer " + token},
        ) as backend,
    ):

        async def request(client, method, path, body=None, key=None):
            response = await client.request(
                method, path, json=body, headers={"Idempotency-Key": key or str(uuid4())}
            )
            assert response.is_success, (path, response.status_code, response.text[:400])
            return response.json()

        async def poll(client, path, predicate, seconds=35):
            start = time.monotonic()
            last = None
            while time.monotonic() - start < seconds:
                last = await request(client, "GET", path)
                if predicate(last):
                    return last, round(time.monotonic() - start, 3)
                await asyncio.sleep(0.35)
            raise AssertionError(("poll_timeout", path, last))

        def fingerprint(detail):
            stable = {
                k: detail[k]
                for k in ("state", "initial_snapshot", "orders", "last_sequence", "step_index")
            }
            return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()

        if "--verify-restart" in sys.argv:
            result = json.loads(RESULT.read_text("utf-8"))
            target = result["scenarios"][0]
            current = await request(sim, "GET", "runs/" + target["run_id"])
            check(
                "restart_persistent_world",
                State.model_validate(current["state"])
                == State.model_validate(target["final_source_state"]),
            )
            replay = result["replay"]
            returned = await request(sim, "POST", replay["path"], replay["body"], replay["key"])
            check("restart_original_trigger_replay", returned == replay["response"])
            final = await request(sim, "GET", "runs/" + target["run_id"])
            check("restart_replay_no_duplicate", final["last_sequence"] == target["last_sequence"])
            result["restart_verified_at"] = datetime.now(UTC).isoformat()
            RESULT.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            return

        old = await request(sim, "GET", "runs?limit=100")
        old_fingerprints = {}
        for row in old["items"]:
            old_fingerprints[row["scenario_run_id"]] = fingerprint(
                await request(sim, "GET", "runs/" + row["scenario_run_id"])
            )
        check("services_ready", (await request(sim, "GET", "status"))["backend_status"] == "ready")

        async def linked(label, parameters):
            job = await request(
                sim,
                "POST",
                "linked-runs",
                {"scenario": "SANDBOX", "label": label, "parameters": parameters},
            )
            finished, _ = await poll(
                sim, "jobs/" + job["job_run_id"], lambda x: x["status"] in {"SUCCEEDED", "FAILED"}
            )
            assert finished["status"] == "SUCCEEDED", finished
            refs = {ref["type"]: ref["id"] for ref in finished["result"]["references"]}
            rid, sid = refs["scenario"], refs["store"]
            await poll(sim, f"runs/{rid}/backend", lambda x: x.get("source_sequence") == 0)
            mission = await request(
                backend,
                "POST",
                "/api/v1/missions",
                {
                    "store_id": sid,
                    "sku_id": "sku_001",
                    "objective": "控制台合成场景：备货与现金底线",
                    "policy": {
                        "cash_floor_minor": 30000,
                        "candidate_quantities": [0, 20, 40, 80],
                        "supplier_id": "supplier_001",
                    },
                    "check_interval_seconds": 5,
                },
            )
            ready, _ = await poll(
                backend, "/api/v1/missions/" + mission["id"], lambda x: bool(x["current_plan_id"])
            )
            plan = await request(backend, "GET", "/api/v1/plans/" + ready["current_plan_id"])
            item = {
                "label": label,
                "run_id": rid,
                "store_id": sid,
                "mission_id": mission["id"],
                "initial_plan_id": plan["id"],
            }
            result["scenarios"].append(item)
            return item, plan

        try:
            item, plan = await linked("联动验收 · 部分到货与需求上调", {})
            rid = item["run_id"]
            check("backend_recommends_40", plan["proposed_purchase"]["quantity"] == 40)
            approved = await request(
                backend,
                "POST",
                f"/api/v1/plans/{plan['id']}/decision",
                {
                    "decision": "approve",
                    "expected_plan_version": plan["plan_version"],
                    "expected_state_version": plan["state_version"],
                    "proposal_hash": plan["proposal_hash"],
                },
            )
            action, _ = await poll(
                backend,
                "/api/v1/actions/" + approved["action_id"],
                lambda x: x["status"] == "SUCCEEDED",
            )
            check("real_simulator_purchase_accepted", action["receipt"]["status"] == "ACCEPTED")

            async def trigger(body):
                current = await request(sim, "GET", f"runs/{rid}")
                body = {"expected_sequence": current["last_sequence"], **body}
                key = str(uuid4())
                start = time.monotonic()
                path = f"runs/{rid}/triggers"
                receipt = await request(sim, "POST", path, body, key)
                observed, elapsed = await poll(
                    sim,
                    f"runs/{rid}/backend",
                    lambda x: x.get("source_sequence") == receipt["last_sequence"],
                )
                source = receipt["after"]
                projection = observed["dashboard"]["state"]
                for field in ("cash_minor", "receivables_minor"):
                    assert source[field] == projection[field], field
                for field in ("on_hand", "in_transit", "remaining_demand"):
                    assert source["stocks"][0][field] == projection["stocks"][0][field], field
                check(
                    body["kind"] + "_synchronized",
                    True,
                    source_sequence=receipt["last_sequence"],
                    sync_wait_seconds=elapsed,
                    total_seconds=round(time.monotonic() - start, 3),
                )
                return {"path": path, "body": body, "key": key, "response": receipt}

            await trigger({"kind": "receipt", "action_id": action["id"], "quantity": 15})
            result["replay"] = await trigger(
                {"kind": "sale", "quantity": 5, "unit_price_minor": 2000, "advance_seconds": 3600}
            )
            await trigger({"kind": "demand", "remaining_demand": 90})
            await trigger({"kind": "receipt", "action_id": action["id"]})
            replay = result["replay"]
            check(
                "old_successful_key_replays_after_other_events",
                await request(sim, "POST", replay["path"], replay["body"], replay["key"])
                == replay["response"],
            )
            final = await request(sim, "GET", f"runs/{rid}")
            s = final["state"]
            stock = s["stocks"][0]
            check(
                "exact_final_world",
                (
                    s["cash_minor"],
                    s["receivables_minor"],
                    stock["on_hand"],
                    stock["in_transit"],
                    stock["remaining_demand"],
                    final["last_sequence"],
                )
                == (60000, 10000, 55, 0, 90, 5),
            )
            item.update(
                final_source_state=s, last_sequence=final["last_sequence"], action_id=action["id"]
            )
            events = await request(sim, "GET", f"runs/{rid}/events?after_sequence=0")
            check(
                "continuous_five_events",
                [e["sequence"] for e in events["events"]] == [1, 2, 3, 4, 5],
            )
            for label, params, want in [
                ("现金紧张 · 500元", {"cash_minor": 50000}, 20),
                ("库存充足 · 100件", {"on_hand": 100}, 0),
            ]:
                _, p = await linked(label, params)
                quantity = p["proposed_purchase"]["quantity"] if p["proposed_purchase"] else 0
                check(label, quantity == want, recommended_quantity=quantity)
            unchanged = True
            for old_id, old_hash in old_fingerprints.items():
                unchanged = (
                    unchanged
                    and fingerprint(await request(sim, "GET", "runs/" + old_id)) == old_hash
                )
            check("preexisting_runs_unchanged", unchanged, count=len(old_fingerprints))
            result["finished_at"] = datetime.now(UTC).isoformat()
        finally:
            RESULT.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )


if __name__ == "__main__":
    asyncio.run(main())
