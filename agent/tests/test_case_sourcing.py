"""The sourcing loop on a fake desk: who reads what, which cards count, what the solver gets."""

import json
import re

import pytest

RECOVERY = {"store_id": "S1", "sku_id": "K1", "evaluated_at": "2026-10-01T00:00:00Z"}
QUOTE = "报价单号：Q-A\n有效期：2026-09-01 至 2026-10-20\n| K1 | 12件/箱 | 24 | 12.00 | 下单后1个自然日内送达 |"
SUPPLIERS = [
    {
        "supplier_id": "A",
        "name": "安和商贸",
        "documents": [
            {"doc_id": "A-quote", "kind": "quote", "text": QUOTE},
            {
                "doc_id": "A-history",
                "kind": "history",
                "text": "PO-1,2026-09-02,2026-09-03,2026-09-03",
            },
        ],
    },
    {
        "supplier_id": "B",
        "name": "百川批发",
        "documents": [{"doc_id": "B-terms", "kind": "terms", "text": "配送范围为：东区、南区。"}],
    },
]
CARD_A = {
    "supplier_id": "A",
    "status": "offer",
    "reason": None,
    "offer": {
        "unit_price_minor": 1200,
        "minimum_order_quantity": 24,
        "pack_size": 12,
        "lead_time_days": 1,
        "valid_from": "2026-09-01",
        "valid_until": "2026-10-20",
        "offer_version": "Q-A",
    },
    "history": {"deliveries": 1, "late": 0},
    "citations": [
        {"field": "unit_price_minor", "doc_id": "A-quote", "quote": "| 24 | 12.00 |"},
        {"field": "minimum_order_quantity", "doc_id": "A-quote", "quote": "| 12件/箱 | 24 |"},
        {"field": "lead_time_days", "doc_id": "A-quote", "quote": "下单后1个自然日内送达"},
        {"field": "valid_until", "doc_id": "A-quote", "quote": "至 2026-10-20"},
    ],
}
CARD_B = {
    "supplier_id": "B",
    "status": "no_offer",
    "reason": "STORE_NOT_SERVED",
    "offer": None,
    "history": {"deliveries": 0, "late": 0},
    "citations": [{"field": "status", "doc_id": "B-terms", "quote": "配送范围为：东区、南区。"}],
}
EXPLANATION = {
    "claims": [
        {
            "statement": "A_24 is recommended",
            "support": ["proposal:offers"],
            "kind": "calculation",
            "subject": {"type": "candidate", "id": "A_24"},
            "applicability": {"result": "recommended"},
        }
    ],
    "missing": [],
    "followup_requests": [],
}


def day(number, lost):
    return {"settlement_at": f"2026-10-0{number}T23:00:00Z", "lost_qty": lost}


class Solver:
    """Stands in for the caller's solver: waits, or buys the cheapest offer's minimum."""

    def __init__(self, gap=20):
        self.gap, self.inputs = gap, []

    async def __call__(self, recovery):
        self.inputs.append(recovery["offers"])
        if len(recovery["offers"]) > 3:
            return None
        wait = {
            "id": "wait",
            "quantity": 0,
            "feasible": True,
            "lost_qty": self.gap,
            "daily": [day(1, 0), day(2, self.gap), day(3, 0)],
        }
        bought = [
            {
                "id": f"{offer['supplier_id']}_{offer['minimum_order_quantity']}",
                "quantity": offer["minimum_order_quantity"],
                "feasible": True,
                "lost_qty": 0,
                "daily": [day(1, 0), day(2, 0), day(3, 0)],
            }
            for offer in recovery["offers"]
        ]
        return {
            "id": "proposal:offers" if bought else "proposal:wait",
            "candidates": [wait, *bought],
            "recommended_candidate_id": bought[0]["id"] if bought else "wait",
        }


class Desk:
    """Plays every reviewer and the explainer; `cards` maps a supplier to its successive answers."""

    def __init__(self, cards, name="main"):
        self.cards, self.name = {k: list(v) for k, v in cards.items()}, name
        self.calls, self.shown = [], []

    async def complete(self, messages, tools, **kwargs):
        names = sorted(tool["function"]["name"] for tool in tools)
        text = "\n".join(str(message.get("content")) for message in messages)
        self.shown.append(text)
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        if "read_supplier_document" not in names:
            self.calls.append(("explain", names))
            return {"content": json.dumps(EXPLANATION), "usage": usage}
        sid = re.search(r'"supplier": \{"supplier_id": "(\w+)"', text).group(1)
        self.calls.append((sid, names))
        if not any(message["role"] == "tool" for message in messages):
            listed = json.loads(text[text.index('{"role": "supplier"') :].split("\n")[0])
            return {
                "content": "",
                "usage": usage,
                "tool_calls": [
                    {
                        "id": f"{sid}-{index}",
                        "function": {
                            "name": "read_supplier_document",
                            "arguments": json.dumps({"doc_id": doc["doc_id"]}),
                        },
                    }
                    for index, doc in enumerate([*listed["documents"], {"doc_id": "A-quote"}])
                ],
            }
        answer = self.cards[sid].pop(0)
        if answer == "ask":
            call = {"id": "q", "function": {"name": "clarify", "arguments": '{"question": "?"}'}}
            return {"content": "", "usage": usage, "tool_calls": [call]}
        return {
            "content": answer if isinstance(answer, str) else json.dumps(answer),
            "usage": usage,
        }


async def run(desk, *, suppliers=SUPPLIERS, solver=None, **options):
    from shopsteward_agent.cases import source_case
    from shopsteward_agent.context import ModelProfile

    solver = solver or Solver()
    result = await source_case(
        RECOVERY,
        suppliers,
        district="西湖区",
        solve=solver,
        case_id="c",
        revision_id="1",
        run_id="root",
        model=desk,
        profile=ModelProfile(model_id=desk.name, max_input_tokens=64000),
        **options,
    )
    return result, solver


@pytest.mark.asyncio
async def test_each_reviewer_reads_only_its_supplier_and_the_solver_gets_the_accepted_offers():
    desk = Desk({"A": [CARD_A], "B": [CARD_B]})
    result, solver = await run(desk)

    assert result["request"] == {
        "store_id": "S1",
        "district": "西湖区",
        "sku_id": "K1",
        "as_of": "2026-10-01",
        "shortfall_qty": 20,
        "short_from": "2026-10-02",
    }
    by_id = {item["supplier_id"]: item for item in result["reviews"]}
    assert {sid: item["status"] for sid, item in by_id.items()} == {
        "A": "accepted",
        "B": "accepted",
    }
    # Both reviewers also asked for A-quote; only A's own scope could serve it.
    assert by_id["A"]["attempts"][0]["opened"] == ["A-history", "A-quote"]
    assert by_id["B"]["attempts"][0]["opened"] == ["B-terms"]
    assert all(names == ["clarify", "read_supplier_document"] for who, names in desk.calls[:4])

    (offer,) = result["offers"]
    assert (offer["supplier_id"], offer["unit_price_minor"], offer["lead_time_seconds"]) == (
        "A",
        1200,
        86400,
    )
    assert solver.inputs == [[], [offer]]
    assert result["proposal"]["recommended_candidate_id"] == "A_24"
    analysis = result["analysis"]
    assert analysis["strategy"] == "fixed" and analysis["merged"]["claims"]
    assert (result["status"], result["unreviewed"], result["advisory_only"]) == (
        "complete",
        [],
        True,
    )
    # Two reviewers at two calls each and one explanation, on one ledger.
    assert result["budget"]["model_calls"] == 5 == len(result["call_records"])
    assert {record["role"] for record in result["call_records"]} == {"supplier", "fixed"}
    assert result["review_bundle"]["revision"] == "seed"


@pytest.mark.asyncio
async def test_a_card_citing_unread_or_absent_text_gets_one_second_reading_by_the_stronger_model():
    from shopsteward_agent.context import ModelProfile

    invented = {**CARD_A, "citations": [{**c, "quote": "单价 9.00"} for c in CARD_A["citations"]]}
    weak = Desk({"A": [invented], "B": ["no card here"]})
    strong = Desk({"A": [CARD_A], "B": [CARD_B]}, name="strong")
    result, _ = await run(
        weak,
        role_models={
            "supplier_escalation": (strong, ModelProfile(model_id="strong", max_input_tokens=64000))
        },
    )
    attempts = {item["supplier_id"]: item["attempts"] for item in result["reviews"]}
    assert [a["model"] for a in attempts["A"]] == ["main", "strong"]
    assert attempts["A"][0]["problems"] == [
        "uncited:unit_price_minor",
        "uncited:minimum_order_quantity",
        "uncited:lead_time_days",
        "uncited:valid_until",
    ]
    assert attempts["B"][0]["problems"] == ["invalid_card"] and attempts["B"][1]["problems"] == []
    assert result["status"] == "complete" and len(result["offers"]) == 1
    # The stronger model only does the second readings, and is told why the first failed.
    assert sorted(who for who, _ in strong.calls) == ["A", "A", "B", "B"]
    assert any("was rejected (invalid_card)" in text for text in strong.shown)
    assert not any("was rejected" in text for text in weak.shown)


@pytest.mark.asyncio
async def test_a_supplier_that_cannot_be_reviewed_is_left_out_and_named():
    # B's reviewer answers with a card about A; A's reviewer keeps asking the user.
    desk = Desk({"A": ["ask", "ask"], "B": [CARD_A, CARD_A]})
    result, solver = await run(desk)
    attempts = {item["supplier_id"]: item["attempts"] for item in result["reviews"]}
    assert [a["problems"] for a in attempts["A"]] == [["asked_user"], ["asked_user"]]
    assert [a["problems"] for a in attempts["B"]] == [["wrong_supplier"], ["wrong_supplier"]]
    assert sorted(result["unreviewed"]) == ["A", "B"] and result["offers"] == []
    # Nothing usable: the solver is not asked again and the explanation covers waiting.
    assert solver.inputs == [[]]
    assert result["proposal"]["recommended_candidate_id"] == "wait"
    assert result["status"] == "partial" and result["analysis"] is not None


@pytest.mark.asyncio
async def test_no_gap_means_no_reviewer_is_started_and_too_many_offers_is_reported_unsolved():
    quiet = Desk({})
    result, solver = await run(quiet, solver=Solver(gap=0))
    assert result["reviews"] == [] and solver.inputs == [[]]
    assert [who for who, _ in quiet.calls] == ["explain"]

    def copy(sid):
        text = json.dumps(CARD_A).replace("A-quote", f"{sid}-quote")
        return {**json.loads(text), "supplier_id": sid}

    many = [
        {
            "supplier_id": sid,
            "documents": [{"doc_id": f"{sid}-quote", "kind": "quote", "text": QUOTE}],
        }
        for sid in "CDEF"
    ]
    crowded, _ = await run(Desk({sid: [copy(sid)] for sid in "CDEF"}), suppliers=many)
    assert len(crowded["offers"]) == 4 and crowded["proposal"] is None
    assert (crowded["status"], crowded["analysis"]) == ("unsolved", None)
