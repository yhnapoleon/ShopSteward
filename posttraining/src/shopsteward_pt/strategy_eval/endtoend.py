"""Run the whole sourcing loop on a world and grade every stage.

This drives the real agent runtime: the root's request, reviewers with their
own documents and tool, the citation gate with its second reading, the
product's solver and the explanation. A world passes only if every supplier
got a card, the solver then recommends what it recommends for the true cards,
and the explanation is faithful to the proposal it was given.
"""

import asyncio
import json
import time
from pathlib import Path
from statistics import mean, median

from .cards import CITED, check_card, solve
from .claims import check_claims
from .runner import PROVIDER, OracleModel


class OracleDesk:
    """Offline stand-in for every role: opens all documents, then states the truth."""

    def __init__(self, worlds):
        self.explainer = OracleModel(worlds)
        self.suppliers = {
            (json.dumps(world["request"], sort_keys=True), supplier["supplier_id"]): supplier
            for world in worlds
            for supplier in world["suppliers"]
        }

    async def complete(self, messages, tools, **kwargs):
        if not any(tool["function"]["name"] == "read_supplier_document" for tool in tools):
            return await self.explainer.complete(messages, tools, **kwargs)
        text = "\n".join(str(message.get("content")) for message in messages)
        task = json.loads(text[text.index('{"role": "supplier"') :].split("\n")[0])
        sid = task["supplier"]["supplier_id"]
        supplier = self.suppliers[(json.dumps(task["request"], sort_keys=True), sid)]
        if not any(message["role"] == "tool" for message in messages):
            calls = [
                {
                    "id": f"{sid}-{index}",
                    "function": {
                        "name": "read_supplier_document",
                        "arguments": json.dumps({"doc_id": doc["doc_id"]}),
                    },
                }
                for index, doc in enumerate(task["documents"])
            ]
            return {"content": "", "tool_calls": calls, "usage": None}
        texts = {doc["doc_id"]: doc["text"] for doc in supplier["documents"]}
        card = supplier["card"]
        citations = [
            {
                "field": name,
                "doc_id": supplier["evidence"][name][0],
                "quote": texts[supplier["evidence"][name][0]].splitlines()[0],
            }
            for name in (CITED if card["status"] == "offer" else ("status",))
        ]
        return {"content": json.dumps({**card, "citations": citations}), "usage": None}


async def run_world(
    world,
    *,
    model,
    profile,
    role_models=None,
    replicate=1,
    label=None,
    bundle=None,
    review_bundle=None,
):
    """`bundle` is the explainer's text version and `review_bundle` the reviewers'."""
    from shopsteward_agent.cases import source_case

    case_id = world["case_id"]
    run_id = f"{case_id}:{label or profile.model_id}:{replicate}"

    async def solver(recovery):
        result = solve(recovery)
        return result and {"id": f"proposal:{case_id}", **result.model_dump(mode="json")}

    started = time.monotonic()
    outcome = await source_case(
        {**world["snapshot"]["recovery"], "offers": []},
        # Reviewers get the documents only; the answer key stays here.
        [{key: s[key] for key in ("supplier_id", "name", "documents")} for s in world["suppliers"]],
        district=world["request"]["district"],
        solve=solver,
        case_id=case_id,
        revision_id="1",
        run_id=run_id,
        model=model,
        profile=profile,
        role_models=role_models,
        bundle=bundle,
        review_bundle=review_bundle,
    )
    latency = int((time.monotonic() - started) * 1000)
    reviews = {item["supplier_id"]: item for item in outcome["reviews"]}
    graded = {
        s["supplier_id"]: check_card(reviews.get(s["supplier_id"], {}).get("card"), s)
        for s in world["suppliers"]
    }
    proposal, analysis = outcome["proposal"], outcome["analysis"]
    told = check_claims(analysis["merged"]["claims"], proposal) if analysis else None
    decision = proposal and proposal["recommended_candidate_id"]
    stages = {
        "request": outcome["request"] == world["request"],
        "reviewed": not outcome["unreviewed"] and len(reviews) == len(world["suppliers"]),
        "cards": all(item["decision_safe"] for item in graded.values()),
        "decision": decision == world["proposal"]["recommended_candidate_id"],
        "explanation": bool(told) and told["coverage"] == 1 and not told["contradictions"],
    }
    usage = outcome["usage"] or {}
    record = {
        "run_id": run_id,
        "case_id": case_id,
        "partition": world["partition"],
        "family": world["family"],
        "model": label or profile.model_id,
        "replicate": replicate,
        "text": {
            "explain": analysis and analysis["routing"]["bundle_revision"],
            "review": outcome["review_bundle"]["revision"],
        },
        "status": outcome["status"],
        "success": all(stages.values()),
        "stages": stages,
        "suppliers": len(world["suppliers"]),
        "second_readings": sum(len(item["attempts"]) > 1 for item in reviews.values()),
        "unreviewed": outcome["unreviewed"],
        "cards": [
            {
                "supplier_id": s["supplier_id"],
                "variant": s["variant"],
                "exact": graded[s["supplier_id"]]["exact"],
                "decision_safe": graded[s["supplier_id"]]["decision_safe"],
                "wrong": [
                    name
                    for name, state in graded[s["supplier_id"]]["fields"].items()
                    if state != "correct"
                ],
                "attempts": [
                    {"model": attempt["model"], "problems": attempt["problems"]}
                    for attempt in reviews.get(s["supplier_id"], {}).get("attempts", [])
                ],
            }
            for s in world["suppliers"]
        ],
        "decision": decision,
        "explanation_missing": told and [c for c in told["required"] if c not in told["covered"]],
        "contradictions": told and [item["claim"] for item in told["contradictions"]],
        "model_calls": outcome["budget"]["model_calls"],
        "tool_calls": outcome["budget"]["tool_calls"],
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "latency_ms": latency,
    }
    # A provider outage says nothing about the loop; such a run is repeated, not scored.
    failures = [p for card in record["cards"] for a in card["attempts"] for p in a["problems"]]
    failures += [m for task in (analysis or {}).get("subtasks", []) for m in task["missing"]]
    record["provider_error"] = any(problem in PROVIDER for problem in failures)
    return record, outcome


async def run_batch(
    worlds,
    *,
    model,
    profile,
    role_models=None,
    label=None,
    replicates=1,
    out=None,
    parallel=2,
    bundle=None,
    review_bundle=None,
):
    """Run world x replicate, appending to `out`; finished runs are skipped."""
    out = Path(out) if out else None
    done = set()
    if out:
        out.mkdir(parents=True, exist_ok=True)
        if (out / "endtoend.jsonl").exists():
            lines = (out / "endtoend.jsonl").read_text(encoding="utf-8").splitlines()
            done = {json.loads(line)["run_id"] for line in lines}
    gate, lock = asyncio.Semaphore(parallel), asyncio.Lock()
    provider_errors = []

    async def job(world, replicate):
        if f"{world['case_id']}:{label or profile.model_id}:{replicate}" in done:
            return None
        async with gate:
            record, outcome = await run_world(
                world,
                model=model,
                profile=profile,
                role_models=role_models,
                replicate=replicate,
                label=label,
                bundle=bundle,
                review_bundle=review_bundle,
            )
        if record["provider_error"]:
            provider_errors.append(record["run_id"])
            return None
        if out:
            rows = {"endtoend": record, "endtoend-runs": {"run_id": record["run_id"], **outcome}}
            async with lock:
                for name, row in rows.items():
                    with (out / f"{name}.jsonl").open("a", encoding="utf-8", newline="\n") as file:
                        file.write(json.dumps(row, ensure_ascii=False) + "\n")
        return record

    records = await asyncio.gather(
        *(job(world, replicate) for world in worlds for replicate in range(1, replicates + 1))
    )
    return {"records": [r for r in records if r], "provider_errors": provider_errors}


def load_records(out):
    path = Path(out) / "endtoend.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def summarize(records):
    """Per model setup. Counts stay visible next to every rate."""
    groups = {}
    for record in records:
        groups.setdefault(record["model"], []).append(record)
    rows = []
    for model, items in sorted(groups.items()):
        cards = [card for record in items for card in record["cards"]]
        tokens = [r for r in items if r["input_tokens"] is not None]
        rows.append(
            {
                "model": model,
                "runs": len(items),
                "worlds": len({record["case_id"] for record in items}),
                "success": sum(record["success"] for record in items),
                **{
                    stage: sum(record["stages"][stage] for record in items)
                    for stage in ("request", "reviewed", "cards", "decision", "explanation")
                },
                "cards_total": len(cards),
                "cards_safe": sum(card["decision_safe"] for card in cards),
                "cards_exact": sum(card["exact"] for card in cards),
                "second_readings": sum(record["second_readings"] for record in items),
                "unreviewed": sum(len(record["unreviewed"]) for record in items),
                "mean_model_calls": round(mean(r["model_calls"] for r in items), 2),
                "mean_tool_calls": round(mean(r["tool_calls"] for r in items), 2),
                "mean_input_tokens": round(mean(r["input_tokens"] for r in tokens))
                if tokens
                else None,
                "mean_output_tokens": round(mean(r["output_tokens"] for r in tokens))
                if tokens
                else None,
                "median_latency_ms": int(median(r["latency_ms"] for r in items)),
            }
        )
    return rows


def markdown(rows):
    head = (
        "| Models | Worlds | End to end | Request | All reviewed | Cards safe (worlds) "
        "| Decision | Explanation | Cards safe | Cards exact | Second readings | Unreviewed "
        "| Model calls | Tool calls | Input tok | Output tok | Median ms |"
    )
    lines = [head, "|" + "---|" * 17]
    for row in rows:
        runs = row["runs"]
        lines.append(
            f"| {row['model']} | {row['worlds']} | {row['success']}/{runs} "
            f"| {row['request']}/{runs} | {row['reviewed']}/{runs} | {row['cards']}/{runs} "
            f"| {row['decision']}/{runs} | {row['explanation']}/{runs} "
            f"| {row['cards_safe']}/{row['cards_total']} "
            f"| {row['cards_exact']}/{row['cards_total']} | {row['second_readings']} "
            f"| {row['unreviewed']} | {row['mean_model_calls']} | {row['mean_tool_calls']} "
            f"| {row['mean_input_tokens']} | {row['mean_output_tokens']} "
            f"| {row['median_latency_ms']} |"
        )
    return "\n".join(lines) + "\n"
