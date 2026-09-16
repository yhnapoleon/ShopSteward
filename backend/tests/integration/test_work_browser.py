"""Opt-in production Vue/Nitro + real HTTP/PG, controlled adapter; no model calls."""

import asyncio
import os
import socket
from pathlib import Path

import httpx
import pytest
from test_missions import clean_queue  # noqa: F401
from test_work_items import SERVICE, env

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("WORK_BROWSER_E2E") != "true", reason="Requires built frontend and local browser"
    ),
]


@pytest.mark.parametrize(
    "script", ["work_browser.mjs", "quantity_browser.mjs", "i18n_business_browser.mjs"]
)
async def test_work_intake_browser(db, tmp_path, script):
    import uvicorn

    async with env(db, docs_enabled=False) as (seed, api_client, app):
        if script in {"quantity_browser.mjs", "i18n_business_browser.mjs"}:
            from app.operations.repository import mark_caught_up

            app.state.settings.work_processor_enabled = False
            app.state.settings.source_stale_seconds = 300
            async with db.session() as session, session.begin():
                await mark_caught_up(session, seed["scenario_run_id"], 0)
        execution_task = None
        if script == "i18n_business_browser.mjs":
            from test_execution import Supplier
            from test_missions import body, headers
            from test_planning_jobs import run_check

            from app.execution.jobs import make_handlers
            from app.scheduling.runner import Runner

            # One scoped identity exercises both UI permissions without discovering
            # unrelated stores left by other tests in the shared test database.
            operator = next(
                g for g in app.state.settings.auth_tokens if g.principal_id == "operator"
            )
            operator.roles = ["operator", "approver"]
            created = await api_client.post("/api/v1/missions", json=body(seed), headers=headers())
            assert created.status_code == 201
            await run_check(db, seed)
            runner = Runner(
                db,
                app.state.settings,
                handlers=make_handlers(app.state.settings, client=Supplier()),
            )

            async def execute_purchases():
                while True:
                    await runner.run_once()
                    await asyncio.sleep(0.05)

            execution_task = asyncio.create_task(execute_purchases())
        backend_socket = socket.socket()
        backend_socket.bind(("127.0.0.1", 0))
        backend_url = f"http://127.0.0.1:{backend_socket.getsockname()[1]}"
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        frontend_url = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        serving = asyncio.create_task(server.serve(sockets=[backend_socket]))
        frontend = browser = None
        output = (
            ROOT
            / "var"
            / (
                "i18n-business-browser"
                if script == "i18n_business_browser.mjs"
                else "quantity-browser"
                if script == "quantity_browser.mjs"
                else "work-intake-browser"
            )
        )
        output.mkdir(parents=True, exist_ok=True)
        log = (output / "frontend.log").open("wb")
        try:
            for _ in range(200):
                if server.started:
                    break
                await asyncio.sleep(0.01)
            process_env = os.environ | {
                "NITRO_HOST": "127.0.0.1",
                "NITRO_PORT": str(port),
                "NUXT_BACKEND_URL": backend_url,
                "NUXT_AGENT_ENABLED": "false",
                "NUXT_DEV_TOOLS": "false",
            }
            frontend = await asyncio.create_subprocess_exec(
                "node",
                ".output/server/index.mjs",
                cwd=ROOT / "frontend",
                env=process_env,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
            )
            async with httpx.AsyncClient() as ready:
                for _ in range(100):
                    try:
                        if (await ready.get(frontend_url, timeout=1)).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    raise AssertionError("Frontend did not start")
            from test_missions import TOKENS

            process_env.update(
                WORK_FRONTEND=frontend_url,
                WORK_BACKEND=backend_url,
                WORK_STORE=seed["store_id"],
                WORK_AUTH=TOKENS["operator"],
                WORK_SERVICE=SERVICE,
                WORK_OUTPUT=str(output),
            )
            browser = await asyncio.create_subprocess_exec(
                "node",
                "tests/support/" + script,
                cwd=ROOT / "frontend",
                env=process_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(browser.communicate(), 180)
            (output / "browser.log").write_bytes(stdout)
            assert browser.returncode == 0, stdout.decode()[-6000:]
        finally:
            if execution_task:
                execution_task.cancel()
                try:
                    await execution_task
                except asyncio.CancelledError:
                    pass
            if browser and browser.returncode is None:
                browser.terminate()
                await browser.wait()
            if frontend and frontend.returncode is None:
                frontend.terminate()
                await frontend.wait()
            server.should_exit = True
            await serving
            backend_socket.close()
            log.close()
