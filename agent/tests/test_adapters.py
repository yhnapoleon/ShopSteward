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


@pytest.mark.asyncio
async def test_responses_adapter_separates_text_from_protocol_blocks():
    class Client:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(
                content=[
                    {"type": "reasoning", "summary": []},
                    {"type": "text", "text": "方案依据", "annotations": []},
                    {"type": "function_call", "name": "read", "arguments": "{}"},
                ],
                tool_calls=[{"name": "read", "args": {}, "id": "call_1"}],
            )

    model = package.OpenAIModel(
        base_url="https://example.invalid/v1", model="test", client=Client()
    )
    result = await model.complete([], [])
    assert result["content"] == "方案依据"
    assert result["tool_calls"][0]["id"] == "call_1"


def test_responses_api_is_explicitly_configurable():
    model = package.OpenAIModel(
        base_url="https://example.invalid/v1",
        model="gpt-5.6-luna",
        key="test-key",
        api_mode="responses",
    )
    assert model.client.use_responses_api is True


@pytest.mark.asyncio
async def test_reasoning_effort_reaches_tool_call_request(monkeypatch):
    import json

    import httpx
    from langchain_openai import ChatOpenAI

    import shopsteward_agent.model as adapter

    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "probe",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "probe", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        monkeypatch.setattr(
            adapter,
            "ChatOpenAI",
            lambda **kwargs: ChatOpenAI(http_async_client=http_client, **kwargs),
        )
        model = package.OpenAIModel(
            base_url="https://example.invalid/v1",
            model="test",
            key="test-key",
            reasoning_effort="none",
        )
        tool = {
            "type": "function",
            "function": {
                "name": "probe",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        result = await model.complete(
            [{"role": "user", "content": "probe"}],
            [tool],
            tool_choice={"type": "function", "function": {"name": "probe"}},
        )
    assert requests[0]["reasoning_effort"] == "none"
    assert requests[0]["tool_choice"]["function"]["name"] == "probe"
    assert result["tool_calls"][0]["function"]["name"] == "probe"


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


@pytest.mark.asyncio
async def test_a_refused_forced_tool_choice_is_retried_unforced_with_an_instruction():
    class Refused(Exception):
        status_code = 400

    class Client:
        def __init__(self):
            self.calls = []

        def bind_tools(self, tools, **options):
            self.options = options
            return self

        async def ainvoke(self, messages):
            self.calls.append((self.options, messages))
            if self.options.get("tool_choice") == "required":
                raise Refused("Thinking mode does not support this tool_choice")
            return AIMessage(
                content="", tool_calls=[{"name": "memory_edit", "args": {}, "id": "x"}]
            )

    client = Client()
    model = package.OpenAIModel(base_url="https://example.invalid/v1", model="test", client=client)
    tools = [{"type": "function", "function": {"name": "memory_edit", "parameters": {}}}]
    result = await model.complete(
        [{"role": "user", "content": "Remember"}], tools, tool_choice="required"
    )
    assert result["tool_calls"][0]["function"]["name"] == "memory_edit"
    assert [options for options, _ in client.calls] == [{"tool_choice": "required"}, {}]
    assert "memory_edit" in client.calls[1][1][-1]["content"]
    # The refusal is remembered for this model: the next forced turn is not refused again.
    await model.complete([], tools, tool_choice="required")
    assert client.calls[-1][0] == {}


@pytest.mark.asyncio
async def test_other_provider_errors_are_not_retried():
    class Broken(Exception):
        status_code = 400

    class Client:
        def bind_tools(self, tools, **options):
            return self

        async def ainvoke(self, messages):
            raise Broken("context length exceeded")

    model = package.OpenAIModel(
        base_url="https://example.invalid/v1", model="test", client=Client()
    )
    with pytest.raises(Broken):
        await model.complete([], [], tool_choice="required")


@pytest.mark.asyncio
async def test_a_run_with_no_tools_sends_no_tool_list(monkeypatch):
    import json

    import httpx
    from langchain_openai import ChatOpenAI

    import shopsteward_agent.model as adapter

    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "probe",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "{}"},
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        monkeypatch.setattr(
            adapter,
            "ChatOpenAI",
            lambda **kwargs: ChatOpenAI(http_async_client=http_client, **kwargs),
        )
        model = package.OpenAIModel(
            base_url="https://example.invalid/v1", model="test", key="test-key"
        )
        result = await model.complete([{"role": "user", "content": "explain"}], [])
    # A Case explainer has no tools; OpenAI refuses an empty tool list.
    assert "tools" not in requests[0] and "tool_choice" not in requests[0]
    assert result["content"] == "{}"
