"""Manage this Mac's isolated development services; never calls a real model.

Run with .venv/bin/python infra/local_dev.py {start,stop,status,migrate,test,smoke}.
Configuration is read from ignored .env files. PostgreSQL must be installed first.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path.home() / ".local/share/shopsteward"
PYTHON = ROOT / ".venv/bin/python"
PG_BIN = Path("/opt/homebrew/opt/postgresql@17/bin")
PG_DATA = RUNTIME / "postgres"
STATE = RUNTIME / "processes.json"
LOGS = RUNTIME / "logs"


def config(directory: str) -> dict[str, str]:
    return {
        k: v
        for k, v in dotenv_values(ROOT / directory / ".env").items()
        if v is not None
    }


def run(command, cwd=ROOT, env=None):
    subprocess.run([str(v) for v in command], cwd=cwd, env=env, check=True)


def birth(pid):
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def owned(record):
    return birth(record["pid"]) == record["birth"] and record["birth"] is not None


def registry():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(records):
    STATE.write_text(json.dumps(records, indent=2) + "\n")


def port_open(port):
    with socket.socket() as connection:
        connection.settimeout(0.3)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def database_start():
    if (
        subprocess.run(
            [str(PG_BIN / "pg_ctl"), "-D", str(PG_DATA), "status"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    ):
        return
    if port_open(55432):
        raise RuntimeError(
            "Port 55432 is occupied by another instance; nothing was stopped"
        )
    run(
        [
            PG_BIN / "pg_ctl",
            "-D",
            PG_DATA,
            "-l",
            RUNTIME / "postgres.log",
            "-w",
            "start",
        ]
    )


def start():
    database_start()
    LOGS.mkdir(parents=True, exist_ok=True)
    records = registry()
    services = [
        (
            "simulator",
            [PYTHON, "-m", "simulator"],
            ROOT / "simulation",
            8001,
            "/health/ready",
        ),
        ("api", [PYTHON, "-m", "app"], ROOT / "backend", 8000, "/health/ready"),
        (
            "worker",
            [PYTHON, "-m", "app.worker", "--profile", "business"],
            ROOT / "backend",
            None,
            None,
        ),
        (
            "frontend",
            [
                "corepack",
                "pnpm",
                "--filter",
                "@shopsteward/frontend",
                "exec",
                "nuxt",
                "dev",
                "--host",
                "127.0.0.1",
                "--port",
                "3000",
            ],
            ROOT,
            3000,
            "/",
        ),
    ]
    env = os.environ.copy()
    env.update(NUXT_TELEMETRY_DISABLED="1", CI="1", AGENT_ENABLED="false")
    # Only the loopback frontend receives the local development user credential.
    # It stays in Nitro server runtime config, never in the public client bundle.
    frontend_env = env.copy()
    grants = json.loads(config("backend").get("AUTH_TOKENS", "[]"))
    admin = next(
        (
            g
            for g in grants
            if g.get("kind", "user") == "user" and "admin" in g.get("roles", [])
        ),
        None,
    )
    if admin:
        frontend_env.update(NUXT_BACKEND_TOKEN=admin["token"], NUXT_DEV_TOOLS="true")
    frontend_env.update(
        NUXT_BACKEND_URL="http://127.0.0.1:8000", NUXT_AGENT_ENABLED="false"
    )
    for name, command, directory, port, endpoint in services:
        if name in records and owned(records[name]):
            print(name + ": already running")
            continue
        if port and port_open(port):
            raise RuntimeError(
                f"Port {port} is occupied by an unregistered process; nothing was stopped"
            )
        with (LOGS / (name + ".log")).open("ab") as log:
            process = subprocess.Popen(
                [str(v) for v in command],
                cwd=directory,
                env=frontend_env if name == "frontend" else env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        records[name] = {"pid": process.pid, "birth": birth(process.pid), "port": port}
        save(records)
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited; see {LOGS / (name + '.log')}")
            if port:
                try:
                    with urlopen(
                        f"http://127.0.0.1:{port}{endpoint}", timeout=2
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
            else:
                time.sleep(1)
                if process.poll() is None:
                    break
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"{name} startup timed out; use status/stop and inspect its log"
                )
            time.sleep(0.3)
        print(f"{name}: started ({process.pid})")
    print(
        "Ready: frontend http://127.0.0.1:3000 ; "
        "API http://127.0.0.1:8000/docs ; real model disabled"
    )


def stop():
    records = registry()
    for name, record in reversed(list(records.items())):
        if owned(record):
            os.killpg(record["pid"], signal.SIGTERM)
            deadline = time.monotonic() + 20
            while owned(record) and time.monotonic() < deadline:
                time.sleep(0.2)
            if owned(record):
                raise RuntimeError(
                    f"{name} did not stop gracefully; no forced kill performed"
                )
        records.pop(name)
        save(records)
    if (
        subprocess.run(
            [str(PG_BIN / "pg_ctl"), "-D", str(PG_DATA), "status"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    ):
        run([PG_BIN / "pg_ctl", "-D", PG_DATA, "-m", "fast", "-w", "stop"])
    print("Project services stopped; databases and files retained")


def status():
    pg_status = subprocess.run(
        [str(PG_BIN / "pg_ctl"), "-D", str(PG_DATA), "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    print("PostgreSQL: " + ("running" if pg_status.returncode == 0 else "stopped"))
    for name, record in registry().items():
        print(
            f"{name}: {'running' if owned(record) else 'stopped'}; port={record['port']}"
        )
    print("Agent worker: disabled; no real model API configured")


def test_environment():
    from sqlalchemy.engine import make_url

    env = os.environ.copy()
    db = make_url(config("backend")["DATABASE_URL"]).set(database="shopsteward_test")
    sim = make_url(config("simulation")["SIM_DATABASE_URL"]).set(
        database="shopsteward_sim_test"
    )
    assert db.host == sim.host == "127.0.0.1" and db.port == sim.port == 55432
    env.update(
        TEST_DATABASE_URL=db.render_as_string(hide_password=False),
        TEST_SIM_DATABASE_URL=sim.render_as_string(hide_password=False),
        AGENT_ENABLED="false",
    )
    return env


def migrate():
    database_start()
    test_env = test_environment()
    for directory, key, test_key in [
        ("simulation", "SIM_DATABASE_URL", "TEST_SIM_DATABASE_URL"),
        ("backend", "DATABASE_URL", "TEST_DATABASE_URL"),
    ]:
        run([PYTHON, "-m", "alembic", "upgrade", "head"], ROOT / directory)
        env = test_env.copy()
        env[key] = env[test_key]
        run([PYTHON, "-m", "alembic", "upgrade", "head"], ROOT / directory, env)


def test():
    database_start()
    LOGS.mkdir(parents=True, exist_ok=True)
    env = test_environment()
    env["DATABASE_URL"] = env["TEST_DATABASE_URL"]
    env["SIM_DATABASE_URL"] = env["TEST_SIM_DATABASE_URL"]
    run(
        [
            PYTHON,
            "-m",
            "pytest",
            "tests",
            "../agent/tests",
            "-c",
            "pyproject.toml",
            "-q",
            "--junitxml=" + str(LOGS / "backend-agent-tests.xml"),
        ],
        ROOT / "backend",
        env,
    )
    run(
        [
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "--junitxml=" + str(LOGS / "simulator-tests.xml"),
        ],
        ROOT / "simulation",
        env,
    )


def smoke(restart=False):
    # Uses the real local business API/worker/simulator and synthetic SC01 data.
    # The output is local, so the team's historical evidence is not overwritten.
    sys.path.insert(0, str(ROOT / "backend"))
    from app.smoke_execution import run as smoke_run

    LOGS.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT / "backend")
    asyncio.run(
        smoke_run(restart, output=LOGS / "macos-periodic-smoke.json", automatic=True)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["start", "stop", "status", "migrate", "test", "smoke"]
    )
    parser.add_argument(
        "--verify-restart",
        action="store_true",
        help="Verify the previous smoke scene after restarting services",
    )
    args = parser.parse_args()
    if args.command == "smoke":
        smoke(args.verify_restart)
    else:
        globals()[args.command]()
