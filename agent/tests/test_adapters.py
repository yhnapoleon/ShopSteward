import pytest
from langchain_core.messages import AIMessage

import shopsteward_agent as package


def test_adapters_exist():
    assert hasattr(package, "OpenAIModel")
    assert hasattr(package, "FencedPostgresSaver")


@pytest.mark.asyncio
async def test_chat_completions_adapter():
    class Client:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content="ok", tool_calls=[{"name": "read", "args": {}, "id": "x"}])

    model = package.OpenAIModel(
        base_url="https://example.invalid/v1", model="test", client=Client()
    )
    result = await model.complete([], [])
    assert result["tool_calls"][0]["function"]["arguments"] == "{}"


def test_memory_atomic_budget_duplicate_and_ambiguity():
    assert hasattr(package, "apply_memory_changes")
    policy = package.apply_memory_changes
    assert policy(["one"], [{"action": "add", "content": "one"}], "USER") == ["one"]
    assert policy(
        ["one"], [{"action": "replace", "old_text": "one", "content": "two"}], "USER"
    ) == ["two"]
    with pytest.raises(ValueError, match="ambiguous"):
        policy(["one a", "one b"], [{"action": "remove", "old_text": "one"}], "USER")
    old = ["one"]
    with pytest.raises(ValueError, match="budget"):
        policy(old, [{"action": "add", "content": "x" * 1375}], "USER")
    assert old == ["one"]
    assert policy(
        ["x" * 1375],
        [{"action": "add", "content": "two"}, {"action": "remove", "old_text": "x"}],
        "USER",
    ) == ["two"]
