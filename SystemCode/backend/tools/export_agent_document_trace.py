"""Read only the completed synthetic acceptance run checkpoints; never invoke a model."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


async def export(args):
    from shopsteward_agent import FencedPostgresSaver

    from app.core.config import Settings

    source = json.loads(args.report.read_text("utf-8"))
    if source.get("database") != "shopsteward_test":
        raise ValueError("isolated acceptance report required")
    os.chdir(ROOT / "backend")
    settings = Settings()
    url = make_url(settings.database_url.get_secret_value()).set(
        database="shopsteward_test", drivername="postgresql"
    )
    if url.host not in {"localhost", "127.0.0.1"}:
        raise ValueError("local test database required")

    async def reject_write(_):
        raise RuntimeError("read-only checkpoint export")

    saver = FencedPostgresSaver(url.render_as_string(hide_password=False), reject_write)
    output = {
        "source_report": args.report.name,
        "mode": "actual_persisted_graph_checkpoints",
        "runs": [],
    }
    for run in source["runs"]:
        identifier = run["run"]["id"]
        checkpoint = await saver.aget_tuple({"configurable": {"thread_id": identifier}})
        if checkpoint is None:
            raise ValueError("checkpoint missing")
        values = checkpoint.checkpoint["channel_values"]
        calls, results = [], []
        for message in values.get("messages", []):
            for call in message.get("tool_calls", []):
                calls.append(
                    {
                        "call_id": call["id"],
                        "tool": call["function"]["name"],
                        "arguments": json.loads(call["function"]["arguments"]),
                    }
                )
            if message.get("role") == "tool":
                value = json.loads(message["content"])
                data = value.get("data", {})
                results.append(
                    {
                        "call_id": message["tool_call_id"],
                        "ok": value.get("ok"),
                        "references": value.get("references", []),
                        "candidate_count": len(data.get("candidates", [])),
                        "candidates": data.get("candidates", []),
                        "timings_ms": data.get("timings_ms"),
                        "degraded": data.get("degraded"),
                        "warnings": data.get("warnings"),
                    }
                )
        output["runs"].append(
            {
                "scenario": run["scenario"],
                "run_id": identifier,
                "required_tools": values.get("required_tools", []),
                "completed_tools": values.get("completed_tools", []),
                "model_calls": values.get("model_calls"),
                "tool_calls": values.get("tool_calls"),
                "calls": calls,
                "tool_results": results,
            }
        )
    if args.output.exists():
        raise ValueError("use a new export path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"runs": len(output["runs"]), "mode": output["mode"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(export(args))
