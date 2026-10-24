"""A sourcing run reading the sample suppliers, with a scripted reviewer and no database."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

# Anhe Trading's offer as its sample documents state it: the notice in force raises the price.
CARD = {
    "supplier_id": "A",
    "status": "offer",
    "reason": None,
    "offer": {
        "unit_price_minor": 1020,
        "minimum_order_quantity": 20,
        "pack_size": 10,
        "lead_time_days": 2,
        "valid_from": "2026-10-01",
        "valid_until": "2026-11-20",
        "offer_version": "BJ-A-01",
    },
    "history": {"deliveries": 5, "late": 1},
    "citations": [
        {"field": "unit_price_minor", "doc_id": "A-notice-1", "quote": "| ITEM_1 | 9.20 | 10.20 |"},
        {"field": "minimum_order_quantity", "doc_id": "A-quote", "quote": "| 10件/箱 | 20 |"},
        {"field": "lead_time_days", "doc_id": "A-quote", "quote": "下单后2个自然日内送达"},
        {"field": "valid_until", "doc_id": "A-quote", "quote": "至 2026-11-20"},
    ],
}


class Rereader:
    """Opens all four documents, opens three of them again, then answers."""

    async def complete(self, messages, tools, **kwargs):
        opened = sum(message["role"] == "tool" for message in messages)
        if opened == 0:
            wanted = ["A-quote", "A-notice-1", "A-terms", "A-history"]
        elif opened == 4:
            wanted = ["A-quote", "A-notice-1", "A-terms"]
        else:
            return {"content": json.dumps(CARD, ensure_ascii=False)}
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": f"{opened}-{doc_id}",
                    "function": {
                        "name": "read_supplier_document",
                        "arguments": json.dumps({"doc_id": doc_id}),
                    },
                }
                for doc_id in wanted
            ],
        }


@pytest.mark.asyncio
async def test_anhe_is_read_although_its_reviewer_opens_documents_again(monkeypatch):
    from shopsteward_agent.context import ModelProfile

    from app.core.config import Settings
    from app.sourcing import run
    from app.sourcing.sample import sample_suppliers

    anhe = sample_suppliers("ITEM_1", "S1", date(2026, 10, 21), 1000)[0]
    assert anhe["name"] == "Anhe Trading" and len(anhe["documents"]) == 4
    profile = ModelProfile(model_id="reader", max_input_tokens=64000)
    monkeypatch.setattr(run, "reviewers", lambda settings: (Rereader(), profile, {}))
    row, finished = SimpleNamespace(sourcing={"reviews": []}), {}

    async def update(db, principal, case_id, run_id, change):
        return await change(None, row)

    async def register(session, row, work, reviews, text, budget, settings):
        finished.update(reviews=reviews, budget=budget)

    monkeypatch.setattr(run, "_update", update)
    monkeypatch.setattr(run, "register", register)
    work = {
        "run_id": "r",
        "revision": 1,
        "request": {"sku_id": "ITEM_1", "store_id": "S1", "shortfall_qty": 30},
        "suppliers": [anhe],
    }
    await run.execute(None, Settings(_env_file=None), None, "case", work)

    (review,) = finished["reviews"]
    assert (review["status"], review["card"]["offer"]["unit_price_minor"]) == ("accepted", 1020)
    assert [attempt["problems"] for attempt in review["attempts"]] == [[]]
    # Seven document reads, within the reading's allowance; the ledger holds two full readings.
    budget = finished["budget"]
    assert (budget["tool_calls"], budget["max_tool_calls"], budget["max_model_calls"]) == (
        7,
        20,
        12,
    )
    assert row.sourcing["reviews"] == [review]
