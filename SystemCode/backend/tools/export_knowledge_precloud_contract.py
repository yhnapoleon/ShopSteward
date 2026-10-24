"""Export current implemented delivery/service/tool contracts without external IO."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from shopsteward_knowledge.api import create_app as create_knowledge_app  # noqa: E402
from shopsteward_knowledge.config import Settings as KnowledgeSettings  # noqa: E402

from app.agent_bridge.document_evidence import DEFINITIONS  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tools.export_knowledge_contract import references  # noqa: E402


def main():
    from openapi_spec_validator import validate

    runtime = create_app(Settings(_env_file=None, database_url=None, auth_tokens=[])).openapi()
    paths = {
        path: {method: op for method, op in methods.items() if op.get("x-phase") in {"K1", "K2"}}
        for path, methods in runtime["paths"].items()
        if any(op.get("x-phase") in {"K1", "K2"} for op in methods.values())
    }
    schemas, pending = {}, list(set(references(paths)))
    while pending:
        name = pending.pop()
        if name not in schemas:
            schemas[name] = runtime["components"]["schemas"][name]
            pending.extend(references(schemas[name]))
    delivery = {
        **runtime,
        "info": {"title": "ShopSteward Knowledge delivery", "version": "0.1.0"},
        "paths": paths,
        "components": {
            "schemas": dict(sorted(schemas.items())),
            "securitySchemes": runtime["components"]["securitySchemes"],
        },
    }
    service = create_knowledge_app(
        KnowledgeSettings(
            database_url=None,
            opensearch_url=None,
            service_key=None,
            embedding_url=None,
            embedding_api_key=None,
            embedding_model=None,
            embedding_dimensions=None,
        )
    ).openapi()
    validate(delivery)
    validate(service)
    directory = ROOT / "docs/api"
    for name, content in (
        ("knowledge-delivery-v1.openapi.json", delivery),
        ("knowledge-service-v1.openapi.json", service),
    ):
        (directory / name).write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    tools = {
        name: {"description": description, "input_schema": model.model_json_schema()}
        for name, (model, description) in DEFINITIONS.items()
    }
    (directory / "knowledge-document-tools.json").write_text(
        json.dumps(
            {"enabled_when": "KNOWLEDGE_SERVICE_ENABLED", "tools": tools},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "delivery_paths": len(paths),
                "service_paths": len(service["paths"]),
                "document_tools": len(tools),
                "openapi_valid": True,
            }
        )
    )


if __name__ == "__main__":
    main()
