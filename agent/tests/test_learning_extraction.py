import json

import pytest


class Model:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    async def complete(self, messages, tools):
        self.calls += 1
        return {"content": self.outputs.pop(0), "tool_calls": []}


@pytest.mark.asyncio
async def test_candidates_are_bounded_and_cannot_forge_provenance():
    from shopsteward_agent.learning.extractor import ExtractionError, extract_candidates

    model = Model(
        ["reflection", json.dumps({"candidates": [{"spec": {}, "evidence_ids": ["forged"]}]})]
    )
    with pytest.raises(ExtractionError, match="evidence"):
        await extract_candidates(
            {"events": [{"id": "real", "document": {}}], "allowed_tools": []}, [], model
        )
    assert model.calls == 2


@pytest.mark.asyncio
async def test_disabled_budget_does_not_call_model():
    from shopsteward_agent.learning.extractor import ExtractionError, extract_candidates

    model = Model([])
    with pytest.raises(ExtractionError, match="budget"):
        await extract_candidates(
            {"events": [{"id": "x", "document": {"text": "x" * 13000}}]}, [], model
        )
    assert model.calls == 0


@pytest.mark.asyncio
async def test_valid_candidate_and_one_json_repair():
    from shopsteward_agent.learning.extractor import extract_candidates

    result = {"candidates": [{"spec": {"title": "compare"}, "evidence_ids": ["e"]}]}
    model = Model(["reflection", "invalid", json.dumps(result)])
    candidates = await extract_candidates({"events": [{"id": "e", "document": {}}]}, [], model)
    assert candidates == result["candidates"] and model.calls == 3
