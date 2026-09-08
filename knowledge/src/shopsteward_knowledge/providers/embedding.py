import asyncio
import hashlib
import json
import math
import time

import httpx

from ..contracts import EmbeddingProfile, validate_vectors


class HttpEmbedding:
    """OpenAI-compatible dense endpoint, with explicit profile and bounded retries."""

    def __init__(self, client: httpx.AsyncClient, url: str, api_key: str):
        self.client, self.url, self.api_key = client, url, api_key
        self.cache: dict[str, list[float]] = {}
        self.usage = {"requests": 0, "input_texts": 0, "reported_tokens": 0}

    async def embed(self, texts, *, input_type, profile, deadline_ms):
        profile = EmbeddingProfile.model_validate(profile)
        if input_type not in {"query", "document"}:
            raise ValueError("invalid embedding input type")
        if not self.api_key:
            raise ValueError("embedding provider disabled")
        if not texts:
            return []
        if len(texts) > 64 or any(
            not text or len(text) > profile.max_input_chars for text in texts
        ):
            raise ValueError("embedding input budget exceeded")
        keys = [
            hashlib.sha256(
                json.dumps(
                    [self.url, profile.model_dump(), input_type, text],
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            for text in texts
        ]
        missing = list(dict.fromkeys(key for key in keys if key not in self.cache))
        if missing:
            values = {key: text for key, text in zip(keys, texts, strict=True)}
            instruction = (
                profile.query_instruction if input_type == "query" else profile.document_instruction
            )
            payload = {
                "model": profile.model,
                "dimensions": profile.dimensions,
                "input": [instruction + values[key] for key in missing],
            }
            deadline = time.monotonic() + deadline_ms / 1000
            async with asyncio.timeout(deadline_ms / 1000):
                for attempt in range(3):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("embedding deadline")
                    response = await self.client.post(
                        self.url,
                        json=payload,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        timeout=remaining,
                    )
                    self.usage["requests"] += 1
                    if response.status_code not in {429, 502, 503, 504} or attempt == 2:
                        response.raise_for_status()
                        break
                    try:
                        delay = max(0.0, min(float(response.headers.get("Retry-After", 0.2)), 2.0))
                    except ValueError:
                        delay = 0.2
                    await asyncio.sleep(delay)
            body = response.json()
            items = body["data"]
            if sorted(item["index"] for item in items) != list(range(len(missing))):
                raise ValueError("embedding response indexes invalid")
            vectors = [item["embedding"] for item in sorted(items, key=lambda item: item["index"])]
            validate_vectors(vectors, len(missing), profile.dimensions)
            if profile.normalize:
                vectors = [
                    [v / math.sqrt(sum(x * x for x in vector)) for v in vector]
                    for vector in vectors
                ]
            if len(self.cache) + len(missing) > 10000:
                self.cache.clear()
            self.cache.update(zip(missing, vectors, strict=True))
            self.usage["input_texts"] += len(missing)
            self.usage["reported_tokens"] += body.get("usage", {}).get("total_tokens", 0)
        return [list(self.cache[key]) for key in keys]
