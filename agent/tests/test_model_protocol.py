from types import SimpleNamespace

import pytest

from shopsteward_agent.model import OpenAIModel


@pytest.mark.asyncio
async def test_explicit_responses_adapter_replays_opaque_items_and_reports_actual_usage():
    from shopsteward_agent.context import ModelProfile

    class Transport:
        def __init__(self):
            self.requests = []
            self.responses = self

        async def create(self, **kwargs):
            self.requests.append(kwargs)
            return SimpleNamespace(
                model_dump=lambda **kwargs: {
                    "id": "resp1",
                    "model": "actual-model",
                    "status": "completed",
                    "output": [
                        {"type": "reasoning", "id": "rs1", "encrypted_content": "opaque"},
                        {
                            "type": "function_call",
                            "id": "fc1",
                            "call_id": "c1",
                            "name": "read",
                            "arguments": "{}",
                        },
                    ],
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 4,
                        "total_tokens": 14,
                        "input_tokens_details": {"cached_tokens": 2},
                        "output_tokens_details": {"reasoning_tokens": 3},
                    },
                }
            )

    transport = Transport()
    model = OpenAIModel(
        base_url="https://example.invalid/v1",
        model="configured",
        profile=ModelProfile(
            model_id="configured",
            api_mode="responses",
            reasoning_effort="low",
            max_output_tokens=777,
        ),
        responses_client=transport,
    )
    first = await model.complete([{"role": "user", "content": "read"}], [])
    await model.complete(
        [
            {"role": "user", "content": "read"},
            {"role": "assistant", "content": "", "provider_items": first["provider_items"]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
        ],
        [],
    )
    request = transport.requests[-1]
    assert request["input"][1:3] == first["provider_items"]
    assert request["input"][-1] == {
        "type": "function_call_output",
        "call_id": "c1",
        "output": '{"ok":true}',
    }
    assert request["store"] is False and "previous_response_id" not in request
    assert request["max_output_tokens"] == 777
    assert request["reasoning"] == {"effort": "low"}
    assert first["returned_model"] == "actual-model"
    assert first["usage"]["input_token_details"]["cache_read"] == 2
    assert first["usage"]["output_token_details"]["reasoning"] == 3


@pytest.mark.asyncio
async def test_replayed_items_carry_api_field_names_and_no_null_fields():
    from pydantic import BaseModel, ConfigDict, Field

    from shopsteward_agent.context import ModelProfile

    class Item(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        type: str = "function_call"
        call_id: str = "c1"
        name: str = "read"
        arguments: str = "{}"
        status: str | None = None
        async_: bool | None = Field(default=None, alias="async")

    class Reply(BaseModel):
        status: str = "completed"
        output: list[Item] = [Item(async_=False), Item(call_id="c2")]

    class Transport:
        responses = None

        async def create(self, **kwargs):
            return Reply()

    transport = Transport()
    transport.responses = transport
    model = OpenAIModel(
        base_url="https://example.invalid/v1",
        model="configured",
        profile=ModelProfile(model_id="configured", api_mode="responses"),
        responses_client=transport,
    )
    reply = await model.complete([{"role": "user", "content": "read"}], [])
    call = {"type": "function_call", "name": "read", "arguments": "{}"}
    assert reply["provider_items"] == [
        {**call, "call_id": "c1", "async": False},
        {**call, "call_id": "c2"},
    ]
    assert [item["id"] for item in reply["tool_calls"]] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_incomplete_reply_never_executes_partial_tool_calls():
    from test_runtime import Model, call, runtime

    from shopsteward_agent import RuntimeFailure

    run = runtime(
        Model(
            [
                {
                    "content": "partial",
                    "tool_calls": [call()],
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                }
            ]
        )
    )
    with pytest.raises(RuntimeFailure, match="model_incomplete"):
        await run.execute("truncated", [])


@pytest.mark.asyncio
async def test_chat_profile_reasoning_effort_reaches_actual_transport(monkeypatch):
    import json

    import httpx

    import shopsteward_agent.model as adapter
    from shopsteward_agent.context import ModelProfile

    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    original = adapter.ChatOpenAI
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        monkeypatch.setattr(
            adapter, "ChatOpenAI", lambda **kwargs: original(**kwargs, http_async_client=http)
        )
        model = OpenAIModel(
            base_url="https://example.invalid/v1",
            model="test",
            key="test-only",
            profile=ModelProfile(model_id="test", reasoning_effort="low"),
        )
        await model.complete([{"role": "user", "content": "hello"}], [])
    assert requests[0]["reasoning_effort"] == "low"
