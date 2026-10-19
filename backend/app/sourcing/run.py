"""One sourcing run on a recovery Case.

The same loop the evaluation runs, placed in the product: one reviewer per supplier
reads only that supplier's documents and returns an offer card; code keeps a card only
when every excerpt it cites is in a document that reviewer opened. The kept offers are
registered as structured offers, the Case is solved again on them, and the usual
explanation follows. Reading happens between transactions; nothing here approves or
sends a purchase.
"""

import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from app.core.errors import AppError
from app.missions.models import MissionRow
from app.missions.repository import command
from app.operations.models import OfferRow
from app.operations.schemas import Offer
from app.operations_cases import repository as repo
from app.operations_cases.models import CaseRevisionRow
from app.operations_cases.processor import capture_snapshot
from app.operations_cases.schemas import CaseDetail
from app.planning.recovery.solver import solve
from app.sourcing.models import SourcedOfferRow
from app.sourcing.provider import configured, provider
from app.sourcing.repository import connected, suppliers

SECONDS = 300
COMPARED = 3  # the solver compares at most three offers
TERMINAL = {"CANCELLED", "RESOLVED", "CLOSED"}


def reviewers(settings):
    """(client, profile, role_models) for the reviewers."""
    from shopsteward_agent import OpenAIModel
    from shopsteward_agent.context import ModelProfile

    where = provider(settings)
    profile = ModelProfile(
        profile_id="sourcing-configured",
        model_id=where["model"],
        api_mode=where["api_mode"],
        reasoning_effort=settings.agent_reasoning_effort,
        max_input_tokens=settings.agent_max_input_tokens,
        max_output_tokens=settings.agent_max_output_tokens,
        timeout_s=settings.agent_model_timeout_seconds,
    )

    def client(profile):
        return OpenAIModel(
            base_url=where["base_url"],
            model=profile.model_id,
            profile=profile,
            key_file=where["key_file"],
        )

    roles = {}
    if settings.agent_sourcing_escalation_model:
        second = profile.model_copy(
            update={
                "profile_id": "sourcing-escalation",
                "model_id": settings.agent_sourcing_escalation_model,
            }
        )
        roles["supplier_escalation"] = (client(second), second)
    return client(profile), profile, roles


async def start(session, row, body, principal, key, settings):
    """Freeze what is asked of every reviewer and mark the run as started.

    Returns (detail, work); `work` is None on a replayed request.
    """
    from shopsteward_agent.cases.sourcing import supply_request

    receipt, replay = await command(
        session,
        principal.principal_id,
        "source_case",
        key,
        {"case_id": row.id, **body.model_dump(mode="json")},
    )
    if replay:
        return CaseDetail.model_validate(receipt.response), None
    repo.check_revision(row, body.expected_revision)
    now = await session.scalar(select(func.clock_timestamp()))
    previous = row.sourcing
    if previous and previous["status"] == "running" and now.timestamp() < previous["deadline"]:
        raise AppError(409, "SOURCING_IN_PROGRESS", "Reviewers are still reading for this Case")
    if not configured(settings):
        raise AppError(422, "SOURCING_MODEL_NOT_CONFIGURED", "No model is configured for reviewers")
    linked = await connected(session, row.store_id)
    readable = [
        entry
        for entry in await suppliers(session, row.store_id)
        if entry["supplier_id"] not in linked
    ]
    if not readable:
        raise AppError(422, "SUPPLIER_DOCUMENTS_REQUIRED", "No supplier documents are on file")
    revision = await session.get(CaseRevisionRow, (row.id, row.current_revision))
    from app.operations_cases.lifecycle import excluded

    # A supplier this case already left out is not read again.
    left_out = await excluded(session, row, revision.inputs)
    on_file = [entry for entry in readable if entry["supplier_id"] not in left_out]
    if not on_file:
        raise AppError(422, "NO_OTHER_SUPPLIERS", "Every supplier on file is left out of this Case")
    mission = await session.get(MissionRow, row.mission_id)
    snapshot, _ = await capture_snapshot(
        session, row, revision, mission, settings, with_offers=False
    )
    recovery = snapshot.recovery.model_dump(mode="json")
    request = supply_request(
        recovery, solve(snapshot.recovery).model_dump(mode="json"), body.district
    )
    if not request["shortfall_qty"]:
        raise AppError(422, "NO_SHORTFALL", "Waiting leaves no gap, so there is nothing to source")
    run_id = str(uuid4())
    row.sourcing = {
        "status": "running",
        "run_id": run_id,
        "revision": row.current_revision,
        "request": request,
        "suppliers": [
            {
                "supplier_id": entry["supplier_id"],
                "name": entry["name"],
                "documents": [
                    {"doc_id": doc["doc_id"], "kind": doc["kind"]} for doc in entry["documents"]
                ],
            }
            for entry in on_file
        ],
        "excluded": sorted(left_out),
        "reviews": [],
        "started_at": now.isoformat(),
        "deadline": now.timestamp() + SECONDS,
        "advisory_only": True,
    }
    await repo.event(session, row, "SOURCING_STARTED", {"run_id": run_id})
    await session.flush()
    result = await repo.detail(session, row)
    receipt.response = result.model_dump(mode="json")
    work = {"run_id": run_id, "revision": row.current_revision, "request": request}
    return result, {**work, "suppliers": on_file}


async def _update(db, principal, case_id, run_id, change):
    """Apply `change(session, row)` if this run is still the Case's current one."""
    async with db.session() as session, session.begin():
        row = await repo.visible(session, principal, case_id, lock=True)
        if (row.sourcing or {}).get("run_id") != run_id:
            return None
        return await change(session, row)


async def execute(db, settings, principal, case_id, work):
    """Read every supplier, register what passes the gate, solve, then explain."""
    from shopsteward_agent.cases import CallBudget, load_bundle, review_supplier

    run_id = work["run_id"]

    async def failed(session, row):
        row.sourcing = {**row.sourcing, "status": "failed", "missing": ["SOURCING_UNAVAILABLE"]}
        await repo.event(session, row, "SOURCING_FAILED", {"run_id": run_id})

    try:
        client, profile, roles = reviewers(settings)
        bundle = load_bundle(settings.agent_sourcing_review_bundle, bundle_id="supplier-review")
        budget = CallBudget(
            max_model_calls=8 * len(work["suppliers"]),
            max_tool_calls=2 * sum(len(s["documents"]) + 2 for s in work["suppliers"]),
            timeout_s=SECONDS - 60,
        )
        turns = asyncio.Semaphore(COMPARED)

        async def read(supplier):
            try:
                review = await review_supplier(
                    supplier,
                    work["request"],
                    case_id=case_id,
                    revision_id=str(work["revision"]),
                    run_id=run_id,
                    model=client,
                    profile=profile,
                    budget=budget,
                    role_models=roles,
                    review_bundle=bundle,
                    turns=turns,
                )
            except Exception:  # noqa: BLE001 - one reviewer failing must not lose the others
                review = {
                    "supplier_id": supplier["supplier_id"],
                    "status": "unreviewed",
                    "card": None,
                    "attempts": [
                        {
                            "attempt": 1,
                            "model": profile.model_id,
                            "opened": [],
                            "problems": ["reviewer_failed"],
                            "reasons": [],
                        }
                    ],
                }
            review["name"] = supplier["name"]

            async def add(session, row):
                # Shown as each reviewer finishes, so the owner sees the reading progress.
                row.sourcing = {**row.sourcing, "reviews": [*row.sourcing["reviews"], review]}

            await _update(db, principal, case_id, run_id, add)
            return review

        reviews = await asyncio.gather(*(read(supplier) for supplier in work["suppliers"]))
        text = {"revision": bundle.revision, "content_hash": bundle.content_hash}

        async def finish(session, row):
            return await register(session, row, work, reviews, text, budget.snapshot(), settings)

        solved = await _update(db, principal, case_id, run_id, finish)
    except Exception:  # noqa: BLE001 - the Case must not be left showing a run that died
        await _update(db, principal, case_id, run_id, failed)
        return
    if solved and settings.agent_api_key_file and settings.agent_case_model:
        from app.agent_bridge.context_cases import attach_case_experts

        # A sourced proposal is always explained when a Case model exists. The flag only
        # decides whether an ordinary analysis waits for an explanation.
        explaining = settings.model_copy(update={"agent_case_experts_enabled": True})
        await attach_case_experts(db, explaining, principal, case_id, *solved)


async def register(session, row, work, reviews, text, budget, settings):
    """Keep the accepted offers as structured offers and solve the Case on them."""
    from shopsteward_agent.offer_cards import to_offer

    now = await session.scalar(select(func.clock_timestamp()))
    offered = sorted(
        (
            review["card"]
            for review in reviews
            if review["card"] and review["card"]["status"] == "offer"
        ),
        key=lambda card: (card["offer"]["unit_price_minor"], card["supplier_id"]),
    )
    current = row.current_revision == work["revision"] and row.status not in TERMINAL
    linked = await connected(session, row.store_id)
    registered = []
    for card in offered[:COMPARED] if current else []:
        key = (row.store_id, row.sku_id, card["supplier_id"])
        if card["supplier_id"] in linked:
            continue
        document = Offer.model_validate(to_offer(card, row.sku_id)).model_dump(mode="json")
        offer = await session.get(OfferRow, key)
        if offer is None:
            session.add(
                OfferRow(store_id=key[0], sku_id=key[1], supplier_id=key[2], document=document)
            )
        else:
            offer.document = document
        read = await session.get(SourcedOfferRow, key)
        if read is None:
            read = SourcedOfferRow(store_id=key[0], sku_id=key[1], supplier_id=key[2])
            session.add(read)
        read.case_id, read.run_id, read.card, read.recorded_at = row.id, work["run_id"], card, now
        registered.append(card["supplier_id"])
    for review in reviews if current else []:
        # A supplier read earlier that now offers nothing no longer has an offer on file.
        key = (row.store_id, row.sku_id, review["supplier_id"])
        read = await session.get(SourcedOfferRow, key)
        if read is not None and review["card"] and review["card"]["status"] == "no_offer":
            await session.delete(read)
            await session.delete(await session.get(OfferRow, key))
    unreviewed = [review["supplier_id"] for review in reviews if not review["card"]]
    row.sourcing = {
        **row.sourcing,
        "status": "partial" if unreviewed or not current else "complete",
        "reviews": list(reviews),
        "unreviewed": unreviewed,
        "registered": registered,
        # Read correctly but not compared: only the cheapest three go to the solver.
        "left_out": [card["supplier_id"] for card in offered[COMPARED:]],
        "review_bundle": text,
        "explain_bundle": settings.agent_sourcing_text_bundle,
        "budget": budget,
        "finished_at": now.isoformat(),
        **({} if current else {"missing": ["CASE_INPUT_CHANGED"]}),
    }
    await repo.event(
        session, row, "SOURCING_COMPLETED", {"run_id": work["run_id"], "registered": registered}
    )
    if not registered:
        return None
    # A new revision compares exactly the suppliers that were just read.
    old = await session.get(CaseRevisionRow, (row.id, row.current_revision))
    mission = await session.get(MissionRow, row.mission_id)
    await repo.invalidate_pending(session, row, mission)
    row.current_revision += 1
    row.proposal_id, row.expert_analysis, row.status, row.missing_inputs = None, None, "OPEN", []
    session.add(
        CaseRevisionRow(
            case_id=row.id,
            revision=row.current_revision,
            inputs={**old.inputs, "supplier_ids": registered},
            evidence=[],
            created_at=now,
        )
    )
    row.sourcing = {**row.sourcing, "revision": row.current_revision}
    await repo.event(session, row, "CASE_REVISED", {"reason": "sourcing"})
    await session.flush()
    await repo.solve_revision(session, row, settings)
    return (row.current_revision, row.proposal_id) if row.proposal_id else None


def notes(case, snapshot):
    """What the explainer is told about the reading, when the offers on the table were sourced."""
    sourcing = case.sourcing or {}
    on_table = {offer["supplier_id"] for offer in snapshot["recovery"].get("offers", [])}
    if not on_table or not on_table <= set(sourcing.get("registered", [])):
        return None
    return {
        "cards": [review["card"] for review in sourcing["reviews"] if review["card"]],
        "unreviewed": sourcing.get("unreviewed", []),
    }
