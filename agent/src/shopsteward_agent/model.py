"""Explicit OpenAI API adapter, no provider detection or global settings."""

import json
from pathlib import Path

from langchain_openai import ChatOpenAI


class OpenAIModel:
    def __init__(
        self,
        *,
        base_url,
        model,
        key=None,
        key_file=None,
        client=None,
        api_mode="chat_completions",
        profile=None,
        responses_client=None,
    ):
        from .context import ModelProfile

        self.profile = profile or ModelProfile(model_id=model, api_mode=api_mode)
        api_mode = self.profile.api_mode
        self.api_mode = api_mode
        self.responses_client = responses_client
        if api_mode not in {"chat_completions", "responses"}:
            raise ValueError("unsupported API mode")
        if client is None and responses_client is None:
            if key is not None and key_file is not None:
                raise ValueError("choose key or key_file")
            if key_file is not None:
                key = Path(key_file).read_text(encoding="utf-8").strip()
            if not key:
                raise ValueError("model key required")
            client = ChatOpenAI(
                base_url=base_url,
                model=self.profile.model_id,
                api_key=key,
                timeout=self.profile.timeout_s,
                max_retries=0,
                use_responses_api=api_mode == "responses",
                max_completion_tokens=self.profile.max_output_tokens,
                **(
                    {"reasoning_effort": self.profile.reasoning_effort}
                    if api_mode == "chat_completions" and self.profile.reasoning_effort is not None
                    else {}
                ),
            )
            if api_mode == "responses":
                from openai import AsyncOpenAI

                self.responses_client = AsyncOpenAI(
                    base_url=base_url, api_key=key, timeout=self.profile.timeout_s, max_retries=0
                )
        self.client = client

    async def complete(self, messages, tools, *, tool_choice=None):
        if self.responses_client is not None:
            return await self._responses(messages, tools, tool_choice=tool_choice)
        options = {"tool_choice": tool_choice} if tool_choice else {}
        response = await self.client.bind_tools(tools, **options).ainvoke(messages)
        return {
            "content": response.text,
            "tool_calls": [
                {
                    "type": "function",
                    "id": c["id"],
                    "function": {
                        "name": c["name"],
                        "arguments": json.dumps(c["args"], ensure_ascii=False),
                    },
                }
                for c in response.tool_calls
            ]
            + [
                {
                    "type": "function",
                    "id": c.get("id"),
                    "function": {"name": c.get("name"), "arguments": c.get("args")},
                }
                for c in response.invalid_tool_calls
            ],
            "usage": response.usage_metadata,
            "status": "incomplete"
            if response.response_metadata.get("finish_reason") == "length"
            else "completed",
            "returned_model": response.response_metadata.get("model_name"),
            "response_id": response.id,
        }

    async def _responses(self, messages, tools, *, tool_choice=None):
        items = []
        for message in messages:
            if "provider_items" in message:
                items.extend(message["provider_items"])
            elif message["role"] == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message["tool_call_id"],
                        "output": message["content"],
                    }
                )
            elif message.get("tool_calls"):
                if message.get("content"):
                    items.append({"role": "assistant", "content": message["content"]})
                items.extend(
                    {
                        "type": "function_call",
                        "call_id": call["id"],
                        "name": call["function"]["name"],
                        "arguments": call["function"]["arguments"],
                    }
                    for call in message["tool_calls"]
                )
            else:
                items.append({"role": message["role"], "content": message["content"]})
        options = {
            "model": self.profile.model_id,
            "input": items,
            "tools": [{"type": "function", **tool["function"]} for tool in tools],
            "store": False,
            "max_output_tokens": self.profile.max_output_tokens,
            "include": ["reasoning.encrypted_content"],
        }
        if self.profile.reasoning_effort is not None:
            options["reasoning"] = {"effort": self.profile.reasoning_effort}
        if tool_choice:
            options["tool_choice"] = tool_choice
        response = await self.responses_client.responses.create(**options)
        # Output items are replayed as input, and the API refuses what it would not send:
        # the SDK's attribute name `async_` instead of `async`, and null fields such as a
        # reasoning item's `status`.
        raw = (
            response.model_dump(mode="json", by_alias=True, exclude_none=True)
            if hasattr(response, "model_dump")
            else response
        )
        output = raw.get("output", [])
        usage = raw.get("usage")
        if usage is not None:
            usage = {
                **{
                    key: usage[key]
                    for key in ("input_tokens", "output_tokens", "total_tokens")
                    if key in usage
                },
                "input_token_details": {
                    "cache_read": (usage.get("input_tokens_details") or {}).get("cached_tokens")
                },
                "output_token_details": {
                    "reasoning": (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
                },
            }
        return {
            "content": "".join(
                part.get("text", "")
                for item in output
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            ),
            "tool_calls": [
                {
                    "type": "function",
                    "id": item["call_id"],
                    "function": {"name": item["name"], "arguments": item["arguments"]},
                }
                for item in output
                if item.get("type") == "function_call"
            ],
            "provider_items": output,
            "status": raw.get("status", "unknown"),
            "incomplete_details": raw.get("incomplete_details"),
            "usage": usage,
            "returned_model": raw.get("model"),
            "response_id": raw.get("id"),
        }
