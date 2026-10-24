"""Opt-in real PG -> tool HTTP -> SSE -> Nitro -> browser acceptance. No model call."""

import asyncio
import os
import socket
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, Request
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_missions import headers

ROOT = Path(__file__).resolve().parents[3]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("PROGRESS_BROWSER_E2E") != "true",
        reason="Requires a built local frontend and Node",
    ),
]


async def test_real_tools_stream_through_nitro_to_task_workspace(db, monkeypatch):
    import uvicorn

    from app.agent_bridge import progress, tools
    from app.agent_bridge.jobs import make_handlers
    from app.core.errors import AppError
    from app.planning.jobs import make_handlers as planning
    from app.scheduling.runner import Runner

    root = ROOT
    output = root / "var/agent-progress-browser"
    output.mkdir(parents=True, exist_ok=True)
    app, setup_client, mission = await setup_agent(db)
    await setup_client.aclose()
    await Runner(db, app.state.settings, handlers=planning(app.state.settings)).run_once()
    gates = {name: asyncio.Event() for name in ("get_dashboard", "evaluate_plan", "revise_plan")}
    test_auth = headers()
    for grant in app.state.settings.auth_tokens:
        if grant.principal_id == "operator":
            grant.roles = ["operator", "approver"]
    streaming = True
    original_tool, original_page = tools.execute_tool, progress.event_page

    async def held_tool(*args, **kwargs):
        name = args[7]
        if name in gates:
            await gates[name].wait()
        return await original_tool(*args, **kwargs)

    async def event_page(*args, **kwargs):
        if not streaming:
            raise AppError(503, "PROGRESS_UNAVAILABLE", "Controlled stream interruption")
        return await original_page(*args, **kwargs)

    monkeypatch.setattr(tools, "execute_tool", held_tool)
    monkeypatch.setattr(progress, "event_page", event_page)

    @app.post("/__test__/{operation}/{value}", include_in_schema=False)
    async def control(operation: str, value: str, request: Request):
        nonlocal streaming
        if request.headers.get("authorization") != test_auth["Authorization"]:
            raise HTTPException(403)
        if operation == "release" and value in gates:
            gates[value].set()
        elif operation == "stream":
            streaming = value == "on"
        return {"ok": True}

    backend_socket = socket.socket()
    backend_socket.bind(("127.0.0.1", 0))
    backend_url = f"http://127.0.0.1:{backend_socket.getsockname()[1]}"
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        frontend_port = candidate.getsockname()[1]
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    serving = asyncio.create_task(server.serve(sockets=[backend_socket]))
    frontend = loop = browser = None
    stop = asyncio.Event()
    frontend_log = (output / "frontend.log").open("wb")
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started
        env = os.environ | {
            "NITRO_HOST": "127.0.0.1",
            "NITRO_PORT": str(frontend_port),
            "NUXT_BACKEND_URL": backend_url,
            "NUXT_AGENT_ENABLED": "true",
            "NUXT_DEV_TOOLS": "false",
        }
        frontend = await asyncio.create_subprocess_exec(
            "node",
            ".output/server/index.mjs",
            cwd=root / "frontend",
            env=env,
            stdout=frontend_log,
            stderr=asyncio.subprocess.STDOUT,
        )
        async with httpx.AsyncClient(base_url=backend_url, timeout=15) as client:

            async def execute(context):
                auth = {"Authorization": "Bearer " + context["token"]}
                for name in gates:
                    arguments = {} if name == "get_dashboard" else {"max_purchase_qty": 20}
                    if name != "get_dashboard":
                        m = (
                            await client.get(f"/api/v1/missions/{mission['id']}", headers=test_auth)
                        ).json()
                        arguments["plan_id"] = m["current_plan_id"]
                        if name == "revise_plan":
                            arguments["expected_mission_version"] = m["mission_version"]
                    r = await client.post(
                        "/internal/v1/agent-tools/" + name,
                        json={
                            "run_id": context["run_id"],
                            "invocation_id": "live-" + name,
                            "arguments": arguments,
                        },
                        headers=auth,
                    )
                    assert r.status_code == 200 and r.json()["ok"], r.text
                return {
                    "status": "SUCCEEDED",
                    "content": "待确认方案已更新为20件，尚未采购。",
                    "references": [],
                }

            runner = Runner(
                db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
            )

            async def run_loop():
                while not stop.is_set():
                    await runner.run_once()
                    await asyncio.sleep(0.05)

            loop = asyncio.create_task(run_loop())
            async with httpx.AsyncClient() as readiness:
                for _ in range(100):
                    try:
                        if (await readiness.get(frontend_url, timeout=1)).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    raise AssertionError("Frontend preview did not start")
            browser_env = env | {
                "PROGRESS_FRONTEND": frontend_url,
                "PROGRESS_BACKEND": backend_url,
                "PROGRESS_OUTPUT": str(output),
                "PROGRESS_MISSION": mission["id"],
                "PROGRESS_STORE": mission["store_id"],
                "PROGRESS_AUTH": test_auth["Authorization"].split(" ", 1)[1],
            }
            browser = await asyncio.create_subprocess_exec(
                "node",
                "tests/support/progress_browser.mjs",
                cwd=root / "frontend",
                env=browser_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(browser.communicate(), 100)
            (output / "browser.log").write_bytes(stdout)
            assert browser.returncode == 0, stdout.decode()[-6000:]
    finally:
        if browser and browser.returncode is None:
            browser.terminate()
            await browser.wait()
        for gate in gates.values():
            gate.set()
        stop.set()
        if loop:
            await asyncio.wait_for(loop, 20)
        if frontend and frontend.returncode is None:
            frontend.terminate()
            await frontend.wait()
        server.should_exit = True
        await serving
        backend_socket.close()
        frontend_log.close()
    await app.state.db.dispose()
