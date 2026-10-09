"""One stage of the sourcing loop graded on its own, offline; needs the main project environment."""

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


def bundles():
    from shopsteward_agent.cases import load_bundle

    return {"explain": load_bundle(), "read": load_bundle(bundle_id="supplier-review")}


class Altered:
    """The true-answer desk with its final answers passed through `alter`, one function per call."""

    def __init__(self, worlds, *alter):
        from shopsteward_pt.strategy_eval.endtoend import OracleDesk

        self.desk, self.alter, self.calls = OracleDesk(worlds), list(alter), 0

    async def complete(self, messages, tools, **kwargs):
        self.calls += 1
        reply = await self.desk.complete(messages, tools, **kwargs)
        if reply["content"] and self.alter:
            reply = {
                **reply,
                "content": json.dumps(self.alter.pop(0)(json.loads(reply["content"]))),
            }
        return reply


def run(stage, world, model, supplier=None):
    from shopsteward_pt.strategy_eval.stages import run_item

    return asyncio.run(
        run_item(stage, world, supplier, bundle=bundles()[stage], model=model, profile=profile())
    )


def priced(world):
    return next(s for s in world["suppliers"] if s["card"]["status"] == "offer")


def test_true_answers_pass_both_stages_at_the_cost_of_that_stage_alone(worlds):
    from shopsteward_pt.strategy_eval.stages import items

    model = Altered(worlds)
    for world in worlds:
        record, analysis = run("explain", world, model)
        assert (record["passed"], record["score"], record["model_calls"]) == (True, 1.0, 1)
        assert record["required"] == world["required"] and analysis["strategy"] == "fixed"
    explained = model.calls
    assert explained == len(worlds)
    for world, supplier in items(worlds, "read"):
        record, review = run("read", world, model, supplier)
        assert (record["passed"], record["exact"], record["first_reading"]) == (True, True, True)
        assert (record["score"], record["wrong"], record["model_calls"]) == (1.0, [], 2)
        assert review["card"]["supplier_id"] == supplier["supplier_id"] == record["supplier_id"]
    assert model.calls - explained == 2 * sum(len(world["suppliers"]) for world in worlds)


def test_an_explanation_is_scored_by_what_it_left_unsaid_and_zero_if_it_contradicts(worlds):
    world = worlds[0]
    chosen = world["proposal"]["recommended_candidate_id"]

    def silent(answer):
        claims = [c for c in answer["claims"] if c["subject"] != {"type": "gap", "id": chosen}]
        return {**answer, "claims": claims}

    def wrong(answer):
        return {
            **answer,
            "claims": [
                {**c, "applicability": {"result": "day-1"}}
                if c["subject"] == {"type": "gap", "id": chosen}
                else c
                for c in answer["claims"]
            ],
        }

    record, _ = run("explain", world, Altered([world], silent))
    assert (record["passed"], record["missing"]) == (False, [f"gap:{chosen}=none"])
    assert record["score"] == pytest.approx(2 / 3) and record["contradictions"] == []
    record, _ = run("explain", world, Altered([world], wrong))
    assert (record["passed"], record["score"]) == (False, 0.0)
    assert record["contradictions"] == [f"gap:{chosen}=day-1"]


def test_a_reading_passes_only_if_every_field_the_solver_reads_is_right(worlds):
    world = worlds[0]
    supplier = priced(world)
    price = supplier["card"]["offer"]["unit_price_minor"]

    def misread(card):
        return {**card, "offer": {**card["offer"], "unit_price_minor": price + 100}}

    def miscounted(card):
        return {**card, "history": {**card["history"], "late": card["history"]["late"] + 1}}

    def uncited(card):
        return {**card, "citations": card["citations"][1:]}

    # A citation that exists cannot catch a wrong number; the answer key does.
    record, review = run("read", world, Altered([world], misread), supplier)
    assert review["status"] == "accepted" and record["attempts"][0]["problems"] == []
    assert (record["passed"], record["score"], record["first_reading"]) == (False, 0.0, True)
    assert record["wrong"] == [{"field": "unit_price_minor", "got": price + 100, "expected": price}]
    # A field the solver does not read costs score, not the pass.
    record, _ = run("read", world, Altered([world], miscounted), supplier)
    assert record["passed"] and not record["exact"] and 0 < record["score"] < 1
    assert [item["field"] for item in record["wrong"]] == ["late"]
    # A rejected first card that is read right the second time passes, but not at first reading.
    record, review = run("read", world, Altered([world], uncited), supplier)
    assert (record["passed"], record["first_reading"], record["model_calls"]) == (True, False, 4)
    assert record["attempts"][0]["reasons"] == ["unit_price_minor: no citation was given"]
    assert "answer" in review["attempts"][0]


def test_a_batch_is_resumable_and_its_summary_names_the_repeated_failure(worlds, tmp_path, capsys):
    from shopsteward_pt.strategy_eval import stages
    from shopsteward_pt.strategy_eval.cli import main

    two = worlds[:2]

    def silent(answer):
        return {**answer, "claims": [c for c in answer["claims"] if c["subject"]["type"] != "gap"]}

    def batch(model, replicates):
        return asyncio.run(
            stages.run_batch(
                two,
                stage="explain",
                bundle=bundles()["explain"],
                model=model,
                profile=profile(),
                replicates=replicates,
                out=tmp_path,
                parallel=1,
            )
        )

    first = batch(Altered(two, silent), 1)
    assert [record["passed"] for record in first["records"]] == [False, True]
    again = Altered(two)
    assert len(batch(again, 2)["records"]) == 2 and again.calls == 2
    (row,) = stages.summarize(stages.load_records(tmp_path, "explain"))
    assert (row["runs"], row["items"], row["passed"]) == (4, 2, 3)
    assert row["failures"] == {"gap-unstated": 1} and row["first_reading"] is None
    kept = (tmp_path / "stage-explain-runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(kept) == 4 and "claims" in json.loads(kept[0])["merged"]

    arguments = ["stage", "--cases", str(DATA), "--out", str(tmp_path / "cli"), "--fake"]
    arguments += ["--partition", "smoke", "--limit", "1", "--stage", "read"]
    assert main(arguments) == 0
    printed = capsys.readouterr().out
    suppliers = len(worlds[0]["suppliers"])
    assert f"| read | oracle-fake | seed | smoke | {suppliers}/{suppliers} | 1.0 |" in printed
