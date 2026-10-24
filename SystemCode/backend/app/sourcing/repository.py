"""Supplier documents on file for a store, and the text artifacts the agents run on."""

import json

from sqlalchemy import delete, func, select

from app.core.errors import AppError
from app.operations.models import OfferRow, ProductRow
from app.sourcing.models import SourcedOfferRow, SupplierDocumentRow
from app.sourcing.sample import sample_suppliers
from app.sourcing.schemas import SupplierDocumentSet, TextBundleEntry


async def suppliers(session, store_id):
    """[{supplier_id, name, documents: [{doc_id, kind, text}]}], the shape a reviewer is given."""
    rows = await session.scalars(
        select(SupplierDocumentRow)
        .where(SupplierDocumentRow.store_id == store_id)
        .order_by(SupplierDocumentRow.supplier_id, SupplierDocumentRow.doc_id)
    )
    found = {}
    for row in rows:
        entry = found.setdefault(
            row.supplier_id,
            {"supplier_id": row.supplier_id, "name": row.supplier_name, "documents": []},
        )
        entry["documents"].append({"doc_id": row.doc_id, "kind": row.kind, "text": row.text})
    return list(found.values())


async def connected(session, store_id):
    """Suppliers whose offer comes from the business source, not from documents."""
    offered = set(
        await session.scalars(
            select(OfferRow.supplier_id).where(OfferRow.store_id == store_id).distinct()
        )
    )
    read = set(
        await session.scalars(
            select(SourcedOfferRow.supplier_id)
            .where(SourcedOfferRow.store_id == store_id)
            .distinct()
        )
    )
    return offered - read


async def listing(session, store_id):
    linked = await connected(session, store_id)
    return SupplierDocumentSet(
        store_id=store_id,
        suppliers=[
            {**entry, "connected": entry["supplier_id"] in linked}
            for entry in await suppliers(session, store_id)
        ],
    )


async def replace(session, store_id, supplier_id, name, documents):
    if supplier_id in await connected(session, store_id):
        # Its offer is already structured and current; documents must not become a second source.
        raise AppError(
            409,
            "SUPPLIER_CONNECTED",
            "This supplier's offer already comes from the business source",
        )
    if len({doc["doc_id"] for doc in documents}) != len(documents):
        raise AppError(422, "DOCUMENT_ID_REPEATED", "Each document needs its own id")
    now = await session.scalar(select(func.clock_timestamp()))
    await session.execute(
        delete(SupplierDocumentRow).where(
            SupplierDocumentRow.store_id == store_id, SupplierDocumentRow.supplier_id == supplier_id
        )
    )
    for doc in documents:
        session.add(
            SupplierDocumentRow(
                store_id=store_id,
                supplier_id=supplier_id,
                supplier_name=name,
                created_at=now,
                **doc,
            )
        )
    await session.flush()


async def load_sample(session, store_id, sku_id, district):
    if await session.get(ProductRow, (store_id, sku_id)) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "This store does not carry that item")
    known = await session.scalar(
        select(OfferRow)
        .where(OfferRow.store_id == store_id, OfferRow.sku_id == sku_id)
        .order_by(OfferRow.supplier_id)
        .limit(1)
    )
    now = await session.scalar(select(func.clock_timestamp()))
    # Priced around what the store pays today, so the comparison is a plausible one.
    base = known.document["unit_price_minor"] if known else 1000
    for entry in sample_suppliers(sku_id, store_id, now.date(), base, district):
        await replace(session, store_id, entry["supplier_id"], entry["name"], entry["documents"])


def text_bundles(settings):
    """Every released text artifact with what it changed from its parent and where it runs."""
    from shopsteward_agent.cases.bundle import BUNDLES, TextBundle

    enabled = [
        (("case-experts", settings.agent_case_text_bundle), "case_explanation"),
        (("case-experts", settings.agent_sourcing_text_bundle), "sourcing_explanation"),
        (("supplier-review", settings.agent_sourcing_review_bundle), "supplier_review"),
    ]
    loaded = {}
    for path in sorted(BUNDLES.glob("*/*.json")):
        bundle = TextBundle.model_validate(json.loads(path.read_text(encoding="utf-8")))
        loaded[(bundle.bundle_id, bundle.revision)] = bundle
    items = []
    for (bundle_id, revision), bundle in loaded.items():
        parent = loaded.get((bundle_id, bundle.parent_revision))
        origin = bundle.provenance
        items.append(
            TextBundleEntry(
                bundle_id=bundle_id,
                revision=revision,
                parent_revision=bundle.parent_revision,
                content_hash=bundle.content_hash,
                origin=origin.get("origin"),
                stage=origin.get("stage"),
                dataset=origin.get("dataset"),
                task_model=(origin.get("task_profile") or {}).get("model_id"),
                reflection_model=(origin.get("reflection_profile") or {}).get("model_id"),
                seed=origin.get("seed"),
                metric_calls=origin.get("max_metric_calls"),
                changes=[
                    {"component": name, "before": parent.components[name], "after": text}
                    for name, text in bundle.components.items()
                    if parent and parent.components[name] != text
                ],
                gate=bundle.gate,
                enabled_for=sorted(use for key, use in enabled if key == (bundle_id, revision)),
            )
        )
    return items
