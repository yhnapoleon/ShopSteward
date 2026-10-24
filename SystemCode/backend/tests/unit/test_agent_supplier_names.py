from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agent_bridge.presentation import deadline_verdicts, local_times, supplier_names_in
from app.agent_bridge.tools import case_for_agent, supplier_ids, supplier_names

NAMES = {"A": "Anhe Trading", "B": "Baichuan Wholesale", "supplier_001": "Huaxin Dairy"}


def test_every_supplier_the_model_reads_carries_its_name():
    detail = {
        "excluded_supplier_ids": ["supplier_001"],
        "recheck_reason": "Supplier B declined; 供应商B 不再参与比价。",
        "proposal": {
            "recommended_candidate_id": "A_30",
            "candidates": [
                {"id": "A_30", "supplier_id": "A", "quantity": 30},
                {"id": "wait", "supplier_id": None, "quantity": 0},
            ],
        },
        "expert_analysis": {
            "merged": {
                "claims": [
                    {"kind": "interpretation", "statement": "Before supplier B was ruled out."}
                ]
            }
        },
    }
    value = case_for_agent(detail)
    assert supplier_ids(value) == {"A", "supplier_001"}
    named = supplier_names_in(value, NAMES)
    assert named["proposal"]["candidates"][0]["supplier_name"] == "Anhe Trading"
    assert "supplier_name" not in named["proposal"]["candidates"][1]
    assert named["expert_analysis"]["findings"] == ["Before Baichuan Wholesale was ruled out."]
    assert named["recheck_reason"] == (
        "Baichuan Wholesale declined; Baichuan Wholesale 不再参与比价。"
    )
    # Ids stay the keys the tools take back.
    assert named["proposal"]["recommended_candidate_id"] == "A_30"
    assert named["excluded_supplier_ids"] == ["supplier_001"]
    assert supplier_names_in({"supplier_id": "C", "supplier_name": "Own"}, NAMES) == {
        "supplier_id": "C",
        "supplier_name": "Own",
    }


async def test_names_come_from_offers_first_then_supplier_documents():
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                [("supplier_001", {"supplier_name": "Huaxin Dairy"}), ("A", {})],
                [("A", "Anhe Trading"), ("supplier_001", "Other name")],
            ]
        )
    )
    value = {"action": {"supplier_id": "supplier_001"}, "supplier_ids": ["A"]}
    assert await supplier_names(session, "s", value) == {
        "A": "Anhe Trading",
        "supplier_001": "Huaxin Dairy",
    }
    empty = SimpleNamespace(execute=AsyncMock())
    assert await supplier_names(empty, "s", {"sku_id": "k"}) == {}
    empty.execute.assert_not_called()


def test_the_model_gets_the_products_validity_verdict_not_a_deadline():
    now = datetime(2026, 10, 21, 7, 0, tzinfo=UTC)
    plan = {
        "status": "PENDING_APPROVAL",
        "created_at": "2026-10-21T06:08:00Z",
        "expires_at": "2026-10-21T07:08:00Z",
        "input_snapshot": {
            "offer": {
                "supplier_id": "supplier_001",
                "valid_from": "2026-10-21T06:00:00Z",
                "valid_until": "2026-10-22T06:21:00Z",
            },
            "source_fresh_until": "2026-10-21T06:30:00Z",
        },
        "proposal": {"expires_at": "2026-10-21T06:59:00+00:00"},
        "sourced": {"valid_until": "2026-11-20"},
    }
    value = local_times(deadline_verdicts(plan, now))
    assert value["expired"] is False and "expires_at" not in value
    assert "expires_at_local" not in value and value["created_at_local"] == "Wed 21/10 14:08"
    assert value["proposal"] == {"expired": True}
    # What a plan was made from is a record, not a verdict to apply now.
    assert value["input_snapshot"] == {"offer": {"supplier_id": "supplier_001"}}
    # A quote's own validity date, read out of a document, stays as written.
    assert value["sourced"]["valid_until"] == "2026-11-20"
