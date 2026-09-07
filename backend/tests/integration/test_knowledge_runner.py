import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url


def main():
    """Test-only entry point: derive a dedicated DB URL without printing credentials."""
    import os

    backend = Path(__file__).resolve().parents[2]
    values = {}
    for line in (backend / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    url = make_url(values["DATABASE_URL"]).set(database="shopsteward_test")
    assert url.database == "shopsteward_test" and url.drivername == "postgresql+asyncpg"
    env = dict(
        os.environ,
        DATABASE_URL=url.render_as_string(hide_password=False),
        TEST_DATABASE_URL=url.render_as_string(hide_password=False),
        APP_ENV="test",
    )
    arguments = sys.argv[1:]
    if "--with-simulator-db" in arguments:
        arguments.remove("--with-simulator-db")
        simulator_values = {}
        for line in (
            (backend.parent / "simulation/.env").read_text(encoding="utf-8-sig").splitlines()
        ):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                simulator_values[key.strip()] = value.strip().strip("\"'")
        simulator_url = make_url(simulator_values["SIM_DATABASE_URL"]).set(
            database="shopsteward_sim_test"
        )
        assert simulator_url.database == "shopsteward_sim_test"
        env["TEST_SIM_DATABASE_URL"] = simulator_url.render_as_string(hide_password=False)
    if arguments == ["migrate"]:
        command = [sys.executable, "-m", "alembic", "upgrade", "head"]
    elif arguments == ["schema-check"]:
        command = [sys.executable, "-m", "alembic", "check"]
    elif arguments == ["heads"]:
        command = [sys.executable, "-m", "alembic", "current"]
    else:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(backend / "pyproject.toml"),
            *(arguments or ["tests/integration/test_knowledge_documents.py", "-q"]),
        ]
    raise SystemExit(subprocess.call(command, cwd=backend, env=env))


if __name__ == "__main__":
    main()
