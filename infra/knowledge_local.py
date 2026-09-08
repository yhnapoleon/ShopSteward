"""Own only the independent knowledge Compose project. Never launch Docker Desktop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = "shopsteward-knowledge-precloud"
SERVICES = ("postgres", "opensearch", "api", "worker")
PORT_DEFAULTS = {
    "KNOWLEDGE_API_PORT": 8020,
    "KNOWLEDGE_POSTGRES_PORT": 55434,
    "KNOWLEDGE_OPENSEARCH_PORT": 19201,
}


def check_ports(ports):
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise ValueError(
                    f"loopback port {port} is occupied; no process was stopped"
                ) from None


def docker(args, *, env=None, timeout=30):
    try:
        result = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError(
            "Docker unavailable; start Docker Desktop manually and retry"
        ) from None
    if result.returncode:
        if args[0] == "info":
            raise ValueError(
                "Docker daemon unavailable; start Docker Desktop manually and retry"
            )
        raise ValueError(
            "Docker command failed; diagnostic output suppressed to protect credentials"
        )
    return result.stdout.strip()


def read_private_env(path):
    if not path.is_file():
        raise ValueError("provide --env-file pointing to a private task configuration")
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"KNOWLEDGE_[A-Z0-9_]+", key):
            raise ValueError(
                "private configuration accepts only KNOWLEDGE_* assignments"
            )
        value = value.strip()
        if value[:1] in {"'", '"'}:
            if value[-1:] != value[:1]:
                raise ValueError("invalid quoted private configuration")
            value = value[1:-1]
        if "$" in value or "\x00" in value:
            raise ValueError("private configuration must use literal values")
        if key in values:
            raise ValueError("duplicate private configuration key")
        values[key] = value
    for key in ("KNOWLEDGE_SERVICE_KEY", "KNOWLEDGE_POSTGRES_PASSWORD"):
        if not values.get(key) or values[key].startswith("replace-"):
            raise ValueError("set private credentials before using Compose")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", values["KNOWLEDGE_POSTGRES_PASSWORD"]):
        raise ValueError(
            "use a URL-safe PostgreSQL password in the private Compose configuration"
        )
    db = values.get("KNOWLEDGE_POSTGRES_DB", "shopsteward_knowledge_test")
    if not re.fullmatch(r"shopsteward_knowledge_test(?:_[a-z0-9]+)*", db):
        raise ValueError("Compose requires a dedicated knowledge test database")
    return values


class Manager:
    def __init__(self, *, env_file, project=PROJECT, state_dir=None):
        if not re.fullmatch(
            r"shopsteward-knowledge-precloud(?:-restore-[a-z0-9-]+)?", project
        ):
            raise ValueError(
                "use the independent precloud project or a named restore project"
            )
        self.project = project
        self.values = read_private_env(Path(env_file))
        self.ports = {
            key: int(self.values.get(key, default))
            for key, default in PORT_DEFAULTS.items()
        }
        if len(set(self.ports.values())) != 3 or any(
            p in {8000, 8001} or not 1024 <= p <= 65535 for p in self.ports.values()
        ):
            raise ValueError(
                "use three distinct unprivileged ports; 8000/8001 are reserved"
            )
        if project != PROJECT and any(
            self.ports[k] == p for k, p in PORT_DEFAULTS.items()
        ):
            raise ValueError("restore project needs three separate ports")
        self.env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("COMPOSE_", "KNOWLEDGE_"))
        }
        self.env.update(self.values, COMPOSE_DISABLE_ENV_FILE="1")
        self.base = [
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(Path(env_file).resolve()),
            "--file",
            str(REPO / "infra/compose.knowledge.yaml"),
        ]
        self.state = Path(state_dir or REPO / "var/knowledge-precloud") / (
            project + ".json"
        )
        if self.state.exists():
            receipt = json.loads(self.state.read_text()).get("build", {})
            self.env.update(receipt.get("pinned_images", {}))

    def compose(self, *args, timeout=30):
        return docker([*self.base, *args], env=self.env, timeout=timeout)

    def containers(self):
        ids = docker(
            [
                "ps",
                "-aq",
                "--filter",
                "label=com.docker.compose.project=" + self.project,
            ]
        )
        if not ids:
            return []
        # Do not retrieve container Config.Env: it contains the private credentials.
        result = docker(
            ["inspect", "--format", "{{json .Id}} {{json .State.Pid}}", *ids.split()]
        )
        return [
            {"id": row.split()[0].strip('"'), "pid": int(row.split()[1])}
            for row in result.splitlines()
        ]

    def ownership(self):
        current = self.containers()
        saved = json.loads(self.state.read_text()) if self.state.exists() else {}
        allowed = {row["id"] for row in saved.get("containers", [])}
        if any(row["id"] not in allowed for row in current):
            raise ValueError(
                "project has containers not owned by this helper; inspect manually"
            )
        return current

    def record(self, **extra):
        previous = json.loads(self.state.read_text()) if self.state.exists() else {}
        previous.update(project=self.project, containers=self.containers(), **extra)
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")

    def check(self):
        self.compose("config", "--quiet")
        check_ports(self.ports.values())
        return {
            "project": self.project,
            "bind": "127.0.0.1",
            "ports": self.ports,
            "docker": "available",
            "integration": "not_run",
        }

    def build(self):
        self.ownership()
        # Resolve the exact pulled runtime/dependency references, without guessing a digest.
        refs = {
            "python": self.values.get(
                "KNOWLEDGE_PYTHON_IMAGE", "python:3.12-slim-trixie"
            ),
            "uv": self.values.get("KNOWLEDGE_UV_IMAGE", "ghcr.io/astral-sh/uv:0.12.10"),
            "postgres": self.values.get(
                "KNOWLEDGE_POSTGRES_IMAGE", "postgres:17-bookworm"
            ),
            "opensearch": self.values.get(
                "KNOWLEDGE_OPENSEARCH_IMAGE", "opensearchproject/opensearch:3.8.0"
            ),
        }
        digests = {}
        for name, reference in refs.items():
            docker(["pull", reference], timeout=600)
            digests[name] = json.loads(
                docker(
                    ["image", "inspect", "--format", "{{json .RepoDigests}}", reference]
                )
            )
            if not digests[name]:
                raise ValueError(
                    "pulled image has no registry digest; cannot pin build"
                )
        pinned = {
            "KNOWLEDGE_" + name.upper() + "_IMAGE": values[0]
            for name, values in digests.items()
        }
        self.env.update(pinned)
        self.compose("build", "api", timeout=900)
        image_ref = self.values.get("KNOWLEDGE_IMAGE", "shopsteward-knowledge:precloud")
        image_id = docker(["image", "inspect", "--format", "{{.Id}}", image_ref])
        receipt = {
            "image_id": image_id,
            "resolved_digests": digests,
            "pinned_images": pinned,
            "lock_sha256": hashlib.sha256((REPO / "uv.lock").read_bytes()).hexdigest(),
            "base_digest_pinning": "passed",
        }
        self.record(build=receipt)
        return receipt

    def start(self, *, migrate=False):
        current = self.ownership()
        saved = json.loads(self.state.read_text()) if self.state.exists() else {}
        built = saved.get("build", {})
        reference = self.values.get("KNOWLEDGE_IMAGE", "shopsteward-knowledge:precloud")
        if not built or docker(
            ["image", "inspect", "--format", "{{.Id}}", reference]
        ) != built.get("image_id"):
            raise ValueError(
                "run build first; current image must match the recorded build"
            )
        if not current:
            check_ports(self.ports.values())
        else:
            # Existing owned PostgreSQL from explicit migration is allowed; check
            # unbound service ports before asking Compose to add their containers.
            rows = self.compose("ps", "--format", "json", "--all")
            parsed = (
                json.loads(rows)
                if rows.startswith("[")
                else [json.loads(r) for r in rows.splitlines()]
            )
            running = {r["Service"] for r in parsed if r.get("State") == "running"}
            for service, key in (
                ("api", "KNOWLEDGE_API_PORT"),
                ("postgres", "KNOWLEDGE_POSTGRES_PORT"),
                ("opensearch", "KNOWLEDGE_OPENSEARCH_PORT"),
            ):
                if service not in running:
                    check_ports([self.ports[key]])
        try:
            if migrate:
                self.compose(
                    "up", "-d", "--no-build", "--wait", "postgres", timeout=180
                )
                self.compose("run", "--rm", "--no-deps", "migrate", timeout=180)
            else:
                self.compose(
                    "up",
                    "-d",
                    "--no-build",
                    "--wait",
                    "--wait-timeout",
                    "180",
                    *SERVICES,
                    timeout=240,
                )
        finally:
            # Record containers even if health/migration fails; stop can safely release them.
            self.record()
        return {
            "project": self.project,
            "migration" if migrate else "startup": "passed",
        }

    def status(self):
        rows = self.compose("ps", "--format", "json", "--all")
        parsed = (
            json.loads(rows)
            if rows.startswith("[")
            else [json.loads(r) for r in rows.splitlines()]
        )
        return {
            "project": self.project,
            "services": [
                {k: row.get(k) for k in ("Service", "State", "Health")}
                for row in parsed
            ],
        }

    def stop(self):
        owned = self.ownership()
        if owned:
            docker(["stop", "--time", "30", *(r["id"] for r in owned)], timeout=180)
        self.record()
        return {
            "project": self.project,
            "containers_stopped": len(owned),
            "volumes": "retained",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["check", "build", "migrate", "start", "status", "stop"]
    )
    parser.add_argument(
        "--env-file", type=Path, default=REPO / "var/knowledge-precloud/private.env"
    )
    parser.add_argument("--project", default=PROJECT)
    args = parser.parse_args(argv)
    try:
        docker(["info", "--format", "{{.ServerVersion}}"])
        manager = Manager(env_file=args.env_file, project=args.project)
        result = (
            manager.start(migrate=True)
            if args.command == "migrate"
            else getattr(manager, args.command)()
        )
        print(json.dumps(result))
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
