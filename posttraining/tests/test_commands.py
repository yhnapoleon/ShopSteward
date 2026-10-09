import json
from pathlib import Path

import pytest
from shopsteward_agent.task_policy.contracts import decision_tool_schemas

from shopsteward_pt.eval import commands


@pytest.mark.asyncio
async def test_resume_completes_reviewed_clarification_and_rescore_is_repeatable(
    tmp_path, monkeypatch
):
    root = Path(__file__).resolve().parents[2]
    row = json.loads(
        (root / "posttraining/datasets/smoke-50.jsonl").read_text(encoding="utf-8").splitlines()[28]
    )
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps(row) + "\n", encoding="utf-8")
    context = {
        "messages": [{"role": "user", "content": row["user_message"]}],
        "mission_id": "m",
        "plan_id": "p",
        "mission_version": 1,
        "quantity_unit": "件",
        "quantity_cap": None,
        "tool_schemas": decision_tool_schemas(),
        "context_version": "test",
    }
    frozen = tmp_path / "contexts.json"
    frozen.write_text(json.dumps({row["episode_id"]: context}), encoding="utf-8")
    monkeypatch.setattr(
        commands,
        "load_runtime",
        lambda _: {"dataset": str(dataset), "frozen_contexts": str(frozen)},
    )
    monkeypatch.setattr(commands, "manifest", lambda *args: {"dataset_sha256": "fixed"})
    run = tmp_path / "run"
    first = await commands.evaluate("unused", run, ["B0"], "decision")
    assert first["B0"]["pending_reviews"] == 1
    directory = run / "decision/B0"
    pending = json.loads((directory / "pending-reviews.jsonl").read_text(encoding="utf-8"))
    commands.write_rows(
        directory / "reviews.jsonl",
        [{**pending, "relevant": True, "no_guess": True, "no_known_id_request": True}],
    )
    second = await commands.evaluate("unused", run, ["B0"], "decision", resume=True)
    assert second["B0"]["action_accuracy"] == {"correct": 2, "total": 2, "rate": 1.0}
    raw = (directory / "raw.jsonl").read_bytes()
    summary = commands.rescore(directory)
    assert summary["pending_reviews"] == 0 and summary["core_success"] is None
    assert commands.rescore(directory) == summary
    await commands.evaluate("unused", run, ["B0"], "decision", resume=True)
    assert (directory / "raw.jsonl").read_bytes() == raw
    monkeypatch.setattr(
        commands, "manifest", lambda *args: {"dataset_sha256": "fixed", "prompt_sha256": "v2"}
    )
    with pytest.raises(ValueError, match="prompt_sha256"):
        await commands.evaluate("unused", run, ["B0"], "decision", resume=True)


def test_manifest_hashes_selected_prompt(tmp_path, monkeypatch):
    import hashlib
    import sys
    from types import ModuleType, SimpleNamespace

    from shopsteward_agent.task_policy.policy import RestrictedPolicy

    fake = ModuleType("app.core.config")
    fake.Settings = lambda **kwargs: SimpleNamespace(
        agent_model="test", agent_base_url="https://example.invalid", agent_api_mode="responses"
    )
    monkeypatch.setitem(sys.modules, "app.core.config", fake)
    monkeypatch.setattr(commands.subprocess, "check_output", lambda *a, **kw: "test-head")
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    runtime = {
        "dataset": str(dataset),
        "frozen_contexts": str(dataset),
        "app_env_file": "unused",
        "policies": {"B1": {"prompt_version": "v2"}},
    }
    metadata = commands.manifest(runtime, "B1", "decision")
    actual = RestrictedPolicy(None, prompt_version="v2").system_prompt
    assert metadata["prompt_sha256"] == hashlib.sha256(actual.encode()).hexdigest()
    assert metadata["prompt_version"] == "v2"
    runtime["policies"]["B1"]["prompt_version"] = "v1"
    assert (
        commands.manifest(runtime, "B1", "decision")["prompt_sha256"] != metadata["prompt_sha256"]
    )
