"""Start the local persistent simulator console, optionally with backend/business worker.

Docker Desktop must already be running. Does not edit .env, start Docker, or enable Agent.
Run from any directory with the repository Python: --migrate --with-backend.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def free_port(port):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--with-backend", action="store_true")
    args = parser.parse_args()
    free_port(8001)
    if args.with_backend:
        free_port(8000)
    log_dir = ROOT / "var" / ("simulator-console-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    log_dir.mkdir(parents=True, exist_ok=True)
    sim_env, backend_env = os.environ.copy(), os.environ.copy()
    sim_env["SIM_CONSOLE_ENABLED"] = "true"
    backend_env["AGENT_ENABLED"] = "false"
    backend_env["SIMULATION_BASE_URL"] = "http://127.0.0.1:8001"
    sim_env["SIM_BACKEND_BASE_URL"] = "http://127.0.0.1:8000"
    backend_config = dotenv_values(ROOT / "backend/.env")
    grants = json.loads(backend_env.get("AUTH_TOKENS", backend_config.get("AUTH_TOKENS", "[]")))
    admins = [
        g for g in grants if g.get("kind", "user") == "user" and "admin" in g.get("roles", [])
    ]
    if admins and not sim_env.get("SIM_BACKEND_TOKEN"):
        sim_env["SIM_BACKEND_TOKEN"] = admins[0]["token"]
    if args.with_backend and not sim_env.get("SIM_BACKEND_TOKEN"):
        raise SystemExit("Configure a backend admin identity before --with-backend.")
    processes = []

    def spawn(name, module_args, directory, env):
        with (log_dir / (name + ".log")).open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", *module_args],
                cwd=ROOT / directory,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        return process

    try:
        if args.migrate:
            for directory, env in [("simulation", sim_env)] + (
                [("backend", backend_env)] if args.with_backend else []
            ):
                p = spawn(directory + "-migration", ["alembic", "upgrade", "head"], directory, env)
                processes.append(p)
                if p.wait(timeout=60):
                    raise RuntimeError("Migration failed; inspect " + str(log_dir))
        sim = spawn(
            "simulator",
            [
                "uvicorn",
                "simulator.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
                "--no-access-log",
            ],
            "simulation",
            sim_env,
        )
        processes.append(sim)
        running = [{"component": "simulator-console", "pid": sim.pid, "port": 8001}]
        if args.with_backend:
            api = spawn(
                "backend-api",
                [
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                    "--no-access-log",
                ],
                "backend",
                backend_env,
            )
            worker = spawn(
                "business-worker", ["app.worker", "--profile", "business"], "backend", backend_env
            )
            processes.extend([api, worker])
            running += [
                {"component": "backend-api", "pid": api.pid, "port": 8000},
                {"component": "business-worker", "pid": worker.pid},
            ]
        with httpx.Client(timeout=2, trust_env=False) as client:
            for port in [8001] + ([8000] if args.with_backend else []):
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    if any(p.poll() is not None and p.returncode != 0 for p in processes):
                        raise RuntimeError("Service exited; inspect " + str(log_dir))
                    try:
                        if client.get(f"http://127.0.0.1:{port}/health/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.3)
                else:
                    raise RuntimeError("Service not ready; inspect " + str(log_dir))
        result = {
            "started_at": datetime.now(UTC).isoformat(),
            "processes": running,
            "dashboard": "http://127.0.0.1:8001/console/",
            "logs": str(log_dir),
            "agent_enabled": False,
        }
        (log_dir / "processes.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except BaseException:
        for p in reversed(processes):
            if p.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True
                    )
                else:
                    p.terminate()
        raise


if __name__ == "__main__":
    main()
