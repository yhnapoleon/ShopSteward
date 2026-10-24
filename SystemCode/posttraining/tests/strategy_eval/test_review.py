"""The review loop offline: who sees which documents, and what a wrong card costs."""

import asyncio
import json
from pathlib import Path

import pytest

DATA = Path(__file__).parents[2] / "datasets" / "ops-sourcing-v1"


@pytest.fixture(scope="module")
def worlds():
    from shopsteward_pt.strategy_eval.cases import load_dataset

    return [world for _, world in load_dataset(DATA) if world["partition"] == "smoke"]


class Recording:
    """Returns the true cards, optionally altered, and remembers what each call was shown."""

    def __init__(self, worlds, alter=None, wrap=None):
        from shopsteward_pt.strategy_eval.review import OracleReviewer

        self.oracle, self.alter, self.wrap, self.seen = OracleReviewer(worlds), alter, wrap, []

    async def complete(self, messages, tools, **kwargs):
        assert tools == []
        self.seen.append(
            [s["supplier_id"] for s in json.loads(messages[-1]["content"])["suppliers"]]
        )
        reply = await self.oracle.complete(messages, tools)
        cards = json.loads(reply["content"])["cards"]
        if self.alter:
            cards = [self.alter(json.loads(json.dumps(card))) for card in cards]
        content = json.dumps({"cards": cards})
        usage = {"input_tokens": 100, "output_tokens": 20, "output_token_details": {"reasoning": 5}}
        return {"content": self.wrap(content) if self.wrap else content, "usage": usage}


def run(world, arm, model):
    from shopsteward_pt.strategy_eval.review import run_world

    async def go():
        return await run_world(world, arm=arm, model=model, gate=asyncio.Semaphore(2))

    return asyncio.run(go())


def test_split_reviewers_each_see_one_supplier_and_joint_sees_all(worlds):
    world = max(worlds, key=lambda w: len(w["suppliers"]))
    ids = [s["supplier_id"] for s in world["suppliers"]]
    fenced = Recording(worlds, wrap=lambda content: f"Here are the cards:\n```json\n{content}\n```")
    split = run(world, "split", fenced)
    assert sorted(fenced.seen) == [[sid] for sid in ids] and split["model_calls"] == len(ids)
    assert (split["input_tokens"], split["reasoning_tokens"]) == (100 * len(ids), 5 * len(ids))

    together = Recording(worlds)
    joint = run(world, "joint", together)
    assert together.seen == [ids] and joint["model_calls"] == 1
    for record in (split, joint):
        assert record["decision_match"] and record["all_safe"] and record["truncated_calls"] == 0
        assert record["fields_correct"] == record["fields_total"]
        assert record["decision"] == world["proposal"]["recommended_candidate_id"]


def test_reading_the_catch_the_careless_way_changes_the_decision(worlds):
    world = next(w for w in worlds if w["family"] == "notice_price")
    catch = world["catch"]
    supplier = next(s for s in world["suppliers"] if s["supplier_id"] == catch["supplier_id"])
    quote = next(doc["text"] for doc in supplier["documents"] if doc["kind"] == "quote")
    row = next(
        line for line in quote.splitlines() if line.startswith(f"| {world['request']['sku_id']} |")
    )
    quoted = float(row.split("|")[5])  # the unit price column, before the notice raised it

    def ignore_the_notice(card):
        if card["supplier_id"] == catch["supplier_id"]:
            card["offer"]["unit_price_minor"] = round(quoted * 100)
        return card

    record = run(world, "split", Recording(worlds, alter=ignore_the_notice))
    assert record["caught"] is False and not record["all_safe"] and not record["decision_match"]
    assert record["decision"] == catch["misread_recommendation"]
    wrong = {card["supplier_id"]: card["wrong"] for card in record["cards"] if card["wrong"]}
    assert wrong == {catch["supplier_id"]: ["unit_price_minor"]}


def test_an_unusable_answer_is_scored_as_wrong_cards_not_as_a_crash(worlds):
    world = worlds[0]
    record = run(world, "joint", Recording(worlds, wrap=lambda content: "I could not decide."))
    assert not record["decision_match"] and record["fields_correct"] == 0
    assert all(not card["valid"] for card in record["cards"])
    # With no card at all the solver can only wait.
    assert record["decision"] == "wait"


def test_batches_resume_respect_the_call_cap_and_keep_provider_errors_for_rerun(worlds, tmp_path):
    from shopsteward_pt.strategy_eval.review import PROMPT, load_records, run_batch, summarize

    class FailsOnce(Recording):
        async def complete(self, messages, tools, **kwargs):
            if not self.seen:
                self.seen.append(None)
                raise ConnectionError("down")
            return await super().complete(messages, tools, **kwargs)

    few, model = worlds[:3], FailsOnce(worlds)

    def batch(**options):
        return asyncio.run(
            run_batch(
                few,
                arms=["joint"],
                model=model,
                model_id="fake",
                out=tmp_path,
                parallel=1,
                **options,
            )
        )

    # Two of three runs fit the cap; the first of them meets the outage.
    first = batch(max_model_calls=2)
    assert len(first["skipped_for_limit"]) == 1 and first["model_calls_planned"] == 2
    assert [e["error"] for e in first["provider_errors"]] == ["ConnectionError: down"]
    assert len(first["records"]) == 1

    second = batch()
    assert len(second["records"]) == 2 and not second["provider_errors"]
    records = load_records(tmp_path)
    assert sorted(r["run_id"] for r in records) == sorted(
        f"{w['case_id']}:joint:fake:{PROMPT}:1" for w in few
    )
    assert batch()["records"] == []
    (row,) = summarize(records)
    assert (row["model"], row["arm"], row["prompt"], row["runs"]) == ("fake", "joint", PROMPT, 3)
    assert row["decision_match"] == 3 and row["cards_safe"] == row["cards"]
