"""Pure publication guards shared by the durable ingestion/worker paths."""

import hashlib
import json

from .contracts import OriginalRef


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def projection_decision(existing: dict | None, incoming: dict) -> str:
    if existing is None or incoming["metadata_revision"] > existing["metadata_revision"]:
        return "apply"
    if incoming["metadata_revision"] < existing["metadata_revision"]:
        return "stale"
    if incoming["payload_hash"] != existing["payload_hash"]:
        raise ValueError("equal projection revision has different payload")
    return "replay"


def verify_original(ref: OriginalRef, content: bytes) -> None:
    if len(content) != ref.size_bytes:
        raise ValueError("original size mismatch")
    if hashlib.sha256(content).hexdigest() != ref.sha256:
        raise ValueError("original SHA-256 mismatch")


def manifest_hash(chunks: list[dict]) -> str:
    ids = [item["chunk_id"] for item in chunks]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("manifest requires nonempty, unique chunks")
    return payload_hash({"chunks": sorted(chunks, key=lambda item: item["chunk_id"])})


def retry_delay(attempt: int, retry_after: float | None = None) -> float:
    delay = min(60, 2 ** max(0, min(attempt - 1, 6)))
    return min(60, max(delay, retry_after or 0))


def retry_attempt_limit(attempt: int, window: int, total: int) -> int:
    if not 0 <= attempt < total:
        raise ValueError("total retry attempt budget exhausted")
    if window < 1:
        raise ValueError("retry attempt window must be positive")
    return min(attempt + window, total)
