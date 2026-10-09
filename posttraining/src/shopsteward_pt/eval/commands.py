"""File-backed eval commands; every score can be regenerated without a model."""

import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from shopsteward_pt.eval.records import EpisodeSpec, EpisodeTrace
from shopsteward_pt.eval.runner import load_runtime, run_episode
from shopsteward_pt.eval.scorers import clarification_review, score_episode
from shopsteward_pt.reporting import write_report


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_rows(path, model):
    return [
        model.model_validate(json.loads(line))
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_rows(path, rows):
    Path(path).write_text(
        "".join(
            json.dumps(
                row.model_dump(mode="json") if hasattr(row, "model_dump") else row,
                ensure_ascii=False,
            )
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def reviews_for(run_dir):
    path = Path(run_dir) / "reviews.jsonl"
    return (
        {
            r["key"]: r
            for r in (
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }
        if path.exists()
        else {}
    )


def rescore(run_dir):
    run_dir = Path(run_dir)
    specs = {s.episode_id: s for s in read_rows(run_dir / "specs.jsonl", EpisodeSpec)}
    traces = read_rows(run_dir / "raw.jsonl", EpisodeTrace)
    reviews = reviews_for(run_dir)
    scores = [score_episode(specs[t.episode_id], t, reviews) for t in traces]
    write_rows(run_dir / "scores.jsonl", scores)
    pending = []
    for score, trace in zip(scores, traces, strict=True):
        if score.review_status == "pending_review":
            spec = specs[trace.episode_id]
            for i, record in enumerate(trace.steps):
                if (
                    i < len(spec.expected_steps)
                    and record.decision
                    and record.decision.name == "clarify"
                    and spec.expected_steps[i].clarification_slot
                ):
                    question = record.decision.arguments["question"]
                    if clarification_review(spec, i, question, reviews) is None:
                        pending.append(
                            {
                                "key": f"{trace.episode_id}:{i}",
                                "request": spec.user_message,
                                "history": [h.model_dump() for h in spec.history],
                                "question": question,
                                "slot": spec.expected_steps[i].clarification_slot,
                                "followup": spec.followup_user_message,
                            }
                        )
    write_rows(run_dir / "pending-reviews.jsonl", pending)
    return write_report(run_dir, scores, traces, specs)


async def freeze(config_path, limit=None):
    from shopsteward_pt.eval.fixtures import fixture_for

    runtime = load_runtime(config_path)
    specs = read_rows(runtime["dataset"], EpisodeSpec)
    if limit:
        specs = specs[:limit]
    target = Path(runtime["frozen_contexts"])
    contexts = {}
    for spec in specs:
        async with fixture_for(spec, runtime) as fixture:
            contexts[spec.episode_id] = (await fixture.context(spec.user_message)).model_dump(
                mode="json"
            )
        print(f"freeze {len(contexts)}/{len(specs)} {spec.episode_id}", flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, contexts)
    write_json(
        target.with_suffix(".manifest.json"),
        {
            "episodes": len(contexts),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "dataset_sha256": hashlib.sha256(Path(runtime["dataset"]).read_bytes()).hexdigest(),
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    return {"episodes": len(contexts), "path": str(target)}


def manifest(runtime, policy_id, mode):
    from shopsteward_agent.task_policy.contracts import decision_tool_schemas
    from shopsteward_agent.task_policy.policy import prompt_for_version

    version = runtime.get("policies", {}).get(policy_id, {}).get("prompt_version", "v1")
    prompt = prompt_for_version(version) if policy_id != "B0" else None
    metadata = {
        "policy_id": policy_id,
        "mode": mode,
        "python": platform.python_version(),
        "concurrency": 1,
        "dataset_sha256": hashlib.sha256(Path(runtime["dataset"]).read_bytes()).hexdigest(),
        "prompt_version": version if prompt is not None else None,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()
        if prompt is not None
        else None,
        "tools_sha256": hashlib.sha256(
            json.dumps(decision_tool_schemas(), sort_keys=True).encode()
        ).hexdigest(),
        "temperature": 0,
        "max_output_tokens": runtime.get("policies", {})
        .get(policy_id, {})
        .get("max_output_tokens"),
        "context_version": "replenishment-real-v1",
        "price": runtime.get("policies", {}).get(policy_id, {}).get("price"),
        "created_at": datetime.now(UTC).isoformat(),
        "git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(runtime["dataset"]).parents[2], text=True
        ).strip(),
        "working_tree": "uncommitted implementation; source snapshot accompanies run",
    }
    if mode == "decision":
        metadata["frozen_sha256"] = hashlib.sha256(
            Path(runtime["frozen_contexts"]).read_bytes()
        ).hexdigest()
    if policy_id != "B0":
        from app.core.config import Settings

        settings = Settings(_env_file=runtime["app_env_file"])
        config = runtime["policies"][policy_id]
        metadata.update(
            model=config.get("model") or settings.agent_model,
            endpoint=config.get("base_url") or settings.agent_base_url,
            api_mode=config.get("api_mode") or settings.agent_api_mode,
        )
    return metadata


async def evaluate(config_path, run_root, policies, mode, suite=None, limit=None, resume=False):
    runtime = load_runtime(config_path)
    specs = read_rows(runtime["dataset"], EpisodeSpec)
    if suite:
        specs = [s for s in specs if s.suite == suite]
    if limit:
        specs = specs[:limit]
    frozen = (
        json.loads(Path(runtime["frozen_contexts"]).read_text(encoding="utf-8"))
        if mode == "decision"
        else {}
    )
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for policy_id in policies:
        directory = root / mode / policy_id
        directory.mkdir(parents=True, exist_ok=True)
        raw = directory / "raw.jsonl"
        if raw.exists() and not resume:
            raise ValueError("run already exists; use --resume or a new run directory")
        existing = {t.episode_id: t for t in read_rows(raw, EpisodeTrace)} if raw.exists() else {}
        if existing:
            saved_specs = read_rows(directory / "specs.jsonl", EpisodeSpec)
            if saved_specs != specs:
                raise ValueError("resume requires identical episode specifications")
            old = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            current = manifest(runtime, policy_id, mode)
            for key in (
                "dataset_sha256",
                "prompt_sha256",
                "tools_sha256",
                "frozen_sha256",
                "model",
                "endpoint",
                "api_mode",
            ):
                if old.get(key) != current.get(key):
                    raise ValueError(f"resume configuration changed: {key}")
        else:
            write_rows(directory / "specs.jsonl", specs)
            write_json(directory / "manifest.json", manifest(runtime, policy_id, mode))
            (directory / "reviews.jsonl").touch()
        reviews = reviews_for(directory)
        warmup = directory / "warmup.jsonl"
        if policy_id != "B0" and mode == "decision" and not warmup.exists():
            rows = []
            for spec in specs[: runtime.get("warmup_episodes", 0)]:
                trace = await run_episode(
                    spec,
                    policy_id,
                    mode="decision",
                    config=runtime,
                    frozen_context=frozen[spec.episode_id],
                )
                rows.append(trace)
                write_rows(warmup, rows)
                if trace.environment_error:
                    raise ValueError("model warmup failed; inspect warmup.jsonl")
        for index, spec in enumerate(specs):
            previous = existing.get(spec.episode_id)
            if previous:
                needs_reply = (
                    len(previous.steps) < len(spec.expected_steps)
                    and previous.steps
                    and previous.steps[0].decision
                    and previous.steps[0].decision.name == "clarify"
                    and clarification_review(
                        spec, 0, previous.steps[0].decision.arguments["question"], reviews
                    )
                    is True
                )
                if not needs_reply:
                    continue
                archive = directory / "pre-resume-raw.jsonl"
                if not archive.exists():
                    archive.write_bytes(raw.read_bytes())
            write_json(
                root / "status.json",
                {
                    "status": "running",
                    "mode": mode,
                    "policy": policy_id,
                    "current": index + 1,
                    "total": len(specs),
                    "episode_id": spec.episode_id,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
            trace = await run_episode(
                spec,
                policy_id,
                mode=mode,
                config=runtime,
                frozen_context=frozen.get(spec.episode_id),
                reviews=reviews,
                previous=previous,
            )
            existing[spec.episode_id] = trace
            write_rows(raw, [existing[s.episode_id] for s in specs if s.episode_id in existing])
            print(
                f"{mode}/{policy_id} {index + 1}/{len(specs)} {spec.episode_id}: {trace.environment_error or 'recorded'}",
                flush=True,
            )
            # Stop an unavailable endpoint after three consecutive failures; preserve all attempts.
            recent = list(existing.values())[-3:]
            if len(recent) == 3 and all(t.environment_error for t in recent):
                rescore(directory)
                raise ValueError(
                    "three consecutive environment failures; inspect raw.jsonl before continuing"
                )
        summaries[policy_id] = rescore(directory)
    write_json(
        root / "status.json",
        {
            "status": "batch_complete",
            "mode": mode,
            "policies": policies,
            "pending_reviews": sum(s["pending_reviews"] for s in summaries.values()),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    return {
        k: {
            key: v[key]
            for key in (
                "scheduled_episodes",
                "pending_reviews",
                "environment_errors",
                "action_accuracy",
                "arguments_accuracy",
                "core_success",
            )
        }
        for k, v in summaries.items()
    }
