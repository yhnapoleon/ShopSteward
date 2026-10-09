"""Optimizer wiring with offline models; needs the separate optimizer environment."""

import json
from pathlib import Path

import pytest

pytest.importorskip("gepa")
pytest.importorskip("langgraph")

DATASET = Path(__file__).resolve().parents[2] / "datasets" / "ops-synthetic-v1"


def test_search_improves_a_text_sensitive_model_using_only_train_and_val_cases(tmp_path):
    from shopsteward_agent.cases import load_bundle
    from shopsteward_agent.context import ModelProfile

    from shopsteward_pt.strategy_eval.cases import load_dataset
    from shopsteward_pt.strategy_eval.evolve import evolve
    from shopsteward_pt.strategy_eval.runner import OracleModel

    pairs = load_dataset(DATASET)
    train = [p for p in pairs if p[1]["partition"] == "evo-train"][:3]
    val = [p for p in pairs if p[1]["partition"] == "evo-val"][:3]
    oracle = OracleModel([fixture for _, fixture in train + val])

    class Literal:
        """States the solver result only when its instructions ask for typed claims."""

        async def complete(self, messages, tools, **kwargs):
            if "TYPED" in json.dumps(messages):
                return await oracle.complete(messages, tools)
            claim = {"statement": "The order is late.", "support": ["proposal:unknown"]}
            fixture = next(f for key, f in oracle.proposals.items() if key in json.dumps(messages))
            claim["support"] = [fixture["proposal"]["id"]]
            return {
                "content": json.dumps({"claims": [claim], "missing": [], "followup_requests": []})
            }

    prompts = []

    class Reflector:
        async def complete(self, messages, tools, **kwargs):
            prompts.append(messages[0]["content"])
            return {"content": "```\nCompare the solver candidates. Emit TYPED claims.\n```"}

    best, result, adapter = evolve(
        train + val,
        base=load_bundle(),
        strategy="fixed",
        task_model=Literal(),
        task_profile=ModelProfile(model_id="fake", max_input_tokens=128000),
        reflection_model=Reflector(),
        components=["question.options"],
        max_metric_calls=30,
        run_dir=tmp_path / "gepa",
        minibatch=2,
    )
    assert "TYPED" in best["question.options"]
    assert max(result.val_aggregate_scores) == 1.0 and result.val_aggregate_scores[0] == 0.0
    # The reflection model was told which required claims were missing, from train cases only.
    assert "Required typed claims that were not stated" in prompts[0]
    seen = {case for entry in adapter.log for case in entry["cases"]}
    assert seen <= {case.case_id for case, _ in train + val}

    gate = [p for p in pairs if p[1]["partition"] == "gate"][:1]
    with pytest.raises(ValueError, match="only evo-train and evo-val"):
        evolve(
            train + gate,
            base=load_bundle(),
            strategy="fixed",
            task_model=Literal(),
            task_profile=ModelProfile(model_id="fake"),
            reflection_model=Reflector(),
            components=["question.options"],
            max_metric_calls=5,
            run_dir=tmp_path / "leak",
        )


def sourcing_worlds():
    from shopsteward_pt.strategy_eval.cases import load_dataset

    worlds = [world for _, world in load_dataset(DATASET.parent / "ops-sourcing-v1")]
    return {
        name: [world for world in worlds if world["partition"] == name][:2]
        for name in ("evo-train", "evo-val", "gate")
    }


class Reflector:
    """Always proposes the same text and keeps the prompts it was shown."""

    def __init__(self, text):
        self.text, self.prompts = text, []

    async def complete(self, messages, tools, **kwargs):
        self.prompts.append(messages[0]["content"])
        return {"content": f"```\n{self.text}\n```"}


def test_the_explanation_of_the_sourcing_loop_is_evolved_alone_with_validation_repeated(tmp_path):
    from shopsteward_agent.cases import load_bundle
    from shopsteward_agent.context import ModelProfile

    from shopsteward_pt.strategy_eval.endtoend import OracleDesk
    from shopsteward_pt.strategy_eval.evolve import evolve_stage

    parts = sourcing_worlds()
    worlds = parts["evo-train"] + parts["evo-val"]
    desk = OracleDesk(worlds)

    class Forgetful:
        """Leaves out every gap claim unless its instructions carry the marker."""

        async def complete(self, messages, tools, **kwargs):
            reply = await desk.complete(messages, tools, **kwargs)
            if "STATE-EVERY-GAP" in json.dumps(messages):
                return reply
            answer = json.loads(reply["content"])
            answer["claims"] = [c for c in answer["claims"] if c["subject"]["type"] != "gap"]
            return {**reply, "content": json.dumps(answer)}

    reflector = Reflector("Compare the solver candidates. STATE-EVERY-GAP.")
    options = {
        "base": load_bundle(),
        "stage": "explain",
        "task_model": Forgetful(),
        "task_profile": ModelProfile(model_id="fake", max_input_tokens=128000),
        "reflection_model": reflector,
        "components": ["question.options"],
        "minibatch": 2,
    }
    best, result, adapter = evolve_stage(
        worlds, max_metric_calls=40, run_dir=tmp_path / "gepa", val_replicates=2, **options
    )
    assert "STATE-EVERY-GAP" in best["question.options"]
    scores = list(result.val_aggregate_scores)
    assert scores[0] == pytest.approx(1 / 3) and max(scores) == 1.0
    assert "Required typed claims that were not stated" in reflector.prompts[0]
    # Every validation world is run twice; nothing outside train and val is touched.
    assert sorted(adapter.log[0]["cases"]) == sorted(2 * [w["case_id"] for w in parts["evo-val"]])
    assert {case for entry in adapter.log for case in entry["cases"]} <= {
        world["case_id"] for world in worlds
    }
    with pytest.raises(ValueError, match="only evo-train and evo-val"):
        evolve_stage(
            worlds + parts["gate"], max_metric_calls=5, run_dir=tmp_path / "leak", **options
        )


def test_the_reviewer_text_is_evolved_from_feedback_that_names_the_field_and_its_source(tmp_path):
    from shopsteward_agent.cases import load_bundle
    from shopsteward_agent.context import ModelProfile

    from shopsteward_pt.strategy_eval.endtoend import OracleDesk
    from shopsteward_pt.strategy_eval.evolve import evolve_stage

    parts = sourcing_worlds()
    worlds = parts["evo-train"] + parts["evo-val"]
    desk = OracleDesk(worlds)

    class Careless:
        """Reads every price one yuan too high unless its instructions carry the marker."""

        async def complete(self, messages, tools, **kwargs):
            reply = await desk.complete(messages, tools, **kwargs)
            if "CHECK-EVERY-PRICE" in json.dumps(messages) or not reply["content"]:
                return reply
            card = json.loads(reply["content"])
            if card["offer"]:
                card["offer"]["unit_price_minor"] += 100
            return {**reply, "content": json.dumps(card)}

    reflector = Reflector("Read every document of the supplier. CHECK-EVERY-PRICE.")
    best, result, adapter = evolve_stage(
        worlds,
        base=load_bundle(bundle_id="supplier-review"),
        stage="read",
        task_model=Careless(),
        task_profile=ModelProfile(model_id="fake", max_input_tokens=128000),
        reflection_model=reflector,
        components=["question.supplier"],
        max_metric_calls=80,
        run_dir=tmp_path / "gepa",
        val_replicates=1,
        minibatch=3,
    )
    assert "CHECK-EVERY-PRICE" in best["question.supplier"]
    scores = list(result.val_aggregate_scores)
    assert scores[0] < 1 and max(scores) == 1.0
    assert "unit_price_minor: returned" in reflector.prompts[0]
    assert "the documents support" in reflector.prompts[0] and "-quote" in reflector.prompts[0]
    # One example is one supplier, so a world appears once per supplier it has.
    suppliers = sum(len(world["suppliers"]) for world in parts["evo-val"])
    assert len(adapter.log[0]["cases"]) == suppliers


def test_oversized_text_scores_zero_and_an_outage_stops_the_search_instead_of_scoring_zero():
    from shopsteward_agent.cases import load_bundle
    from shopsteward_agent.context import ModelProfile

    from shopsteward_pt.strategy_eval.cases import load_dataset
    from shopsteward_pt.strategy_eval.evolve import MAX_COMPONENT_CHARS, CaseBundleAdapter

    batch = [p for p in load_dataset(DATASET) if p[1]["partition"] == "evo-train"][:2]

    class Down:
        calls = 0

        async def complete(self, messages, tools, **kwargs):
            self.calls += 1
            raise ConnectionError("no route")

    model = Down()
    adapter = CaseBundleAdapter(
        base=load_bundle(),
        strategy="fixed",
        model=model,
        profile=ModelProfile(model_id="fake", max_input_tokens=128000),
    )
    adapter.retry_waits = (0, 0)
    long = adapter.evaluate(batch, {"question.options": "x" * (MAX_COMPONENT_CHARS + 1)})
    assert long.scores == [0.0, 0.0] and model.calls == 0
    assert "characters" in adapter.log[-1]["notes"][0]
    with pytest.raises(RuntimeError, match="provider unavailable"):
        adapter.evaluate(batch, {"question.options": "Compare the candidates."})
    assert model.calls >= 3  # each example was retried before the search was stopped
