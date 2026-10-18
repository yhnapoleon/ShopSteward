"""End-to-end over the real runner and solver; needs the main project environment."""

import json

import pytest

pytest.importorskip("langgraph")


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    from shopsteward_pt.strategy_eval.cases import load_dataset, write_dataset

    directory = tmp_path_factory.mktemp("ops")
    return directory, write_dataset(directory), load_dataset(directory)


def profile():
    from shopsteward_agent.context import ModelProfile

    return ModelProfile(model_id="fake", max_input_tokens=128000)


def test_dataset_is_deterministic_partitioned_and_true_to_each_family(dataset, tmp_path):
    from shopsteward_pt.strategy_eval.cases import load_dataset, write_dataset

    directory, manifest, pairs = dataset
    assert {name: len(ids) for name, ids in manifest["partitions"].items()} == {
        "smoke": 12,
        "evo-train": 12,
        "evo-val": 12,
        "gate": 24,
    }
    assert write_dataset(tmp_path)["sha256"] == manifest["sha256"]
    by_family = {}
    for case, fixture in pairs:
        by_family.setdefault(fixture["family"], []).append(fixture)
        assert case.required_condition_ids == tuple(fixture["required"])
    assert len(by_family) == 8
    assert all(sum(f["partition"] == "gate" for f in items) == 3 for items in by_family.values())
    for fixture in by_family["tight_budget"] + by_family["unverified_execution"]:
        assert fixture["required"][0] == "candidate:wait=recommended"
        assert fixture["required"][1].startswith("gap:wait=day-")
    assert all(f["required"][1] == "gap:wait=none" for f in by_family["no_action"])
    assert all(len(f["required"]) == 3 for f in by_family["late_cheap_offer"])

    fixtures = directory / "fixtures.jsonl"
    original = fixtures.read_text(encoding="utf-8")
    fixtures.write_text(original.replace('"on_hand": ', '"on_hand": 1', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        load_dataset(directory)
    fixtures.write_text(original, encoding="utf-8", newline="\n")


@pytest.mark.asyncio
async def test_every_strategy_is_scored_by_one_contract_and_finished_runs_are_not_repeated(
    dataset, tmp_path
):
    from shopsteward_agent.cases import load_bundle

    from shopsteward_pt.strategy_eval.runner import OracleModel, run_batch, summarize

    pairs = dataset[2][:2]
    arguments = {
        "strategies": ["fixed", "single", "static_multi", "adaptive_multi"],
        "bundle": load_bundle(),
        "model": OracleModel([fixture for _, fixture in pairs]),
        "profile": profile(),
        "out": tmp_path,
    }
    first = await run_batch(pairs, **arguments)
    records = first["records"]
    assert len(records) == 8
    assert all(r["score"] == 1.0 and r["task_success"] is True for r in records)
    calls = {r["strategy_id"]: r["model_calls"] for r in records}
    assert (calls["R0"], calls["R1"], calls["R2"]) == (1, 1, 3)
    assert all(r["mast"] == [] and not r["contradictions"] for r in records)
    assert len((tmp_path / "traces.jsonl").read_text(encoding="utf-8").splitlines()) == 8

    again = await run_batch(pairs, **arguments)
    assert again["records"] == [] and again["model_calls_sent"] == 0
    rows = summarize(records)
    assert [(row["strategy_id"], row["task_success"], row["runs"]) for row in rows] == [
        ("R0", 2, 2),
        ("R1", 2, 2),
        ("R2", 2, 2),
        ("R3", 2, 2),
    ]


@pytest.mark.asyncio
async def test_contradicting_the_solver_zeroes_the_score_and_fails_the_task(dataset):
    from shopsteward_agent.cases import load_bundle

    from shopsteward_pt.strategy_eval.runner import run_one

    case, fixture = next(
        pair for pair in dataset[2] if pair[1]["proposal"]["recommended_candidate_id"] != "wait"
    )

    class Contrarian:
        async def complete(self, messages, tools, **kwargs):
            claim = {
                "statement": "Waiting is the recommended option",
                "support": [fixture["proposal"]["id"]],
                "subject": {"type": "candidate", "id": "wait"},
                "applicability": {"result": "recommended"},
            }
            return {
                "content": json.dumps({"claims": [claim], "missing": [], "followup_requests": []})
            }

    item = await run_one(
        case,
        fixture,
        strategy="single",
        bundle=load_bundle(),
        model=Contrarian(),
        profile=profile(),
    )
    record = item["record"]
    assert (record["score"], record["task_success"]) == (0.0, False)
    assert record["critical_failures"] == ["solver_contradiction"]
    assert record["contradictions"] == ["candidate:wait=recommended"]
    assert record["input_tokens"] is None  # the provider reported no usage; never recorded as 0


@pytest.mark.asyncio
async def test_batch_limit_never_starts_a_run_it_could_not_finish(dataset):
    from shopsteward_agent.cases import load_bundle

    from shopsteward_pt.strategy_eval.runner import OracleModel, run_batch

    pairs = dataset[2][:4]
    outcome = await run_batch(
        pairs,
        strategies=["fixed"],
        bundle=load_bundle(),
        model=OracleModel([fixture for _, fixture in pairs]),
        profile=profile(),
        parallel=1,
        max_model_calls=15,
    )
    assert len(outcome["records"]) == 2 and len(outcome["skipped_for_limit"]) == 2
    assert outcome["model_calls_sent"] == 2


@pytest.mark.asyncio
async def test_provider_failures_are_rerun_later_instead_of_scored_as_strategy_failures(
    dataset, tmp_path
):
    from shopsteward_agent.cases import load_bundle

    from shopsteward_pt.strategy_eval.runner import OracleModel, run_batch

    pairs = dataset[2][:2]
    oracle = OracleModel([fixture for _, fixture in pairs])

    class Flaky:
        down = True

        async def complete(self, messages, tools, **kwargs):
            if self.down and pairs[0][0].case_id in str(messages):
                raise ConnectionError("provider unavailable")
            return await oracle.complete(messages, tools)

    model = Flaky()
    arguments = {
        "strategies": ["fixed"],
        "bundle": load_bundle(),
        "model": model,
        "profile": profile(),
        "out": tmp_path,
    }
    first = await run_batch(pairs, **arguments)
    assert [r["case_id"] for r in first["records"]] == [pairs[1][0].case_id]
    assert len(first["provider_errors"]) == 1
    model.down = False
    second = await run_batch(pairs, **arguments)
    assert [r["case_id"] for r in second["records"]] == [pairs[0][0].case_id]
    assert second["records"][0]["task_success"] is True
