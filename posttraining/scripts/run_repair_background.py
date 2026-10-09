"""Run one authorized repair stage, then yield for actual clarification review."""

import argparse
import asyncio
import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from shopsteward_agent.model import OpenAIModel

from shopsteward_pt.eval.commands import evaluate, write_json

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "var/posttraining/repair-call-attempts.jsonl"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["diagnostics", "dev"], required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    run = (
        ROOT
        / "var/posttraining/runs"
        / ("repair-diagnostics-v1" if args.stage == "diagnostics" else "dev-repair-v2")
    )
    run.mkdir(parents=True, exist_ok=True)
    config = (
        ROOT
        / "posttraining/configs"
        / (
            "eval_repair_diagnostics_v1.json"
            if args.stage == "diagnostics"
            else "eval_dev_repair_v2.json"
        )
    )
    state = {
        "pid": os.getpid(),
        "stage": args.stage,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "resume": args.resume,
    }
    write_json(run / "background.json", state)
    if not (run / "source-snapshot.zip").exists():
        paths = []
        for folder in (
            "posttraining/src",
            "posttraining/scripts",
            "posttraining/configs",
            "agent/src/shopsteward_agent/task_policy",
            "backend/app",
        ):
            paths.extend(p for p in (ROOT / folder).rglob("*") if p.suffix in {".py", ".json"})
        with zipfile.ZipFile(run / "source-snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path, path.relative_to(ROOT).as_posix())
        write_json(
            run / "source-hashes.json",
            {
                p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in paths
            },
        )
    count = len(LEDGER.read_text(encoding="utf-8").splitlines()) if LEDGER.exists() else 0
    original = OpenAIModel.complete

    async def counted(model, *positional, **keywords):
        nonlocal count
        if count >= 600:
            raise ValueError("repair model call budget exhausted: 600")
        count += 1
        entry = {
            "attempt": count,
            "stage": args.stage,
            "pid": os.getpid(),
            "time": datetime.now(UTC).isoformat(),
        }
        with LEDGER.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")
        try:
            return await original(model, *positional, **keywords)
        except Exception:
            # Stop a batch on the first API failure; evaluate catches Exception,
            # whereas this control signal must reach the worker supervisor.
            raise SystemExit("model call failed; inspect stage logs before resuming") from None

    OpenAIModel.complete = counted

    async def run_stage():
        if args.stage == "diagnostics":
            return {
                "decision": await evaluate(
                    config, run, ["B1", "B1_candidate"], "decision", resume=args.resume
                )
            }
        decision = await evaluate(config, run, ["B1"], "decision", resume=args.resume)
        execution = await evaluate(
            config, run, ["B1"], "execution", suite="core", resume=args.resume
        )
        return {"decision": decision, "execution": execution}

    code = 0
    try:
        results = asyncio.run(run_stage())
        state.update(status="awaiting_review", results=results)
    except (Exception, SystemExit) as exc:
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc)[:300])
        code = 1
    state.update(finished_at=datetime.now(UTC).isoformat(), total_attempts=count, exit_code=code)
    write_json(run / "background.json", state)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
