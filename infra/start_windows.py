"""Start the local Windows frontend, API and workers using existing private config.

Run with .venv/Scripts/python.exe infra/start_windows.py. Migrate first; Docker
Desktop must already be running. A healthy existing simulator is reused. Other
occupied service ports are refused, and only newly created processes are cleaned
up on failure. Secrets are passed in the environment, never command arguments.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main():
    if sys.platform != "win32":
        raise SystemExit("Use infra/local_dev.py for macOS.")
    node = shutil.which("node")
    if not node:
        raise SystemExit("Install Node.js and the locked frontend dependencies first.")
    for port in (3000, 8000):
        if listening(port):
            raise SystemExit(
                f"Port {port} is occupied. Verify its owner before restarting."
            )
    config = {
        k: v for k, v in dotenv_values(ROOT / "backend/.env").items() if v is not None
    }
    env = {**os.environ, **config}
    grants = json.loads(env.get("AUTH_TOKENS", "[]"))
    admin = next(
        (
            g
            for g in grants
            if g.get("kind", "user") == "user" and "admin" in g.get("roles", [])
        ),
        None,
    )
    if not admin:
        raise SystemExit("Configure a backend user admin identity first.")
    agent = env.get("AGENT_ENABLED", "false").lower() == "true"
    if agent and not Path(env.get("AGENT_API_KEY_FILE", "")).is_file():
        raise SystemExit(
            "Configure an existing AGENT_API_KEY_FILE before enabling Agent."
        )
    env.update(
        SIMULATION_BASE_URL="http://127.0.0.1:8001",
        AGENT_BACKEND_URL="http://127.0.0.1:8000",
    )
    frontend_env = {
        **os.environ,
        "NUXT_BACKEND_URL": "http://127.0.0.1:8000",
        "NUXT_BACKEND_TOKEN": admin["token"],
        "NUXT_DEV_TOOLS": "true",
        "NUXT_AGENT_ENABLED": str(agent).lower(),
    }
    log_dir = (
        ROOT / "var" / ("windows-stack-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    created = []
    records = []

    def spawn(name, args, cwd, child_env, port=None):
        with (log_dir / f"{name}.log").open("w", encoding="utf-8") as log:
            child = subprocess.Popen(
                args,
                cwd=ROOT / cwd,
                env=child_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        created.append(child)
        records.append({"component": name, "pid": child.pid, "port": port})

    try:
        if not listening(8001):
            sim_env = {
                **os.environ,
                "SIM_CONSOLE_ENABLED": "true",
                "SIM_BACKEND_BASE_URL": "http://127.0.0.1:8000",
                "SIM_BACKEND_TOKEN": admin["token"],
            }
            spawn(
                "simulator",
                [sys.executable, "-m", "simulator"],
                "simulation",
                sim_env,
                8001,
            )
        else:
            records.append({"component": "existing-simulator", "port": 8001})
        spawn(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ],
            "backend",
            env,
            8000,
        )
        spawn(
            "business-worker",
            [sys.executable, "-m", "app.worker", "--profile", "business"],
            "backend",
            env,
        )
        if agent:
            spawn(
                "agent-worker",
                [sys.executable, "-m", "app.worker", "--profile", "agent"],
                "backend",
                env,
            )
        spawn(
            "frontend",
            [
                node,
                "node_modules/nuxt/bin/nuxt.mjs",
                "dev",
                "--host",
                "127.0.0.1",
                "--port",
                "3000",
            ],
            "frontend",
            frontend_env,
            3000,
        )
        with httpx.Client(timeout=2, trust_env=False) as client:
            for port, path in (
                (8001, "/health/ready"),
                (8000, "/health/ready"),
                (3000, "/api/session"),
            ):
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if any(p.poll() is not None for p in created):
                        raise RuntimeError(f"A service exited. Inspect {log_dir}")
                    try:
                        response = client.get(f"http://127.0.0.1:{port}{path}")
                        if response.status_code == 200:
                            if port == 3000 and not response.json().get(
                                "authenticated"
                            ):
                                raise RuntimeError(
                                    "Frontend identity could not connect to backend."
                                )
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError(f"Service {port} not ready. Inspect {log_dir}")
        result = {
            "started_at": datetime.now(UTC).isoformat(),
            "agent_enabled": agent,
            "model": env.get("AGENT_MODEL") if agent else None,
            "processes": records,
            "logs": str(log_dir),
            "frontend": "http://127.0.0.1:3000",
        }
        (log_dir / "processes.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
    except BaseException:
        for child in reversed(created):
            if child.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
        raise


if __name__ == "__main__":
    main()
