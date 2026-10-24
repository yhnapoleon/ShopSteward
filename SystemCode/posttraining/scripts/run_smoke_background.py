"""Run smoke or dev baselines, then yield for question review and continuation."""

import argparse
import asyncio
import hashlib
import os
import shutil
import sys
import traceback
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for folder in ("backend", "agent/src", "posttraining/src", "knowledge/src", "simulation"):
    sys.path.insert(0, str(ROOT / folder))

from shopsteward_pt.eval.commands import evaluate, freeze, write_json  # noqa: E402


async def run(directory, config, suite, freeze_first):
    if freeze_first:
        write_json(
            directory / "status.json",
            {"status": "freezing", "updated_at": datetime.now(UTC).isoformat()},
        )
        await freeze(config)
    await evaluate(config, directory, ["B0", "B1"], "decision", resume=True)
    # Exact-question matching still applies; these are the already reviewed B0 questions.
    target = directory / "execution/B0"
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "reviews.jsonl").exists():
        shutil.copyfile(directory / "decision/B0/reviews.jsonl", target / "reviews.jsonl")
    await evaluate(config, directory, ["B0"], "execution", suite=suite, resume=True)
    await evaluate(config, directory, ["B1"], "execution", suite=suite, resume=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "posttraining/configs/eval_smoke_v1.json"
    )
    parser.add_argument("--execution-suite", choices=["core", "challenge"])
    parser.add_argument("--freeze-first", action="store_true")
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    state = {"pid": os.getpid(), "started_at": datetime.now(UTC).isoformat(), "status": "running"}
    write_json(directory / "background.json", state)
    paths = []
    for folder in (
        "posttraining/src",
        "posttraining/configs",
        "posttraining/scripts",
        "agent/src/shopsteward_agent/task_policy",
        "backend/app",
    ):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.suffix in {".py", ".json"})
    with zipfile.ZipFile(directory / "source-snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ROOT).as_posix())
    write_json(
        directory / "source-hashes.json",
        {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    )
    code = 0
    try:
        asyncio.run(run(directory, args.config.resolve(), args.execution_suite, args.freeze_first))
        state["status"] = "awaiting_review_and_next_stage"
    except Exception as exc:
        code = 1
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc)[:400])
        traceback.print_exc()
    state.update(finished_at=datetime.now(UTC).isoformat(), exit_code=code)
    write_json(directory / "background.json", state)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
