"""Verify seven read APIs over the persisted B0-07 SC01 fixture using a real HTTP server.

Run from repository root. Owns only an API on port 8014, creates no business data,
uses ephemeral scoped credentials, and stops its server in finally.
"""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.db.session import Database  # noqa: E402


async def verify(client, db, fixture, token, service_token):
    contract = json.loads((ROOT / "docs/api/frontend-data.openapi.json").read_text("utf-8"))
    runtime = (await client.get("/openapi.json")).json()
    assert runtime == json.loads(
        (ROOT / "docs/api/backend.runtime.openapi.json").read_text("utf-8")
    )
    store_id = fixture["store_id"]
    tables = [
        "business_events",
        "ledger_entries",
        "job_runs",
        "command_receipts",
        "alerts",
        "mission_timeline",
    ]

    async def snapshot():
        async with db.session() as session:
            return {
                name: await session.scalar(text("SELECT count(*) FROM " + name)) for name in tables
            }

    async def read(path, **params):
        response = await client.get(path, params=params)
        assert response.status_code == 200, (path, response.status_code, response.text)
        value = response.json()
        if path in contract["paths"]:
            schema = contract["paths"][path]["get"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            Draft202012Validator(
                schema | {"components": contract["components"]}, format_checker=FormatChecker()
            ).validate(value)
        return value

    before = await snapshot()
    dashboard = await read("/api/v1/dashboard", store_id=store_id)
    assert dashboard["state"] == fixture["final_state"], (
        "Persisted B0-07 fixture changed; do not alter it"
    )
    requests = {}
    for path in contract["paths"]:
        if path.endswith("/summary"):
            continue
        params = {} if path.endswith(("/me", "/stores")) else {"store_id": store_id}
        requests[path] = {"params": params, "response": await read(path, **params)}
    sales = requests["/api/v1/sales"]["response"]["items"]
    assert (
        len(sales) == 1 and sales[0]["quantity"] == 10 and sales[0]["sales_amount_minor"] == 20000
    )
    day = (
        datetime.fromisoformat(sales[0]["simulation_time"])
        .astimezone(UTC)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    params = {
        "store_id": store_id,
        "from": day.isoformat(),
        "to": (day + timedelta(days=1)).isoformat(),
    }
    summary = await read("/api/v1/sales/summary", **params)
    assert (
        summary["record_count"],
        summary["recorded_quantity"],
        summary["recorded_sales_amount_minor"],
    ) == (1, 10, 20000)
    requests["/api/v1/sales/summary"] = {"params": params, "response": summary}
    assert [s["store_id"] for s in requests["/api/v1/stores"]["response"]["items"]] == [store_id]
    assert requests["/api/v1/me"]["response"]["roles"] == ["viewer"]
    for path in ["/api/v1/actions", "/api/v1/inbounds", "/api/v1/ledger-entries"]:
        collected, cursor = [], None
        while True:
            params = {"store_id": store_id, "limit": 1}
            if cursor is not None:
                params["cursor"] = cursor
            page = await read(path, **params)
            collected.extend(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
            assert len(collected) < 20
        assert collected == requests[path]["response"]["items"]
    actions = requests["/api/v1/actions"]["response"]["items"]
    assert len(actions) == 2 and sorted(a["quantity"] for a in actions) == [20, 40]
    for action in actions:
        assert await read("/api/v1/actions/" + action["id"]) == action
    inbounds = requests["/api/v1/inbounds"]["response"]["items"]
    assert len(inbounds) == 2 and all(
        i["arrival_status"] == "RECEIVED"
        and i["remaining_quantity"] == 0
        and i["is_overdue"] is False
        for i in inbounds
    )
    ledger = requests["/api/v1/ledger-entries"]["response"]["items"]
    assert len(ledger) == 7
    opening = next(r["opening_state"] for r in ledger if r["effect_type"] == "INIT")
    changes = [r["changes"] for r in ledger if r["changes"] is not None]
    assert opening["cash_minor"] + sum(c["cash_delta_minor"] for c in changes) == 40000
    assert (
        opening["receivables_minor"] + sum(c["receivables_delta_minor"] for c in changes) == 20000
    )
    assert opening["stocks"][0]["on_hand"] + sum(c["on_hand_delta"] for c in changes) == 70
    assert opening["stocks"][0]["in_transit"] + sum(c["in_transit_delta"] for c in changes) == 0
    goods = await read("/api/v1/ledger-entries", store_id=store_id, effect_type="GOODS_RECEIVED")
    assert len(goods["items"]) == 2
    errors = []
    for expected, headers, params in [
        (401, {"Authorization": "Bearer invalid"}, {"store_id": store_id}),
        (403, {"Authorization": "Bearer " + service_token}, {"store_id": store_id}),
        (404, {"Authorization": "Bearer " + token}, {"store_id": "unauthorized-store"}),
        (
            422,
            {"Authorization": "Bearer " + token},
            {"store_id": store_id, "warehouse_id": "unsupported"},
        ),
    ]:
        response = await client.get("/api/v1/sales", headers=headers, params=params)
        assert response.status_code == expected
        errors.append({"status": expected, "code": response.json()["error"]["code"]})
    assert await snapshot() == before
    assert (await read("/api/v1/dashboard", store_id=store_id))["state"] == dashboard["state"]
    return {
        "recorded_at": datetime.now(UTC).isoformat(),
        "work_package": "frontend-data-v1",
        "fixture_source": (
            "b0-07-process-result.json (persisted SC01, read only; not a new SC01 run)"
        ),
        "store_id": store_id,
        "runtime_operations": sum(
            len([m for m in item if m in {"get", "post", "patch", "put", "delete"}])
            for item in runtime["paths"].values()
        ),
        "runtime_paths": len(runtime["paths"]),
        "requests": requests,
        "error_checks": errors,
        "page_size_one_reconstructs_full_lists": True,
        "action_list_matches_detail": True,
        "sc01_ledger_reconstruction": {
            "cash_minor": 40000,
            "receivables_minor": 20000,
            "on_hand": 70,
            "in_transit": 0,
        },
        "business_counts_before_and_after": before,
        "business_state_unchanged": True,
    }


async def main():
    port = 8014
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError("Port 8014 is occupied; no existing process was stopped")
    fixture = json.loads((ROOT / "docs/api/b0-07-process-result.json").read_text("utf-8"))
    settings = Settings(_env_file=ROOT / "backend/.env")
    db = Database(settings.database_url.get_secret_value())
    token, service_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    env = os.environ.copy()
    env["AUTH_TOKENS"] = json.dumps(
        [
            {
                "token": token,
                "principal_id": "frontend-read-verifier",
                "roles": ["viewer"],
                "store_ids": [fixture["store_id"]],
            },
            {"token": service_token, "principal_id": "frontend-read-service", "kind": "service"},
        ]
    )
    env["APP_ENV"] = "test"
    result = None
    started = time.monotonic()
    with (ROOT / "var/frontend-http.log").open("w", encoding="utf-8") as log:
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
                str(port),
                "--no-access-log",
            ],
            cwd=ROOT / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}",
                headers={"Authorization": "Bearer " + token},
                timeout=10,
            ) as client:
                async with asyncio.timeout(30):
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError(
                                "Owned API exited before readiness; inspect var/frontend-http.log"
                            )
                        try:
                            if (await client.get("/health/ready")).status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        await asyncio.sleep(0.2)
                result = await verify(client, db, fixture, token, service_token)
        finally:
            if process.poll() is None:
                process.terminate()
            await asyncio.to_thread(process.wait, timeout=15)
            await db.dispose()
    result |= {
        "owned_api_pid": process.pid,
        "owned_api_stopped": True,
        "port": port,
        "wall_seconds": round(time.monotonic() - started, 3),
    }
    output = ROOT / "docs/api/frontend-data-http-result.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "PASS real HTTP: 7 read APIs, 4 error boundaries, "
        "paging and persisted SC01 ledger; API stopped"
    )


if __name__ == "__main__":
    asyncio.run(main())
