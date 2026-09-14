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
from urllib.parse import urlsplit

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
    # Always import this checkout, even when using an existing shared interpreter.
    env["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / path)
        for path in ("backend", "agent/src", "ml/src", "simulation", "knowledge/src")
    )
    forecast = env.get("FORECAST_V6_ENABLED", "false").lower() == "true"
    if forecast:
        url = urlsplit(env.get("FORECAST_V6_URL", "http://127.0.0.1:8053"))
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.path not in ("", "/")
        ):
            raise SystemExit("Windows launcher requires a loopback FORECAST_V6_URL.")
        forecast_port = url.port or 8053
        if listening(forecast_port):
            raise SystemExit(
                f"Forecast port {forecast_port} is occupied; verify its owner first."
            )
        if not env.get("FORECAST_V6_TOKEN"):
            raise SystemExit("Configure FORECAST_V6_TOKEN before enabling v6.")
        bundle = Path(
            env.get("ML_V6_BUNDLE", str(ROOT / "var/forecast-v6/bundle"))
        ).resolve()
        if not (bundle / "manifest.json").is_file():
            raise SystemExit("Package the v6 bundle before starting.")
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
        if forecast:
            spawn(
                "forecast-v6",
                [
                    env.get("ML_PYTHON", sys.executable),
                    "-m",
                    "uvicorn",
                    "shopsteward_ml.service:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(forecast_port),
                    "--no-access-log",
                ],
                ".",
                env
                | {
                    "ML_SERVICE_TOKEN": env["FORECAST_V6_TOKEN"],
                    "ML_V6_BUNDLE": str(bundle),
                },
                forecast_port,
            )
        if not listening(8001):
            sim_env = {
                **os.environ,
                "SIM_CONSOLE_ENABLED": "true",
                "SIM_BACKEND_BASE_URL": "http://127.0.0.1:8000",
                "SIM_BACKEND_TOKEN": admin["token"],
                "PYTHONPATH": env["PYTHONPATH"],
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
            checks = [
                (8001, "/health/ready"),
                (8000, "/health/ready"),
                (3000, "/api/session"),
            ]
            if forecast:
                checks.insert(0, (forecast_port, "/health/ready"))
            for port, path in checks:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if any(p.poll() is not None for p in created):
                        raise RuntimeError(f"A service exited. Inspect {log_dir}")
                    try:
                        headers = (
                            {"Authorization": "Bearer " + env["FORECAST_V6_TOKEN"]}
                            if forecast and port == forecast_port
                            else {}
                        )
                        response = client.get(
                            f"http://127.0.0.1:{port}{path}", headers=headers
                        )
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
            "forecast_v6_enabled": forecast,
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
