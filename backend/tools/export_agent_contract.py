"""Export the actually registered Agent operations; no database or credentials needed."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    document = create_app(Settings(_env_file=None)).openapi()
    api = ROOT / "docs" / "api"
    write(api / "backend.runtime.openapi.json", document)
    agent = {
        **document,
        "info": {"title": "ShopSteward Agent backend API", "version": "0.1.0"},
        "paths": {
            path: {
                method: operation
                for method, operation in item.items()
                if operation.get("x-phase") == "B2-A"
            }
            for path, item in document["paths"].items()
            if any(op.get("x-phase") == "B2-A" for op in item.values())
        },
    }
    write(api / "agent-v1.openapi.json", agent)
    status = json.loads((api / "implementation-status.json").read_text(encoding="utf-8"))
    status["work_package"] = "B2-A Agent framework"
    status["implemented_operation_ids"] = [
        op["operationId"] for item in document["paths"].values() for op in item.values()
    ]
    status["agent"] = {
        "runtime_schema": "agent-v1.openapi.json",
        "worker_profile": "agent",
        "registered_job_types": ["agent_followup"],
        "deployment": "backend API + independent Agent worker",
        "external_agent_http": "planned",
    }
    write(api / "implementation-status.json", status)
    # Historical design APIs remain planned; this additive input field is shared by both.
    for name in ("backend.openapi.json", "services.openapi.json"):
        path = api / name
        design = json.loads(path.read_text(encoding="utf-8"))
        if "DecisionSnapshot" not in design["components"]["schemas"]:
            continue
        design["components"]["schemas"]["DecisionSnapshot"]["properties"]["task_constraints"] = {
            "type": "object",
            "properties": {"max_purchase_qty": {"type": "integer", "minimum": 0}},
            "additionalProperties": False,
            "default": {},
            "description": "Temporary constraints for the current purchase round; "
            "authoritative cash policy is unchanged.",
        }
        write(path, design)
    print(f"Exported {len(agent['paths'])} Agent paths, {len(document['paths'])} total paths")


if __name__ == "__main__":
    main()
