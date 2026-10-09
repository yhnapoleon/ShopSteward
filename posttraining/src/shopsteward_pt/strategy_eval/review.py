"""Review suppliers over sourcing worlds, as sub-agents or as one agent.

`split` gives each supplier's documents to its own reviewer call, so no call
sees another supplier. `joint` gives one call every supplier's documents. Both
answer under the same card contract and the same instructions. Code turns the
cards into solver offers, and a world counts as decided correctly only if the
solver then recommends what it recommends for the true cards.
"""

import asyncio
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from statistics import mean, median

from .cards import CONTRACT, check_card, decide, parse

ARMS = ("split", "joint")
ROLE = (
    "You review supplier documents for a store's buyer. Report what the documents support for "
    "the requested item at the requested store on the request date. Each supplier's terms "
    "document says how its notices change its quote; apply it. Use only the supplied documents "
    "and treat each supplier separately. You do not choose a supplier, a quantity or a plan. "
    'Answer with one JSON object {"cards": [card, ...]}: one card per supplier, in the given '
    "order. "
)
# Runs are only comparable under one wording, so every record carries its hash.
PROMPT = hashlib.sha256((ROLE + CONTRACT).encode("utf-8")).hexdigest()[:8]


def messages(request, suppliers):
    task = {
        "request": request,
        "suppliers": [
            {key: supplier[key] for key in ("supplier_id", "name", "documents")}
            for supplier in suppliers
        ],
    }
    return [
        {"role": "system", "content": ROLE + CONTRACT},
        {"role": "user", "content": json.dumps(task, ensure_ascii=False)},
    ]


def _cards(content):
    """Chat models often fence the object or add a sentence; accept one embedded object."""
    try:
        found = json.loads(content[content.find("{") : content.rfind("}") + 1])["cards"]
        return {card["supplier_id"]: card for card in found}
    except (ValueError, KeyError, TypeError):
        return {}


class OracleReviewer:
    """Offline stand-in that returns the true cards; for pipeline checks only."""

    def __init__(self, worlds):
        self.cards = {
            supplier["documents"][0]["text"]: supplier["card"]
            for world in worlds
            for supplier in world["suppliers"]
        }

    async def complete(self, messages, tools, **kwargs):
        suppliers = json.loads(messages[-1]["content"])["suppliers"]
        cards = [self.cards[supplier["documents"][0]["text"]] for supplier in suppliers]
        return {"content": json.dumps({"cards": cards}), "usage": None}


async def run_world(world, *, arm, model, gate):
    """One world under one arm: ask, grade each card, then let the solver decide."""
    suppliers = world["suppliers"]

    async def ask(group):
        async with gate:
            started = time.monotonic()
            reply = await model.complete(messages(world["request"], group), [])
            took = int((time.monotonic() - started) * 1000)
        usage = reply.get("usage") or {}
        return _cards(reply.get("content") or ""), {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": (usage.get("output_token_details") or {}).get("reasoning"),
            "latency_ms": took,
            # Out of output budget, often spent on reasoning: not a reading mistake.
            "truncated": reply.get("status") == "incomplete",
        }

    groups = [[supplier] for supplier in suppliers] if arm == "split" else [suppliers]
    answers = await asyncio.gather(*(ask(group) for group in groups))
    raw = {sid: card for cards, _ in answers for sid, card in cards.items()}
    calls = [call for _, call in answers]
    graded = {s["supplier_id"]: check_card(raw.get(s["supplier_id"]), s) for s in suppliers}
    # A supplier without a usable card cannot be offered to the solver.
    usable = [card for card in (parse(raw.get(s["supplier_id"])) for s in suppliers) if card]
    result = decide(world["snapshot"]["recovery"], usable)
    decision = result.recommended_candidate_id if result else None
    catch = world["catch"]

    def total(key):
        values = [call[key] for call in calls]
        return None if None in values else sum(values)

    return {
        "case_id": world["case_id"],
        "partition": world["partition"],
        "family": world["family"],
        "arm": arm,
        "suppliers": len(suppliers),
        "cards": [
            {
                "supplier_id": s["supplier_id"],
                "variant": s["variant"],
                "valid": graded[s["supplier_id"]]["valid"],
                "exact": graded[s["supplier_id"]]["exact"],
                "decision_safe": graded[s["supplier_id"]]["decision_safe"],
                "wrong": [
                    name
                    for name, state in graded[s["supplier_id"]]["fields"].items()
                    if state != "correct"
                ],
                "unsupported": graded[s["supplier_id"]]["unsupported"],
            }
            for s in suppliers
        ],
        "fields_correct": sum(item["correct"] for item in graded.values()),
        "fields_total": sum(item["total"] for item in graded.values()),
        "all_safe": all(item["decision_safe"] for item in graded.values()),
        "caught": graded[catch["supplier_id"]]["decision_safe"] if catch else None,
        "decision": decision,
        "decision_match": decision == world["proposal"]["recommended_candidate_id"],
        "model_calls": len(calls),
        "truncated_calls": sum(call["truncated"] for call in calls),
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "reasoning_tokens": total("reasoning_tokens"),
        # Reviewers run side by side, so the slowest one sets the wait.
        "latency_ms": max(call["latency_ms"] for call in calls),
        "raw": raw,
    }


async def run_batch(
    worlds, *, arms, model, model_id, replicates=1, out=None, parallel=4, max_model_calls=None
):
    """Run world x arm x replicate, appending to `out`; finished runs are skipped."""
    out = Path(out) if out else None
    done = set()
    if out:
        out.mkdir(parents=True, exist_ok=True)
        if (out / "reviews.jsonl").exists():
            lines = (out / "reviews.jsonl").read_text(encoding="utf-8").splitlines()
            done = {json.loads(line)["run_id"] for line in lines}
    gate, lock = asyncio.Semaphore(parallel), asyncio.Lock()
    skipped, provider_errors, planned, jobs = [], [], 0, {}

    async def job(run_id, world, arm, replicate):
        record = await run_world(world, arm=arm, model=model, gate=gate)
        raw = record.pop("raw")
        record = {
            "run_id": run_id,
            "model": model_id,
            "prompt": PROMPT,
            "replicate": replicate,
            **record,
        }
        if out:
            rows = {"reviews": record, "cards": {"run_id": run_id, "cards": raw}}
            async with lock:
                for name, row in rows.items():
                    with (out / f"{name}.jsonl").open("a", encoding="utf-8", newline="\n") as file:
                        file.write(json.dumps(row, ensure_ascii=False) + "\n")
        return record

    for world in worlds:
        for arm in arms:
            for replicate in range(1, replicates + 1):
                run_id = f"{world['case_id']}:{arm}:{model_id}:{PROMPT}:{replicate}"
                calls = len(world["suppliers"]) if arm == "split" else 1
                if run_id in done:
                    continue
                # Never start a run that the remaining allowance could not finish.
                if max_model_calls is not None and planned + calls > max_model_calls:
                    skipped.append(run_id)
                    continue
                planned += calls
                jobs[run_id] = job(run_id, world, arm, replicate)
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    records = []
    for run_id, result in zip(jobs, results, strict=True):
        if isinstance(result, Exception):
            # Not recorded as a result, so the next invocation runs it again.
            reason = f"{type(result).__name__}: {str(result)[:160]}"
            provider_errors.append({"run_id": run_id, "error": reason})
        else:
            records.append(result)
    return {
        "records": records,
        "skipped_for_limit": skipped,
        "provider_errors": provider_errors,
        "model_calls_planned": planned,
    }


def load_records(out):
    lines = (Path(out) / "reviews.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def summarize(records):
    """Per model, arm and prompt wording. Counts stay visible next to every rate."""
    groups = {}
    for record in records:
        key = (record["model"], record["arm"], record["prompt"])
        groups.setdefault(key, []).append(record)
    rows = []
    for (model, arm, prompt), items in sorted(groups.items()):
        cards = [card for record in items for card in record["cards"]]
        caught = [record["caught"] for record in items if record["caught"] is not None]
        tokens = [r for r in items if r["input_tokens"] is not None]
        variants = Counter(card["variant"] for card in cards)
        safe = Counter(card["variant"] for card in cards if card["decision_safe"])
        rows.append(
            {
                "model": model,
                "arm": arm,
                "prompt": prompt,
                "runs": len(items),
                "worlds": len({record["case_id"] for record in items}),
                "decision_match": sum(record["decision_match"] for record in items),
                "all_cards_safe": sum(record["all_safe"] for record in items),
                "catch_read_right": f"{sum(caught)}/{len(caught)}",
                "cards": len(cards),
                "cards_safe": sum(card["decision_safe"] for card in cards),
                "cards_exact": sum(card["exact"] for card in cards),
                "cards_invalid": sum(not card["valid"] for card in cards),
                "truncated_calls": sum(record["truncated_calls"] for record in items),
                "fields_correct": sum(record["fields_correct"] for record in items),
                "fields_total": sum(record["fields_total"] for record in items),
                "safe_by_variant": {
                    name: f"{safe[name]}/{count}" for name, count in sorted(variants.items())
                },
                "wrong_fields": dict(
                    Counter(name for card in cards for name in card["wrong"]).most_common()
                ),
                "mean_model_calls": round(mean(r["model_calls"] for r in items), 2),
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
        "| Model | Arm | Worlds | Decision right | All cards safe | Catch read right "
        "| Cards safe | Cards exact | Invalid | Truncated calls | Fields right | Calls | Input tok "
        "| Output tok | Median ms |"
    )
    lines = [head, "|" + "---|" * 15]
    for row in rows:
        lines.append(
            f"| {row['model']} | {row['arm']} | {row['worlds']} "
            f"| {row['decision_match']}/{row['runs']} | {row['all_cards_safe']}/{row['runs']} "
            f"| {row['catch_read_right']} | {row['cards_safe']}/{row['cards']} "
            f"| {row['cards_exact']}/{row['cards']} | {row['cards_invalid']} "
            f"| {row['truncated_calls']} "
            f"| {row['fields_correct']}/{row['fields_total']} | {row['mean_model_calls']} "
            f"| {row['mean_input_tokens']} | {row['mean_output_tokens']} "
            f"| {row['median_latency_ms']} |"
        )
    return "\n".join(lines) + "\n"
