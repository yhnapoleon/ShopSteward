"""Grade one stage of the sourcing loop on its own, against the answer key.

The whole loop costs about eight model calls a world, and one stage's noise
hides another's. `explain_world` gives the explainer what the loop gives it
when every reviewer was right; `read_supplier` lets one reviewer read one
supplier, gate and second reading included. Text is optimized against these;
the whole loop is run only to release a version.
"""

import asyncio
import json
import time
from pathlib import Path
from statistics import mean, median

from .cards import check_card, cited, to_offer, value
from .claims import check_claims
from .runner import PROVIDER

STAGES = ("explain", "read")


def run_key(stage, world, supplier, label, revision, replicate):
    who = f":{supplier['supplier_id']}" if supplier else ""
    return f"{world['case_id']}:{stage}{who}:{label}:{revision}:{replicate}"


def items(worlds, stage):
    """What one run of a stage is about: a world, or one supplier of a world."""
    if stage == "explain":
        return [(world, None) for world in worlds]
    return [(world, supplier) for world in worlds for supplier in world["suppliers"]]


async def explain_world(world, *, bundle, model, profile, replicate=1, label=None):
    """One explanation of the true proposal. Returns (record, analysis)."""
    from shopsteward_agent.cases import analyze_frozen_case

    label = label or profile.model_id
    run_id = run_key("explain", world, None, label, bundle.revision, replicate)
    recovery, proposal = world["snapshot"]["recovery"], world["proposal"]
    cards = [cited(supplier, recovery["sku_id"]) for supplier in world["suppliers"]]
    offers = [to_offer(card, recovery["sku_id"]) for card in cards if card["status"] == "offer"]
    started = time.monotonic()
    analysis = await analyze_frozen_case(
        # What the loop passes on when no reviewer erred: true cards with real excerpts.
        {
            "recovery": {**recovery, "offers": offers},
            "sourcing": {"cards": cards, "unreviewed": []},
        },
        proposal,
        case_id=world["case_id"],
        revision_id="1",
        run_id=run_id,
        strategy="fixed",
        model=model,
        profile=profile,
        bundle=bundle,
        forced=True,
    )
    told = check_claims(analysis["merged"]["claims"], proposal)
    failed = {
        task["subtask_id"]: task["missing"]
        for task in analysis["subtasks"]
        if task["status"] == "failed"
    }
    contradictions = [item["claim"] for item in told["contradictions"]]
    usage = analysis["usage"] or {}
    record = {
        "run_id": run_id,
        "stage": "explain",
        "case_id": world["case_id"],
        "partition": world["partition"],
        "family": world["family"],
        "model": label,
        "text": bundle.revision,
        "replicate": replicate,
        # Ranks candidates for the optimizer. Reports use `passed`.
        "score": 0.0 if failed or contradictions else told["coverage"],
        "passed": told["coverage"] == 1 and not contradictions,
        "required": told["required"],
        "missing": [item for item in told["required"] if item not in told["covered"]],
        "contradictions": contradictions,
        "unverifiable": told["unverifiable"],
        "status": analysis["status"],
        "failed_subtasks": failed,
        "provider_error": any(code in PROVIDER for codes in failed.values() for code in codes),
        "model_calls": analysis["budget"]["model_calls"],
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    return record, analysis


async def read_supplier(
    world,
    supplier,
    *,
    bundle,
    model,
    profile,
    role_models=None,
    replicate=1,
    label=None,
):
    """One reviewer on one supplier, gate and second reading included. Returns (record, review)."""
    from shopsteward_agent.cases import CallBudget, review_supplier

    label = label or profile.model_id
    run_id = run_key("read", world, supplier, label, bundle.revision, replicate)
    budget = CallBudget(
        max_model_calls=8, max_tool_calls=2 * (len(supplier["documents"]) + 2), timeout_s=300
    )
    started = time.monotonic()
    review = await review_supplier(
        # The reviewer gets the documents only; the answer key stays here.
        {key: supplier[key] for key in ("supplier_id", "name", "documents")},
        world["request"],
        case_id=world["case_id"],
        revision_id="1",
        run_id=run_id,
        model=model,
        profile=profile,
        budget=budget,
        role_models=role_models,
        review_bundle=bundle,
    )
    card, attempts = review["card"], review["attempts"]
    graded, spent = check_card(card, supplier), budget.snapshot()
    record = {
        "run_id": run_id,
        "stage": "read",
        "case_id": world["case_id"],
        "partition": world["partition"],
        "family": world["family"],
        "supplier_id": supplier["supplier_id"],
        "variant": supplier["variant"],
        "model": label,
        "text": bundle.revision,
        "replicate": replicate,
        # Ranks candidates for the optimizer. Reports use `passed`: every field the
        # solver reads is right.
        "score": graded["correct"] / graded["total"] if graded["decision_safe"] else 0.0,
        "passed": graded["decision_safe"],
        "exact": graded["exact"],
        "first_reading": card is not None and len(attempts) == 1,
        "wrong": [
            {
                "field": name,
                "got": card and value(card, name),
                "expected": value(supplier["card"], name),
            }
            for name, state in graded["fields"].items()
            if state != "correct"
        ],
        "attempts": [
            {key: attempt[key] for key in ("model", "problems", "reasons")} for attempt in attempts
        ],
        "provider_error": any(p in PROVIDER for attempt in attempts for p in attempt["problems"]),
        "model_calls": spent["model_calls"],
        "tool_calls": spent["tool_calls"],
        # Unknown usage stays unknown; it is not counted as zero.
        "input_tokens": (spent["usage"] or {}).get("input_tokens"),
        "output_tokens": (spent["usage"] or {}).get("output_tokens"),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    return record, review


async def run_item(stage, world, supplier, *, role_models=None, **options):
    """One run of either stage. Returns (record, what the stage produced)."""
    if stage == "explain":
        return await explain_world(world, **options)
    return await read_supplier(world, supplier, role_models=role_models, **options)


def failure_kinds(record):
    """Short labels for why a run did not pass, so a repeated failure shows as repeated."""
    if record["stage"] == "explain":
        if record["failed_subtasks"]:
            # No usable answer came back, so "unstated" would misname it.
            return sorted({code for codes in record["failed_subtasks"].values() for code in codes})
        kinds = {item.split(":")[0] + "-unstated" for item in record["missing"]}
        return sorted(kinds | ({"contradiction"} if record["contradictions"] else set()))
    rejected = record["attempts"][-1]["problems"]
    if rejected:
        return ["rejected:" + ",".join(rejected)]
    return sorted(item["field"] for item in record["wrong"])


def _kept(stage, outcome):
    """What is worth reading back later: the claims made, or the readings with rejected answers."""
    if stage == "read":
        return outcome
    keep = ("subtask_id", "status", "claims", "missing", "rejected")
    return {
        "merged": outcome["merged"],
        "subtasks": [{key: task.get(key) for key in keep} for task in outcome["subtasks"]],
    }


async def run_batch(
    worlds,
    *,
    stage,
    bundle,
    model,
    profile,
    role_models=None,
    label=None,
    replicates=1,
    out=None,
    parallel=3,
):
    """Run item x replicate, appending to `out`; finished runs are skipped."""
    out, name = (Path(out) if out else None), label or profile.model_id
    done = {record["run_id"] for record in load_records(out, stage)} if out else set()
    if out:
        out.mkdir(parents=True, exist_ok=True)
    gate, lock = asyncio.Semaphore(parallel), asyncio.Lock()
    provider_errors = []

    async def job(world, supplier, replicate):
        if run_key(stage, world, supplier, name, bundle.revision, replicate) in done:
            return None
        async with gate:
            record, outcome = await run_item(
                stage,
                world,
                supplier,
                bundle=bundle,
                model=model,
                profile=profile,
                role_models=role_models,
                replicate=replicate,
                label=label,
            )
        if record["provider_error"]:
            provider_errors.append(record["run_id"])
            return None
        if out:
            rows = {
                f"stage-{stage}": record,
                f"stage-{stage}-runs": {"run_id": record["run_id"], **_kept(stage, outcome)},
            }
            async with lock:
                for file, row in rows.items():
                    with (out / f"{file}.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return record

    records = await asyncio.gather(
        *(
            job(world, supplier, replicate)
            for world, supplier in items(worlds, stage)
            for replicate in range(1, replicates + 1)
        )
    )
    return {"records": [r for r in records if r], "provider_errors": provider_errors}


def load_records(out, stage):
    path = Path(out) / f"stage-{stage}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def summarize(records):
    """Per stage, model setup, text version and partition. Counts stay next to every rate."""
    groups = {}
    for record in records:
        key = (record["stage"], record["model"], record["text"], record["partition"])
        groups.setdefault(key, []).append(record)
    rows = []
    for (stage, model, text, partition), runs in sorted(groups.items()):
        failures = {}
        for run in runs:
            for kind in [] if run["passed"] else failure_kinds(run) or ["other"]:
                failures[kind] = failures.get(kind, 0) + 1
        rows.append(
            {
                "stage": stage,
                "model": model,
                "text": text,
                "partition": partition,
                "runs": len(runs),
                "items": len({run["run_id"].rsplit(":", 1)[0] for run in runs}),
                "passed": sum(run["passed"] for run in runs),
                "mean_score": round(mean(run["score"] for run in runs), 3),
                "first_reading": sum(run["first_reading"] for run in runs)
                if stage == "read"
                else None,
                "failures": failures,
                "mean_model_calls": round(mean(run["model_calls"] for run in runs), 2),
                "median_latency_ms": int(median(run["latency_ms"] for run in runs)),
            }
        )
    return rows


def markdown(rows):
    lines = [
        "| Stage | Models | Text | Partition | Passed | Mean score | First reading "
        "| Failures | Model calls | Median ms |",
        "|" + "---|" * 10,
    ]
    for row in rows:
        failures = ", ".join(f"{kind} x{count}" for kind, count in sorted(row["failures"].items()))
        first = "—" if row["first_reading"] is None else f"{row['first_reading']}/{row['runs']}"
        lines.append(
            f"| {row['stage']} | {row['model']} | {row['text']} | {row['partition']} "
            f"| {row['passed']}/{row['runs']} | {row['mean_score']} | {first} "
            f"| {failures or '—'} | {row['mean_model_calls']} | {row['median_latency_ms']} |"
        )
    return "\n".join(lines) + "\n"
