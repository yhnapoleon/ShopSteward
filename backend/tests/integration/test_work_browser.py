"""Opt-in production Vue/Nitro + real HTTP/PG, controlled adapter; no model calls."""

import asyncio
import os
import socket
from pathlib import Path

import httpx
import pytest
from test_work_items import SERVICE, env

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("WORK_BROWSER_E2E") != "true", reason="Requires built frontend and local browser"
    ),
]


async def test_work_intake_browser(db, tmp_path):
    import uvicorn

    async with env(db, docs_enabled=False) as (seed, _, app):
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
        output = ROOT / "var/work-intake-browser"
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
                "tests/support/work_browser.mjs",
                cwd=ROOT / "frontend",
                env=process_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(browser.communicate(), 180)
            (output / "browser.log").write_bytes(stdout)
            assert browser.returncode == 0, stdout.decode()[-6000:]
        finally:
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
