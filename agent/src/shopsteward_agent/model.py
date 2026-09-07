"""Explicit Chat Completions adapter, no provider detection or global settings."""

import json
from pathlib import Path

from langchain_openai import ChatOpenAI


class OpenAIModel:
    def __init__(self, *, base_url, model, key=None, key_file=None, client=None):
        if client is None:
            if key is not None and key_file is not None:
                raise ValueError("choose key or key_file")
            if key_file is not None:
                key = Path(key_file).read_text(encoding="utf-8").strip()
            if not key:
                raise ValueError("model key required")
            client = ChatOpenAI(
                base_url=base_url,
                model=model,
                api_key=key,
                timeout=30,
                max_retries=0,
                use_responses_api=False,
                max_completion_tokens=2048,
            )
        self.client = client

    async def complete(self, messages, tools, *, tool_choice=None):
        options = {"tool_choice": tool_choice} if tool_choice else {}
        response = await self.client.bind_tools(tools, **options).ainvoke(messages)
        return {
            "content": response.content,
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
        }
