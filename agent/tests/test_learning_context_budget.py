import json


def test_optional_learning_never_displaces_required_user_constraints():
    from shopsteward_agent.context import (
        AdmissionBoundary,
        ContextBuilder,
        MessageEnvelope,
        ModelProfile,
    )

    data = {
        "knowledge": [{"content": "explicit preference"}],
        "learned_skills": [
            {
                "asset_id": "skill",
                "revision": 1,
                "content_hash": "hash",
                "evaluation_id": "report",
                "spec": {"procedure": ["optional learned step " * 200]},
            }
        ],
    }
    result = ContextBuilder(ModelProfile(model_id="test", max_input_tokens=1800)).build(
        admission=AdmissionBoundary(run_id="r", conversation_id="c", input_through_seq=1),
        messages=[
            MessageEnvelope(message_id="u", run_id="r", seq=1, role="user", content="预算最多200元")
        ],
        system="rules",
        tools=[],
        current_context=json.dumps(data),
    )
    assert "预算最多200元" in str(result.messages)
    assert "explicit preference" in str(result.messages)
    assert "optional learned step" not in str(result.messages)
    assert result.manifest["learning_assets"] == []
    assert {"source_id": "skill:1", "reason": "learning_budget"} in result.manifest["omitted"]
