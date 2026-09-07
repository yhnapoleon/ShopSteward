"""Export registered APIs without database access or credentials."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "simulation"), str(ROOT / "backend")]
from app.core.config import Settings as BackendSettings  # noqa: E402
from app.main import create_app as backend_app  # noqa: E402

from simulator.config import Settings  # noqa: E402
from simulator.main import create_app  # noqa: E402


def main():
    api = ROOT / "docs/api"

    def write(name, value):
        (api / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    backend = backend_app(BackendSettings(_env_file=None)).openapi()
    simulation = create_app(Settings(_env_file=None, sim_console_enabled=False)).openapi()
    console = create_app(Settings(_env_file=None, sim_console_enabled=True)).openapi()
    write("backend.runtime.openapi.json", backend)
    write("simulation.runtime.openapi.json", simulation)
    write("simulator-console.runtime.openapi.json", console)
    # Keep historical planned endpoints and examples; update the shared seed input only.
    for name in ("backend.openapi.json", "services.openapi.json"):
        design = json.loads((api / name).read_text("utf-8"))
        for schema in ("ScenarioCreate", "ScenarioParameters"):
            design["components"]["schemas"][schema] = simulation["components"]["schemas"][schema]
        write(name, design)
    status = json.loads((api / "implementation-status.json").read_text("utf-8"))
    status["simulation"].update(
        implemented_operation_ids=[
            op["operationId"]
            for path, item in simulation["paths"].items()
            if path.startswith("/sim/")
            for op in item.values()
        ],
        console_schema="simulator-console.runtime.openapi.json",
        console="opt-in loopback /console/; durable SANDBOX seeds and typed triggers",
        migration="sim_0003_controls",
    )
    write("implementation-status.json", status)
    print("Exported backend, simulator service and opt-in console runtime contracts.")


if __name__ == "__main__":
    main()
