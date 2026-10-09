"""The sourcing loop: one reviewer per supplier, the solver decides, one explanation.

The root states what it needs. Each reviewer reads only its own supplier's
documents, through a tool, and returns an offer card. Code accepts a card only
if it parses and every excerpt it cites is in a document that reviewer really
opened; a rejected card gets one second reading, by a stronger model when one
is configured. The caller's solver turns the accepted cards into a proposal and
the usual explanation runs on that. Every call draws on one ledger.
"""

import asyncio
import json
import time

from langgraph.checkpoint.memory import InMemorySaver

from ..context import AdmissionBoundary, ContextBuilder, MessageEnvelope
from ..offer_cards import CONTRACT, parse, to_offer, unsupported
from ..runtime import Runtime, RuntimeFailure
from .budget import CallBudget
from .bundle import load_bundle
from .frozen import analyze_frozen_case

ROLE, SECOND = "supplier", "supplier_escalation"
READ = {
    "type": "function",
    "function": {
        "name": "read_supplier_document",
        "description": "Read one listed document of the supplier under review; "
        "never modifies business state.",
        "parameters": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
            "additionalProperties": False,
        },
    },
}


def supply_request(recovery, baseline, district):
    """What the root asks of every reviewer: the item, the store, the date and the gap."""
    wait = next(c for c in baseline["candidates"] if c["id"] == "wait")
    short = next((day for day in wait["daily"] if day["lost_qty"] > 0), None)
    return {
        "store_id": recovery["store_id"],
        "district": district,
        "sku_id": recovery["sku_id"],
        "as_of": recovery["evaluated_at"][:10],
        "shortfall_qty": wait["lost_qty"],
        "short_from": short and short["settlement_at"][:10],
    }


def gate(raw, supplier, opened):
    """Return (card, problems) without any answer key; a card with problems is not used."""
    card = parse(raw)
    if card is None:
        return None, ["invalid_card"]
    if card["supplier_id"] != supplier["supplier_id"]:
        return None, ["wrong_supplier"]
    read = [doc for doc in supplier["documents"] if doc["doc_id"] in opened]
    return card, [f"uncited:{name}" for name in unsupported(card, read)]


def _embedded(content):
    """Chat models often fence the object or add a sentence; accept one embedded object."""
    try:
        return json.loads(content[content.find("{") : content.rfind("}") + 1])
    except ValueError:
        return None


async def source_case(
    recovery,
    suppliers,
    *,
    district,
    solve,
    case_id,
    revision_id,
    run_id,
    model,
    profile,
    role_models=None,
    bundle=None,
    review_bundle=None,
    budget=None,
    record_call=None,
    strategy="fixed",
    parallel=3,
):
    """One advisory sourcing run. `solve` is the caller's trusted solver.

    `recovery` is the frozen recovery input without offers; `await solve(recovery)`
    returns a proposal with an `id`, or None when the input is not valid. Role
    models may name "supplier", "supplier_escalation" and the explaining role.
    """
    role_models = dict(role_models or {})
    review_bundle = review_bundle or load_bundle(bundle_id="supplier-review")
    # Room for two readings of every supplier plus the explanation; a ceiling, not a target.
    budget = budget or CallBudget(
        max_model_calls=8 * len(suppliers) + 2,
        max_tool_calls=2 * sum(len(s["documents"]) + 2 for s in suppliers) + 2,
        timeout_s=300,
    )
    records, turns = {}, asyncio.Semaphore(parallel)

    async def observe(record):
        records[(record["run_id"], record["role"], record["call_index"])] = record
        if record_call:
            await record_call(record)

    async def read(supplier, attempt, problems):
        """One reading by one reviewer, in its own runtime and its own document scope."""
        sid = supplier["supplier_id"]
        by_id = {doc["doc_id"]: doc for doc in supplier["documents"]}
        client, client_profile = role_models.get(SECOND if attempt > 1 else ROLE, (model, profile))
        reading = f"{run_id}:{ROLE}:{sid}:{attempt}"
        question = review_bundle.question(ROLE)
        if problems:
            question += (
                " An earlier card for this supplier was rejected ("
                + ", ".join(problems)
                + "). Read the documents again and return a corrected card."
            )

        async def call_tool(name, args, invocation_id):
            doc = by_id.get(args.get("doc_id")) if name == READ["function"]["name"] else None
            if doc is None:
                return {"ok": False, "error": "EVIDENCE_UNAVAILABLE", "references": []}
            return {
                "ok": True,
                "data": doc,
                "persisted": False,
                "references": [{"type": "supplier_document", "id": doc["doc_id"]}],
            }

        async def context():
            return json.dumps(
                {
                    "role": ROLE,
                    "request": request,
                    "supplier": {"supplier_id": sid, "name": supplier.get("name")},
                    "documents": [
                        {"doc_id": doc["doc_id"], "kind": doc.get("kind")}
                        for doc in supplier["documents"]
                    ],
                    "output_contract": "Return only the card. "
                    + CONTRACT
                    + " Cite only documents you opened. The card is advisory; no purchasing "
                    "approval or memory/plan writes.",
                },
                ensure_ascii=False,
            )

        attempt_record = {"attempt": attempt, "model": client_profile.model_id, "opened": []}
        async with turns:
            runtime = Runtime(
                client,
                InMemorySaver(),
                [READ],
                call_tool,
                context,
                context_builder=ContextBuilder(client_profile),
                admission=AdmissionBoundary(
                    kind="case",
                    run_id=reading,
                    case_id=case_id,
                    input_revision=int(revision_id) if str(revision_id).isdigit() else None,
                    input_through_seq=1,
                ),
                message_envelopes=[
                    MessageEnvelope(
                        message_id=f"{ROLE}:{sid}",
                        run_id=reading,
                        seq=1,
                        role="user",
                        content=question,
                    )
                ],
                max_model_calls=4,
                max_tool_calls=len(by_id) + 2,
                run_timeout=max(0.001, min(120, budget.deadline - time.time())),
                model_timeout=client_profile.timeout_s,
                shared_budget=budget,
                role=ROLE,
                record_call=observe,
            )
            try:
                result = await runtime.execute(reading, [{"role": "user", "content": question}])
            except RuntimeFailure as exc:
                return None, {**attempt_record, "problems": [exc.code]}
        attempt_record["opened"] = sorted(
            ref["id"] for ref in result["references"] if ref.get("type") == "supplier_document"
        )
        if result["status"] == "WAITING_INPUT":
            # A reviewer has the documents or it does not; it has nothing to ask the user.
            return None, {**attempt_record, "problems": ["asked_user"]}
        card, found = gate(_embedded(result["content"]), supplier, attempt_record["opened"])
        return (None if found else card), {**attempt_record, "problems": found}

    async def review(supplier):
        card, first = await read(supplier, 1, None)
        attempts = [first]
        if card is None:
            card, second = await read(supplier, 2, first["problems"])
            attempts.append(second)
        return {
            "supplier_id": supplier["supplier_id"],
            "status": "accepted" if card else "unreviewed",
            "card": card,
            "attempts": attempts,
        }

    baseline = await solve({**recovery, "offers": []})
    if baseline is None:
        raise ValueError("recovery_input_invalid")
    request = supply_request(recovery, baseline, district)
    # No gap means nothing to source; the explanation then covers waiting.
    reviews = (
        await asyncio.gather(*(review(supplier) for supplier in suppliers))
        if request["shortfall_qty"]
        else []
    )
    cards = [item["card"] for item in reviews if item["card"]]
    offers = [to_offer(card, recovery["sku_id"]) for card in cards if card["status"] == "offer"]
    proposal = await solve({**recovery, "offers": offers}) if offers else baseline
    unreviewed = [item["supplier_id"] for item in reviews if not item["card"]]
    outcome = {
        "request": request,
        "reviews": reviews,
        "unreviewed": unreviewed,
        "offers": offers,
        "proposal": proposal,
        "analysis": None,
        "review_bundle": {
            "revision": review_bundle.revision,
            "content_hash": review_bundle.content_hash,
        },
        "advisory_only": True,
    }
    if proposal is not None:
        # The explainer sees the accepted cards with their excerpts, so it knows who was
        # ruled out and that the offers are sourced; only the solver's numbers count.
        notes = {"cards": cards, "unreviewed": unreviewed}
        outcome["analysis"] = await analyze_frozen_case(
            {"recovery": {**recovery, "offers": offers}, "sourcing": notes},
            proposal,
            case_id=case_id,
            revision_id=revision_id,
            run_id=f"{run_id}:explain",
            strategy=strategy,
            model=model,
            profile=profile,
            bundle=bundle,
            role_models=role_models,
            budget=budget,
            record_call=observe,
            forced=True,
        )
    explained = outcome["analysis"] and outcome["analysis"]["status"] == "complete"
    snapshot = budget.snapshot()
    return {
        **outcome,
        "status": "unsolved"
        if proposal is None
        else "complete"
        if explained and not unreviewed
        else "partial",
        "budget": snapshot,
        "usage": snapshot["usage"],
        "cost_status": "unknown",
        "call_records": list(records.values()),
    }
