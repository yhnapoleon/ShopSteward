"""Run real browser/Agent environment synchronization on dedicated local databases.

Uses ports 8018/8019/3018. Production must be built first. Existing user services,
databases, scene selection and credentials are not modified. Requires Windows.
"""

import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import asyncpg
import httpx
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


async def prepare_databases(url):
    conn = await asyncpg.connect(
        url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    )
    try:
        for name in ("shopsteward_environment_test", "shopsteward_sim_environment_test"):
            if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name):
                await conn.execute('CREATE DATABASE "' + name + '"')
    finally:
        await conn.close()


def main():
    for port in (8018, 8019, 3018):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    config = {k: v for k, v in dotenv_values(ROOT / "backend/.env").items() if v is not None}
    url = make_url(config["DATABASE_URL"])
    asyncio.run(prepare_databases(url))
    token, service = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    env = {
        **os.environ,
        **config,
        "DATABASE_URL": url.set(database="shopsteward_environment_test").render_as_string(
            hide_password=False
        ),
        "SIM_DATABASE_URL": url.set(database="shopsteward_sim_environment_test").render_as_string(
            hide_password=False
        ),
        "AUTH_TOKENS": json.dumps(
            [{"token": token, "principal_id": "environment-e2e", "roles": ["admin"]}]
        ),
        "SIMULATION_BASE_URL": "http://127.0.0.1:8019",
        "SIMULATION_TOKEN": service,
        "SIM_SERVICE_TOKEN": service,
        "SIM_CONSOLE_ENABLED": "true",
        "SIM_BACKEND_BASE_URL": "http://127.0.0.1:8018",
        "SIM_BACKEND_TOKEN": token,
        "AGENT_BACKEND_URL": "http://127.0.0.1:8018",
        "NUXT_BACKEND_URL": "http://127.0.0.1:8018",
        "NUXT_DEV_TOOLS": "true",
        "NUXT_AGENT_ENABLED": "true",
        "NITRO_HOST": "127.0.0.1",
        "NITRO_PORT": "3018",
        "FRONTEND_URL": "http://127.0.0.1:3018",
        "SIMULATOR_URL": "http://127.0.0.1:8019",
        "ENVIRONMENT_E2E": "true",
        "ENVIRONMENT_TEST_TOKEN": token,
    }
    logs = ROOT / "var/environment-e2e"
    logs.mkdir(parents=True, exist_ok=True)
    for folder in ("backend", "simulation"):
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / folder,
            env=env,
            check=True,
        )
    children = []

    def start(name, args, folder):
        with (logs / (name + ".log")).open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                args,
                cwd=ROOT / folder,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        children.append(process)

    try:
        start(
            "simulator",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "simulator.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8019",
                "--no-access-log",
            ],
            "simulation",
        )
        start(
            "backend",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8018",
                "--no-access-log",
            ],
            "backend",
        )
        start("business", [sys.executable, "-m", "app.worker", "--profile", "business"], "backend")
        start("agent", [sys.executable, "-m", "app.worker", "--profile", "agent"], "backend")
        start("frontend", [shutil.which("node"), ".output/server/index.mjs"], "frontend")
        with httpx.Client(timeout=2, trust_env=False) as client:
            for endpoint in (
                "http://127.0.0.1:8018/health/ready",
                "http://127.0.0.1:8019/health/ready",
                "http://127.0.0.1:3018/api/session",
            ):
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if any(p.poll() is not None for p in children):
                        raise RuntimeError(
                            "An isolated service exited; inspect var/environment-e2e"
                        )
                    try:
                        if client.get(endpoint).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Isolated service not ready: " + endpoint)
        result = subprocess.run(
            [
                shutil.which("node"),
                "node_modules/@playwright/test/cli.js",
                "test",
                "environment.spec.ts",
                *sys.argv[1:],
                "--output=../var/environment-e2e/artifacts",
                "--reporter=line",
            ],
            cwd=ROOT / "frontend",
            env=env,
        )
        return result.returncode
    finally:
        for process in reversed(children):
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )


if __name__ == "__main__":
    raise SystemExit(main())
