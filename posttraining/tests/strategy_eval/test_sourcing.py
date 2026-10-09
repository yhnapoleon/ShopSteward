"""Sourcing worlds: the document rules are fixed by hand here, not by the generator."""

import json
import random
import shutil
from pathlib import Path

import pytest

DATA = Path(__file__).parents[2] / "datasets" / "ops-sourcing-v1"
REQUEST = {"store_id": "S1", "district": "西湖区", "sku_id": "FOODS_1_010", "as_of": "2026-10-01"}


def notice(number, kind, change, effective, revokes=None, item="FOODS_1_010"):
    return {
        "doc_id": f"B-notice-{number}",
        "no": f"TZ-{number}",
        "kind": kind,
        "issued": "2026-09-01",
        "effective": effective,
        "lines": {item: change},
        "revokes": revokes,
    }


def facts(*notices, unit="件", zone=("西湖区", "上城区"), listed="FOODS_1_010", until="2026-10-20"):
    row = {"pack": 12, "moq": 24, "price": 1200, "lead": 1}
    return {
        "supplier_id": "B",
        "zone": list(zone),
        "quote": {
            "no": "BJ-B-0901",
            "valid_from": "2026-09-01",
            "valid_until": until,
            "unit": unit,
            "rows": [{"item_id": listed, **row}, {"item_id": "FOODS_1_050", **row, "price": 900}],
        },
        "notices": list(notices),
        "history": [
            {"promised": "2026-09-03", "actual": "2026-09-03"},
            {"promised": "2026-09-10", "actual": "2026-09-12"},
        ],
    }


def offer(card):
    return {key: card["offer"][key] for key in ("unit_price_minor", "lead_time_days")}


def test_a_quote_stands_until_a_notice_in_force_changes_it():
    from shopsteward_pt.strategy_eval.sourcing import read

    card, evidence = read(facts(), REQUEST)
    assert card["status"] == "offer" and card["reason"] is None
    assert card["offer"] == {
        "unit_price_minor": 1200,
        "minimum_order_quantity": 24,
        "pack_size": 12,
        "lead_time_days": 1,
        "valid_from": "2026-09-01",
        "valid_until": "2026-10-20",
        "offer_version": "BJ-B-0901",
    }
    assert card["history"] == {"deliveries": 2, "late": 1}
    assert evidence["unit_price_minor"] == ["B-quote"]

    raised = notice(1, "price", (1200, 1380), "2026-09-28")
    card, evidence = read(facts(raised), REQUEST)
    assert offer(card) == {"unit_price_minor": 1380, "lead_time_days": 1}
    assert evidence["unit_price_minor"] == ["B-notice-1"] and evidence["lead_time_days"] == [
        "B-quote"
    ]

    slower = notice(2, "lead", (1, 4), "2026-10-01")  # in force on its effective day
    assert offer(read(facts(raised, slower), REQUEST)[0]) == {
        "unit_price_minor": 1380,
        "lead_time_days": 4,
    }
    not_yet = notice(1, "price", (1200, 1380), "2026-10-02")
    other_item = notice(2, "price", (900, 990), "2026-09-20", item="FOODS_1_050")
    assert offer(read(facts(not_yet, other_item), REQUEST)[0])["unit_price_minor"] == 1200


def test_the_latest_notice_in_force_wins_and_a_revoked_one_is_void():
    from shopsteward_pt.strategy_eval.sourcing import read

    first = notice(1, "price", (1200, 1380), "2026-09-20")
    later = notice(2, "price", (1380, 1300), "2026-09-25")
    assert offer(read(facts(later, first), REQUEST)[0])["unit_price_minor"] == 1300

    correction = notice(2, "price", (1380, 1230), "2026-09-28", revokes="TZ-1")
    card, evidence = read(facts(first, correction), REQUEST)
    assert card["offer"]["unit_price_minor"] == 1230 and evidence["unit_price_minor"] == [
        "B-notice-2"
    ]
    # A correction that is not yet in force has revoked nothing.
    pending = notice(2, "price", (1380, 1230), "2026-10-05", revokes="TZ-1")
    assert offer(read(facts(first, pending), REQUEST)[0])["unit_price_minor"] == 1380


def test_three_document_facts_end_the_offer_and_expiry_is_left_to_the_solver():
    from shopsteward_pt.strategy_eval.sourcing import read

    stopped = notice(1, "withdraw", None, "2026-09-30")
    for supplier, reason, source in (
        (facts(stopped), "SUPPLY_WITHDRAWN", "B-notice-1"),
        (facts(listed="FOODS_1_011"), "SKU_NOT_COVERED", "B-quote"),
        (facts(stopped, zone=("上城区",)), "STORE_NOT_SERVED", "B-terms"),
    ):
        card, evidence = read(supplier, REQUEST)
        assert (card["status"], card["reason"], card["offer"]) == ("no_offer", reason, None)
        assert evidence == {"status": [source]}
    elsewhere = notice(1, "withdraw", None, "2026-09-30", item="FOODS_1_050")
    later = notice(2, "withdraw", None, "2026-10-03")
    assert read(facts(elsewhere, later), REQUEST)[0]["status"] == "offer"

    lapsed = read(facts(until="2026-09-28"), REQUEST)[0]
    assert lapsed["status"] == "offer" and lapsed["offer"]["valid_until"] == "2026-09-28"


def test_each_named_misreading_gives_the_answer_a_careless_reader_would():
    from shopsteward_pt.strategy_eval.sourcing import read

    raised = notice(1, "price", (1200, 1380), "2026-09-20")
    correction = notice(2, "price", (1380, 1230), "2026-09-28", revokes="TZ-1")
    not_yet = notice(1, "price", (1200, 1380), "2026-10-02")

    def misread(supplier, mistake):
        return read(supplier, REQUEST, mistake)[0]

    assert misread(facts(raised), "notices")["offer"]["unit_price_minor"] == 1200
    assert misread(facts(not_yet), "future")["offer"]["unit_price_minor"] == 1380
    assert misread(facts(raised, correction), "revoked")["offer"]["unit_price_minor"] == 1380
    assert misread(facts(until="2026-09-28"), "expiry")["offer"]["valid_until"] == "2026-10-15"
    assert misread(facts(zone=("上城区",)), "zone")["status"] == "offer"
    assert misread(facts(listed="FOODS_1_011"), "near_miss")["offer"]["unit_price_minor"] == 1200
    by_case = misread(facts(unit="箱"), "unit")["offer"]
    assert (by_case["unit_price_minor"], by_case["minimum_order_quantity"]) == (14400, 2)


WINDOW = {
    "item_id": "FOODS_1_010",
    "sell_price_cents": 298,
    "neighbors": [
        {"item_id": f"FOODS_1_{n:03d}", "sell_price_cents": 100 + n} for n in range(11, 51)
    ],
}
MODES = {
    "First Class": {"promised_days": 1, "actual_days": {"2": 1}},
    "Standard Class": {"promised_days": 4, "actual_days": {"3": 1, "6": 1}},
}


def cells(text, item):
    line = next(line for line in text.splitlines() if line.startswith(f"| {item} |"))
    return [cell.strip() for cell in line.strip("|").split("|")]


@pytest.mark.parametrize(
    "variant", ["plain", "case_price", "notice_price", "lead_change", "superseded"]
)
def test_rendered_documents_say_what_the_facts_say(variant):
    from shopsteward_pt.strategy_eval.sourcing import _facts, documents, read

    request = {**REQUEST, "store_id": "CA_1"}
    supplier = _facts(
        random.Random(variant),
        "B",
        WINDOW,
        MODES,
        factor=0.9,
        mode="First Class",
        variant=variant,
        district="西湖区",
        need=40,
    )
    texts = {doc["doc_id"]: doc["text"] for doc in documents(supplier, request, "食品")}
    card, evidence = read(supplier, request)
    quote = supplier["quote"]
    row = next(row for row in quote["rows"] if row["item_id"] == "FOODS_1_010")
    scale = row["pack"] if variant == "case_price" else 1
    _, _, pack, minimum, price, lead = cells(texts["B-quote"], "FOODS_1_010")
    assert (pack, int(minimum) * scale, round(float(price) * 100)) == (
        f"{row['pack']}件/箱",
        row["moq"],
        row["price"] * scale,
    )
    assert lead == "下单后1个自然日内送达" and f"计价单位：{quote['unit']}" in texts["B-quote"]
    assert f"{quote['valid_from']} 至 {quote['valid_until']}" in texts["B-quote"]
    assert "西湖区" in texts["B-terms"] and card["status"] == "offer"
    assert texts["B-history"].count("PO-B-") == card["history"]["deliveries"] > 0
    assert card["history"]["late"] == card["history"]["deliveries"]  # promised 1 day, took 2

    governing = texts[evidence["unit_price_minor"][0]]
    assert f"{card['offer']['unit_price_minor'] / 100:.2f}" in governing or variant == "case_price"
    if variant == "lead_change":
        assert cells(texts[evidence["lead_time_days"][0]], "FOODS_1_010")[2] == (
            f"下单后{card['offer']['lead_time_days']}个自然日内送达"
        )
    if variant == "superseded":
        (revoking,) = [n for n in supplier["notices"] if n["revokes"]]
        assert f"撤销 {revoking['revokes']} 号通知函" in texts[revoking["doc_id"]]
        assert evidence["unit_price_minor"] == [revoking["doc_id"]]
    assert [doc_id for doc_id in texts if "notice" in doc_id] == [
        n["doc_id"] for n in sorted(supplier["notices"], key=lambda n: n["issued"])
    ]


@pytest.fixture(scope="module")
def worlds(tmp_path_factory):
    from shopsteward_pt.strategy_eval.cases import load_dataset
    from shopsteward_pt.strategy_eval.sourcing import write_dataset

    directory = tmp_path_factory.mktemp("sourcing")
    shutil.copy(DATA / "sources.json", directory)
    return write_dataset(directory), load_dataset(directory)


def test_the_committed_dataset_is_what_the_code_generates_from_its_sources(worlds):
    manifest, pairs = worlds
    assert manifest == json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert {name: len(ids) for name, ids in manifest["partitions"].items()} == {
        "smoke": 12,
        "evo-train": 12,
        "evo-val": 12,
        "gate": 24,
    }
    owners = {}
    for _, world in pairs:
        owners.setdefault(world["source"]["series_id"], set()).add(world["partition"])
    assert all(len(partitions) == 1 for partitions in owners.values())


def test_every_world_is_solved_from_its_cards_and_its_catch_changes_the_decision(worlds):
    from shopsteward_pt.strategy_eval.cards import check_card, decide
    from shopsteward_pt.strategy_eval.sourcing import FAMILIES, LOSES

    families = set()
    for case, world in worlds[1]:
        families.add(world["family"])
        cards = [supplier["card"] for supplier in world["suppliers"]]
        result = decide(world["snapshot"]["recovery"], cards)
        chosen = result.recommended_candidate_id
        assert chosen == world["proposal"]["recommended_candidate_id"]
        assert case.required_condition_ids == tuple(world["required"])
        assert world["required"][1:] == [f"gap:{chosen}=none", world["required"][2]]
        assert world["required"][2].startswith("gap:wait=day-")
        assert sum(card["status"] == "offer" for card in cards) <= 3
        assert all(check_card(s["card"], s)["exact"] for s in world["suppliers"])
        catch = world["catch"]
        if world["family"] == "baseline":
            assert catch is None and {s["variant"] for s in world["suppliers"]} == {"plain"}
            continue
        assert catch["mistake"] == FAMILIES[world["family"]]
        assert catch["misread_recommendation"] != chosen
        trapped = next(s for s in world["suppliers"] if s["supplier_id"] == catch["supplier_id"])
        assert trapped["variant"] == world["family"]
        assert chosen.startswith(catch["supplier_id"] + "_") != (world["family"] in LOSES)
    assert families == set(FAMILIES)
