"""The whole loop in the real agent runtime, offline; needs the main project environment."""

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

DATA = Path(__file__).parents[2] / "datasets" / "ops-sourcing-v1"


@pytest.fixture(scope="module")
def worlds():
    from shopsteward_pt.strategy_eval.cases import load_dataset

    return [world for _, world in load_dataset(DATA) if world["partition"] == "smoke"]


def profile():
    from shopsteward_agent.context import ModelProfile

    return ModelProfile(model_id="fake", max_input_tokens=128000)


class Watched:
    """The true-answer desk, optionally altering reviewer cards; keeps what every call saw."""

    def __init__(self, worlds, alter=None):
        from shopsteward_pt.strategy_eval.endtoend import OracleDesk

        self.desk, self.alter, self.shown = OracleDesk(worlds), alter, []

    async def complete(self, messages, tools, **kwargs):
        self.shown.append("\n".join(str(message.get("content")) for message in messages))
        reply = await self.desk.complete(messages, tools, **kwargs)
        reviewing = any(tool["function"]["name"] == "read_supplier_document" for tool in tools)
        if self.alter and reviewing and reply["content"]:
            reply = {**reply, "content": json.dumps(self.alter(json.loads(reply["content"])))}
        return reply


def run(world, model):
    from shopsteward_pt.strategy_eval.endtoend import run_world

    return asyncio.run(run_world(world, model=model, profile=profile()))


def test_every_stage_passes_on_true_answers_and_no_reviewer_sees_the_answer_key(worlds):
    model = Watched(worlds)
    for world in worlds:
        record, outcome = run(world, model)
        assert record["success"] and all(record["stages"].values()), world["case_id"]
        assert outcome["request"] == world["request"]
        assert outcome["proposal"]["candidates"] == world["proposal"]["candidates"]
        assert record["second_readings"] == 0 and record["status"] == "complete"
        # Two calls per supplier (open the documents, then answer) and one explanation.
        assert record["model_calls"] == 2 * len(world["suppliers"]) + 1
        assert record["tool_calls"] == sum(len(s["documents"]) for s in world["suppliers"])
    assert not any('"variant"' in text or '"evidence"' in text for text in model.shown)


def test_a_misread_catch_fails_the_cards_and_the_decision_but_not_the_other_stages(worlds):
    world = next(w for w in worlds if w["family"] == "withdrawn")
    catch = world["catch"]
    quote = next(
        doc["text"]
        for s in world["suppliers"]
        if s["supplier_id"] == catch["supplier_id"]
        for doc in s["documents"]
        if doc["kind"] == "quote"
    )
    row = next(
        line for line in quote.splitlines() if line.startswith(f"| {world['request']['sku_id']} |")
    )
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    excerpt = quote.splitlines()[0]

    def ignore_the_withdrawal(card):
        if card["supplier_id"] != catch["supplier_id"]:
            return card
        return {
            **card,
            "status": "offer",
            "reason": None,
            "offer": {
                "unit_price_minor": round(float(cells[4]) * 100),
                "minimum_order_quantity": int(cells[3]),
                "pack_size": int(cells[2].split("件")[0]),
                "lead_time_days": 1,
                "valid_from": "2026-09-01",
                "valid_until": "2026-10-30",
                "offer_version": "Q",
            },
            "citations": [
                {"field": name, "doc_id": f"{catch['supplier_id']}-quote", "quote": excerpt}
                for name in (
                    "unit_price_minor",
                    "minimum_order_quantity",
                    "lead_time_days",
                    "valid_until",
                )
            ],
        }

    record, _ = run(world, Watched(worlds, alter=ignore_the_withdrawal))
    assert record["stages"]["request"] and record["stages"]["reviewed"]
    assert not record["stages"]["cards"] and not record["stages"]["decision"]
    assert (
        not record["success"]
        and record["decision"] != world["proposal"]["recommended_candidate_id"]
    )
    wrong = {card["supplier_id"]: card["wrong"][0] for card in record["cards"] if card["wrong"]}
    assert wrong == {catch["supplier_id"]: "status"}


def test_cards_without_excerpts_are_read_twice_then_left_out_and_reported(worlds):
    world = worlds[0]

    def strip(card):
        return {**card, "citations": []}

    record, outcome = run(world, Watched(worlds, alter=strip))
    assert record["second_readings"] == len(world["suppliers"])
    assert sorted(record["unreviewed"]) == sorted(s["supplier_id"] for s in world["suppliers"])
    assert not record["stages"]["reviewed"] and not record["success"]
    assert outcome["offers"] == [] and record["decision"] == "wait"
    assert all(len(card["attempts"]) == 2 for card in record["cards"])
