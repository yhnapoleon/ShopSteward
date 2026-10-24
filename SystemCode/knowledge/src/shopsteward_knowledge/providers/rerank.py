"""Optional explicit HTTP rerank protocol; remote output can assign scores only."""

import asyncio
import math

from ..contracts import Candidate


class HttpRerank:
    def __init__(self, client, url, api_key, model):
        if not url or not api_key or not model:
            raise ValueError("explicit rerank URL, key and model required")
        self.client, self.url, self.api_key, self.model = client, url, api_key, model
        self.requests = 0
        self.input_characters = 0

    async def rerank(self, query, candidates, *, deadline_ms):
        if not 1 <= len(candidates) <= 30 or not 1 <= deadline_ms <= 8000:
            raise ValueError("rerank candidate or deadline budget exceeded")
        values = [Candidate.model_validate(c).model_copy(deep=True) for c in candidates]
        if not query or len(query) > 4000 or sum(len(c.text) for c in values) > 60000:
            raise ValueError("rerank input budget exceeded")
        async with asyncio.timeout(deadline_ms / 1000):
            self.requests += 1
            self.input_characters += len(query) + sum(len(c.text) for c in values)
            response = await self.client.post(
                self.url,
                headers={"Authorization": "Bearer " + self.api_key},
                json={
                    "model": self.model,
                    "query": query,
                    "documents": [c.text for c in values],
                    "top_n": len(values),
                },
                timeout=deadline_ms / 1000,
            )
            response.raise_for_status()
        results = response.json().get("results")
        if not isinstance(results, list) or len(results) != len(values):
            raise ValueError("rerank result count differs")
        seen = set()
        for result in results:
            index, score = result.get("index"), result.get("relevance_score")
            if (
                type(index) is not int
                or not 0 <= index < len(values)
                or index in seen
                or type(score) not in (int, float)
                or not math.isfinite(score)
            ):
                raise ValueError("invalid rerank index or score")
            seen.add(index)
            values[index].rerank_score = float(score)
        return sorted(values, key=lambda c: (-c.rerank_score, c.chunk_id, c.generation_id))
