"""Export implemented K1 routes and update runtime inventory without a database."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def references(value):
    if isinstance(value, dict):
        ref = value.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            yield ref.rsplit("/", 1)[-1]
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def main():
    runtime = create_app(Settings(_env_file=None)).openapi()
    paths = {
        path: {method: op for method, op in item.items() if op.get("x-phase") == "K1"}
        for path, item in runtime["paths"].items()
        if any(op.get("x-phase") == "K1" for op in item.values())
    }
    required, pending = {}, list(set(references(paths)))
    while pending:
        name = pending.pop()
        if name not in required:
            required[name] = runtime["components"]["schemas"][name]
            pending.extend(references(required[name]))
    knowledge = {
        **runtime,
        "info": {
            "title": "ShopSteward Knowledge K1 API",
            "version": "0.1.0",
            "description": "Original upload and management only. Parsing/indexing/search are K2+.",
        },
        "paths": paths,
        "components": {
            "schemas": dict(sorted(required.items())),
            "securitySchemes": {
                "UserBearer": runtime["components"]["securitySchemes"]["UserBearer"]
            },
        },
    }
    api = ROOT / "docs/api"
    status = json.loads((api / "implementation-status.json").read_text("utf-8"))
    status["work_package"] = "K0 baseline + K1 knowledge document management"
    status["implemented_operation_ids"] = [
        op["operationId"] for item in runtime["paths"].values() for op in item.values()
    ]
    status["knowledge"] = {
        "phase": "K1",
        "runtime_schema": "knowledge-v1.openapi.json",
        "migration": "0010_knowledge",
        "implemented_operation_ids": [
            op["operationId"] for item in paths.values() for op in item.values()
        ],
        "registered_job_types": [],
        "upload_status": "201 UPLOADED / NOT_INDEXED",
        "planned": ["parsing", "indexing", "search", "reindex", "activation", "Agent tools", "UI"],
    }
    for name, value in [
        ("backend.runtime.openapi.json", runtime),
        ("knowledge-v1.openapi.json", knowledge),
        ("implementation-status.json", status),
    ]:
        (api / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
    count = len(status["knowledge"]["implemented_operation_ids"])
    print(f"Exported {len(paths)} K1 paths / {count} operations")


if __name__ == "__main__":
    main()
