from typing import Literal, Protocol

from .contracts import Candidate, SearchRequest


class EmbeddingPort(Protocol):
    async def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["query", "document"],
        profile: dict,
        deadline_ms: int,
    ) -> list[list[float]]: ...


class IndexPort(Protocol):
    async def upsert(self, generation_id: str, chunks: list[dict]) -> None: ...
    async def search(self, request: SearchRequest) -> list[Candidate]: ...
    async def verify_generation(self, generation_id: str, chunks: list[dict]) -> bool: ...
    async def delete_generation(self, generation_id: str) -> None: ...


class BlobPort(Protocol):
    async def put(self, key: str, data: bytes, sha256: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
