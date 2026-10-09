"""A card is graded field by field; its citations can be checked without an answer key."""

OFFER = {
    "unit_price_minor": 1380,
    "minimum_order_quantity": 24,
    "pack_size": 12,
    "lead_time_days": 2,
    "valid_from": "2026-09-01",
    "valid_until": "2026-10-20",
    "offer_version": "BJ-B-0901",
}
HISTORY = {"deliveries": 9, "late": 3}
SUPPLIER = {
    "card": {
        "supplier_id": "B",
        "status": "offer",
        "reason": None,
        "offer": OFFER,
        "history": HISTORY,
    },
    "evidence": {
        "unit_price_minor": ["B-notice-1"],
        "minimum_order_quantity": ["B-quote"],
        "lead_time_days": ["B-quote"],
        "valid_until": ["B-quote"],
    },
    "documents": [
        {
            "doc_id": "B-quote",
            "text": "有效期：2026-09-01 至 2026-10-20\n| X | 12件/箱 | 24 | 12.00 | 下单后2个自然日内送达 |",
        },
        {"doc_id": "B-notice-1", "text": "| X | 12.00 | 13.80 |"},
    ],
}
GONE = {
    "card": {
        "supplier_id": "C",
        "status": "no_offer",
        "reason": "SUPPLY_WITHDRAWN",
        "offer": None,
        "history": HISTORY,
    },
    "evidence": {"status": ["C-notice-1"]},
    "documents": [{"doc_id": "C-notice-1", "text": "暂停供应下列商品\n- X"}],
}


def cite(field, doc_id, quote):
    return {"field": field, "doc_id": doc_id, "quote": quote}


def card(**changes):
    return {**SUPPLIER["card"], "citations": [], **changes}


def test_fields_are_graded_one_by_one_and_only_solver_inputs_decide_safety():
    from shopsteward_pt.strategy_eval.cards import check_card

    exact = check_card(card(), SUPPLIER)
    assert (exact["correct"], exact["total"], exact["exact"], exact["decision_safe"]) == (
        10,
        10,
        True,
        True,
    )

    cosmetic = check_card(
        card(offer={**OFFER, "offer_version": "?"}, history={"deliveries": 9, "late": 4}), SUPPLIER
    )
    assert [name for name, state in cosmetic["fields"].items() if state == "wrong"] == [
        "offer_version",
        "late",
    ]
    assert cosmetic["decision_safe"] and not cosmetic["exact"]

    old_price = check_card(card(offer={**OFFER, "unit_price_minor": 1200}), SUPPLIER)
    assert old_price["fields"]["unit_price_minor"] == "wrong" and not old_price["decision_safe"]

    dropped = check_card(card(status="no_offer", reason="STORE_NOT_SERVED", offer=None), SUPPLIER)
    assert dropped["correct"] == 2 and not dropped["decision_safe"]

    withdrawn = {**GONE["card"], "citations": []}
    assert check_card(withdrawn, GONE)["exact"]
    wrong_reason = check_card({**withdrawn, "reason": "SKU_NOT_COVERED"}, GONE)
    assert wrong_reason["fields"]["reason"] == "wrong" and wrong_reason["decision_safe"]
    assert not check_card(card(supplier_id="C"), GONE)["decision_safe"]


def test_a_card_that_breaks_the_contract_scores_nothing():
    from shopsteward_pt.strategy_eval.cards import check_card

    for broken in (
        None,
        "B: 13.80",
        card(offer={**OFFER, "unit_price_minor": 13.8}),
        card(reason="STORE_NOT_SERVED"),
        card(status="no_offer", reason=None, offer=None),
        card(status="no_offer", reason="TOO_EXPENSIVE", offer=None),
        card(plan={"quantity": 48}),
    ):
        graded = check_card(broken, SUPPLIER)
        assert (graded["valid"], graded["correct"], graded["decision_safe"]) == (False, 0, False)
        assert graded["unsupported"] is None


def test_citations_are_exact_excerpts_and_must_point_at_the_governing_document():
    from shopsteward_pt.strategy_eval.cards import check_card, parse, unsupported

    cited = card(
        citations=[
            cite("unit_price_minor", "B-notice-1", "| X | 12.00 |  13.80 |"),  # spacing may differ
            cite("minimum_order_quantity", "B-notice-1", "13.80"),  # real text, wrong document
            cite("lead_time_days", "B-quote", "下单后3个自然日内送达"),  # not in the document
        ]
    )
    graded = check_card(cited, SUPPLIER)
    assert graded["citations"] == {
        "unit_price_minor": "sourced",
        "minimum_order_quantity": "grounded",
        "lead_time_days": "ungrounded",
        "valid_until": "absent",
    }
    assert graded["unsupported"] == ["lead_time_days", "valid_until"]

    gone = parse({**GONE["card"], "citations": [cite("status", "C-notice-1", "暂停供应下列商品")]})
    assert unsupported(gone, GONE["documents"]) == []
    assert unsupported({**gone, "citations": []}, GONE["documents"]) == ["status"]


def test_cards_become_solver_offers_and_an_unusable_set_is_no_decision():
    from shopsteward_pt.strategy_eval.cards import decide, to_offer
    from shopsteward_pt.strategy_eval.cases import build

    made = to_offer(SUPPLIER["card"], "sku-eval")
    assert made["lead_time_seconds"] == 172800 and made["supplier_id"] == "B"
    # The written last day is still valid, so the solver's exclusive end is the next midnight.
    assert (made["valid_from"], made["valid_until"]) == (
        "2026-09-01T00:00:00+00:00",
        "2026-10-21T00:00:00+00:00",
    )

    recovery = build(
        on_hand=10, demand=[10] * 7, inbound=[(40, 0, 5)], cash=200000, budget=70000, offers=[]
    )
    slow = {
        **SUPPLIER["card"],
        "supplier_id": "A",
        "offer": {**OFFER, "unit_price_minor": 900, "lead_time_days": 6},
    }
    lapsed = {
        **SUPPLIER["card"],
        "supplier_id": "C",
        "offer": {**OFFER, "unit_price_minor": 900, "valid_until": "2026-09-30"},
    }
    result = decide(recovery, [SUPPLIER["card"], slow, lapsed, GONE["card"]])
    # Stock lasts day 1 and the inbound order lands on day 6. B arrives on day 3, so it can
    # only cover days 3 to 5: 30 units, which is three cases.
    assert result.recommended_candidate_id == "B_36"
    reasons = {c.id: c.rejection_reasons for c in result.candidates}
    assert reasons["C_48"] == ["OFFER_EXPIRED"] and reasons["A_48"] == []

    fourth = {**SUPPLIER["card"], "supplier_id": "D"}
    assert decide(recovery, [SUPPLIER["card"], slow, lapsed, fourth]) is None
