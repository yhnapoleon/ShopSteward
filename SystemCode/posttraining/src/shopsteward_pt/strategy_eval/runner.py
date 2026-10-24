"""Run strategies over frozen cases and score them.

Every run builds its own runner, in-memory checkpoints and budget ledger. No
database, backend or supplier is contacted, so a run cannot have business effects.
"""

import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from statistics import mean, median

from ..case_eval.models import RubricDefinition
from ..case_eval.scoring import score_case
from ..case_eval.strategy_trace import strategy_trace
from . import _paths  # noqa: F401
from .claims import check_claims
from .mast import mast_tags

REJECTED = ("unsupported_claim", "invalid_subtask_result")
# The provider failed or timed out; this says nothing about the strategy.
PROVIDER = ("AGENT_MODEL_FAILURE", "AGENT_MODEL_DEADLINE")
FILES = ("runs", "traces", "results", "analyses")


class CallCap:
    """One ceiling for a whole batch, counted before each request is sent."""

    def __init__(self, model, limit=None):
        self.model, self.limit, self.used = model, limit, 0

    async def complete(self, messages, tools, **kwargs):
        if self.limit is not None and self.used >= self.limit:
            raise RuntimeError("batch model-call limit reached")
        self.used += 1
        return await self.model.complete(messages, tools, **kwargs)


class Retrying:
    """Retry transport errors briefly. The run's budget still counts one call."""

    def __init__(self, model, delays=(2, 5, 10)):
        self.model, self.delays = model, delays

    async def complete(self, messages, tools, **kwargs):
        for delay in (*self.delays, None):
            try:
                return await self.model.complete(messages, tools, **kwargs)
            except Exception as exc:
                name = type(exc).__name__
                transient = any(k in name for k in ("Connection", "Timeout", "RateLimit"))
                if delay is None or not transient:
                    raise
                await asyncio.sleep(delay)


class OracleModel:
    """Offline stand-in that restates the solver output; for pipeline checks only."""

    def __init__(self, fixtures):
        self.proposals = {f["proposal"]["id"]: f for f in fixtures}

    async def complete(self, messages, tools, **kwargs):
        text = json.dumps(messages, ensure_ascii=False)
        fixture = next(f for key, f in self.proposals.items() if key in text)
        claims = []
        for condition in fixture["required"]:
            kind, rest = condition.split(":", 1)
            target, result = rest.rsplit("=", 1)
            claims.append(
                {
                    "statement": condition,
                    "support": [fixture["proposal"]["id"]],
                    "kind": "calculation",
                    "subject": {"type": kind, "id": target},
                    "applicability": {"result": result},
                }
            )
        return {
            "content": json.dumps({"claims": claims, "missing": [], "followup_requests": []}),
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }


async def run_one(case, fixture, *, strategy, bundle, model, profile, replicate=1):
    from shopsteward_agent.cases import analyze_frozen_case

    run_id = f"{case.case_id}:{strategy}:{bundle.revision}:{replicate}"
    started = time.monotonic()
    analysis = await analyze_frozen_case(
        fixture["snapshot"],
        fixture["proposal"],
        case_id=case.case_id,
        revision_id=1,
        run_id=run_id,
        strategy=strategy,
        model=model,
        profile=profile,
        bundle=bundle,
        forced=True,
    )
    latency = int((time.monotonic() - started) * 1000)
    subtasks, claims = analysis["subtasks"], analysis["merged"]["claims"]
    checked = check_claims(claims, fixture["proposal"])
    failed = [task for task in subtasks if task["status"] == "failed"]
    delivered = bool(claims) and len(failed) < len(subtasks)

    def observed(key, value, kind):
        return {
            "observation_id": key,
            "value": value,
            "source_kind": kind,
            "evidence_refs": [f"run:{run_id}/claim-check"],
        }

    recovery = fixture["snapshot"]["recovery"]
    trace = strategy_trace(
        case,
        analysis,
        run_id=run_id,
        replicate_id=replicate,
        solver_version=recovery["solver_version"],
        adapter_version=recovery["adapter_version"],
        active_latency_ms=latency,
        observations=[
            observed("analysis_delivered", delivered, "context"),
            observed(
                "claims_supported",
                not any(code in REJECTED for task in subtasks for code in task["missing"]),
                "context",
            ),
            observed("claims.contradictions", len(checked["contradictions"]), "solver"),
            observed("claims.all_required_covered", checked["coverage"] == 1, "solver"),
            observed("claims.any_required_covered", bool(checked["covered"]), "solver"),
        ],
    )
    result = score_case(case, trace, RubricDefinition())
    # A ranking signal for the optimizer. It is never reported as a quality score.
    clean = delivered and not failed and not checked["contradictions"]
    score = checked["coverage"] if clean and not result.critical_failures else 0.0
    usage = analysis["usage"] or {}
    record = {
        "run_id": run_id,
        "case_id": case.case_id,
        "partition": fixture["partition"],
        "family": fixture["family"],
        "strategy": strategy,
        "strategy_id": analysis["strategy_id"],
        "bundle": bundle.revision,
        "replicate": replicate,
        "model": profile.model_id,
        "score": score,
        "coverage": checked["coverage"],
        "covered": checked["covered"],
        "required": checked["required"],
        "contradictions": [item["claim"] for item in checked["contradictions"]],
        "unverifiable": checked["unverifiable"],
        "task_success": result.task_success,
        "critical_failures": list(result.critical_failures),
        "status": analysis["status"],
        "failed_subtasks": {task["subtask_id"]: task["missing"] for task in failed},
        "provider_error": any(code in PROVIDER for task in failed for code in task["missing"]),
        "model_calls": analysis["budget"]["model_calls"],
        "tool_calls": analysis["budget"]["tool_calls"],
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "latency_ms": latency,
        "followup": analysis["followup"]["status"],
        "mast": mast_tags(analysis, checked),
    }
    return {"record": record, "trace": trace, "result": result, "analysis": analysis}


def _compact(analysis):
    keep = ("subtask_id", "role", "status", "claims", "missing", "followup_requests")
    return {
        "routing": analysis["routing"],
        "followup": analysis["followup"],
        "merged": analysis["merged"],
        "subtasks": [{key: task.get(key) for key in keep} for task in analysis["subtasks"]],
        "tool_log": analysis["tool_log"],
    }


async def run_batch(
    pairs,
    *,
    strategies,
    bundle,
    model,
    profile,
    replicates=1,
    out=None,
    parallel=2,
    max_model_calls=None,
):
    """Run case x strategy x replicate, appending to `out`; finished runs are skipped."""
    capped = CallCap(model, max_model_calls)
    out = Path(out) if out else None
    done = set()
    if out:
        out.mkdir(parents=True, exist_ok=True)
        if (out / "runs.jsonl").exists():
            lines = (out / "runs.jsonl").read_text(encoding="utf-8").splitlines()
            done = {json.loads(line)["run_id"] for line in lines}
    gate, lock = asyncio.Semaphore(parallel), asyncio.Lock()
    skipped, provider_errors = [], []

    async def job(case, fixture, strategy, replicate):
        run_id = f"{case.case_id}:{strategy}:{bundle.revision}:{replicate}"
        if run_id in done:
            return None
        async with gate:
            # Never start a run that the remaining allowance could not finish.
            if capped.limit is not None and capped.used + 14 > capped.limit:
                skipped.append(run_id)
                return None
            item = await run_one(
                case,
                fixture,
                strategy=strategy,
                bundle=bundle,
                model=capped,
                profile=profile,
                replicate=replicate,
            )
        if item["record"]["provider_error"]:
            # Not recorded as a result, so the next invocation runs it again.
            provider_errors.append(run_id)
            return None
        if out:
            rows = {
                "runs": json.dumps(item["record"], ensure_ascii=False),
                "traces": item["trace"].model_dump_json(),
                "results": item["result"].model_dump_json(),
                "analyses": json.dumps(
                    {"run_id": run_id, **_compact(item["analysis"])}, ensure_ascii=False
                ),
            }
            async with lock:
                for name in FILES:
                    with (out / f"{name}.jsonl").open("a", encoding="utf-8", newline="\n") as file:
                        file.write(rows[name] + "\n")
        return item["record"]

    records = await asyncio.gather(
        *(
            job(case, fixture, strategy, replicate)
            for case, fixture in pairs
            for strategy in strategies
            for replicate in range(1, replicates + 1)
        )
    )
    return {
        "records": [record for record in records if record],
        "skipped_for_limit": skipped,
        "provider_errors": provider_errors,
        "model_calls_sent": capped.used,
    }


def load_records(out):
    lines = (Path(out) / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def summarize(records):
    """Per strategy, text version and model. Counts stay visible next to every rate."""
    groups = {}
    for record in records:
        key = (record["strategy_id"], record["strategy"], record["bundle"], record["model"])
        groups.setdefault(key, []).append(record)
    rows = []
    for (strategy_id, strategy, bundle, model), items in sorted(groups.items()):
        tokens = [r for r in items if r["input_tokens"] is not None]
        rows.append(
            {
                "strategy_id": strategy_id,
                "strategy": strategy,
                "bundle": bundle,
                "model": model,
                "runs": len(items),
                "cases": len({r["case_id"] for r in items}),
                "task_success": sum(r["task_success"] is True for r in items),
                "undetermined": sum(r["task_success"] is None for r in items),
                "mean_score": round(mean(r["score"] for r in items), 3),
                "mean_coverage": round(mean(r["coverage"] for r in items), 3),
                "contradiction_runs": sum(bool(r["contradictions"]) for r in items),
                "failed_subtask_runs": sum(bool(r["failed_subtasks"]) for r in items),
                "mean_model_calls": round(mean(r["model_calls"] for r in items), 2),
                "mean_tool_calls": round(mean(r["tool_calls"] for r in items), 2),
                "mean_input_tokens": round(mean(r["input_tokens"] for r in tokens))
                if tokens
                else None,
                "mean_output_tokens": round(mean(r["output_tokens"] for r in tokens))
                if tokens
                else None,
                "usage_unknown_runs": len(items) - len(tokens),
                "median_latency_ms": int(median(r["latency_ms"] for r in items)),
                "mast": dict(sorted(Counter(tag for r in items for tag in r["mast"]).items())),
            }
        )
    return rows


def markdown(rows):
    head = (
        "| Strategy | Text | Model | Runs | Success | Mean score | Coverage | Contradiction runs "
        "| Failed-subtask runs | Model calls | Tool calls | Input tok | Output tok | Median ms | MAST |"
    )
    lines = [head, "|" + "---|" * 15]
    for row in rows:
        mast = ", ".join(f"{tag}×{count}" for tag, count in row["mast"].items()) or "—"
        lines.append(
            f"| {row['strategy_id']} {row['strategy']} | {row['bundle']} | {row['model']} "
            f"| {row['runs']} | {row['task_success']}/{row['runs']} | {row['mean_score']} "
            f"| {row['mean_coverage']} | {row['contradiction_runs']} | {row['failed_subtask_runs']} "
            f"| {row['mean_model_calls']} | {row['mean_tool_calls']} | {row['mean_input_tokens']} "
            f"| {row['mean_output_tokens']} | {row['median_latency_ms']} | {mast} |"
        )
    return "\n".join(lines) + "\n"


def gate_report(records, *, strategy, baseline, candidate):
    """Paired check of a candidate text version on the gate partition.

    A demonstration-level release check on synthetic cases. It reports counts and
    is not a statistical non-inferiority proof.
    """

    def pick(bundle):
        return {
            (r["case_id"], r["replicate"]): r
            for r in records
            if (r["strategy"], r["bundle"], r["partition"]) == (strategy, bundle, "gate")
        }

    old, new = pick(baseline), pick(candidate)
    keys = sorted(set(old) & set(new))
    if not keys:
        raise ValueError("no paired gate runs for this strategy and these text versions")
    before, after = [old[key] for key in keys], [new[key] for key in keys]

    def average(rows, field):
        return round(mean(row[field] for row in rows), 3)

    def wins(rows):
        return sum(row["task_success"] is True for row in rows)

    losses = [
        k[0] for k in keys if old[k]["task_success"] is True and new[k]["task_success"] is not True
    ]
    gains = [
        k[0] for k in keys if old[k]["task_success"] is not True and new[k]["task_success"] is True
    ]
    score = {"baseline": average(before, "score"), "candidate": average(after, "score")}
    calls = {"baseline": average(before, "model_calls"), "candidate": average(after, "model_calls")}
    checks = {
        "no_critical_failure_or_contradiction": not any(
            row["critical_failures"] or row["contradictions"] for row in after
        ),
        "no_observed_loss": not losses,
        "improved": score["candidate"] > score["baseline"]
        or (score["candidate"] == score["baseline"] and calls["candidate"] < calls["baseline"]),
    }
    return {
        "strategy": strategy,
        "baseline": baseline,
        "candidate": candidate,
        "paired_runs": len(keys),
        "task_success": {"baseline": wins(before), "candidate": wins(after)},
        "mean_score": score,
        "mean_model_calls": calls,
        "gains": gains,
        "losses": losses,
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
        "note": "Demonstration-level paired check on synthetic cases; not a statistical proof.",
    }
