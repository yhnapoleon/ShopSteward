"""Whole, separately located parent evidence from immutable PostgreSQL chunks."""

from datetime import UTC, datetime

from sqlalchemy import func, tuple_

from ..contracts import Candidate, SearchScope
from ..db import overlay_candidate, scope_query, visible_projection
from ..models import Chunk, IndexGeneration


def _limits(radius, max_chars):
    if type(radius) is not int or not 0 <= radius <= 4:
        raise ValueError("parent radius must be between zero and four")
    if type(max_chars) is not int or not 1 <= max_chars <= 24000:
        raise ValueError("parent character budget must be between one and 24000")


def _allowed(candidate, scope):
    return (
        scope.expires_at > datetime.now(UTC)
        and candidate.store_id == scope.store_id
        and any(
            (candidate.version_id, candidate.generation_id, candidate.metadata_revision)
            == (v.version_id, v.generation_id, v.metadata_revision)
            for v in scope.allowed_versions
        )
        and (candidate.valid_from is None or candidate.valid_from <= scope.as_of)
        and (candidate.valid_until is None or scope.as_of < candidate.valid_until)
    )


def _key(payload):
    ordinal = payload.get("ordinal")
    source = payload.get("source_ordinal", ordinal)
    if type(source) is not int or source < 0 or type(ordinal) is not int or ordinal < 0:
        raise ValueError("parent chunks require nonnegative source and chunk ordinals")
    return source, ordinal, payload["chunk_id"]


def _candidate(payload):
    return Candidate.model_validate(
        {k: v for k, v in payload.items() if k in Candidate.model_fields}
    )


def select_parent_candidates(hit, anchor, neighbours, scope, *, radius=2, max_chars=6000):
    """Select nearby whole evidence; never concatenate text under the hit's locator.

    The caller supplies an authorized current projection. An oversized hit is kept
    intact, with no additional context. Neither the hit nor input payloads are mutated.
    """
    _limits(radius, max_chars)
    if (
        not _allowed(hit, scope)
        or not isinstance(anchor.get("parent_id"), str)
        or not anchor["parent_id"]
    ):
        return []
    try:
        source = _candidate(anchor)
        anchor_key = _key(anchor)
    except (ValueError, KeyError, TypeError):
        return []
    identity = (
        "document_id",
        "version_id",
        "generation_id",
        "metadata_revision",
        "store_id",
        "original_sha256",
    )
    if (
        any(getattr(source, field) != getattr(hit, field) for field in (*identity, "chunk_id"))
        or not _allowed(source, scope)
        or (source.text, source.content_sha256, source.locator)
        != (hit.text, hit.content_sha256, hit.locator)
    ):
        return []
    siblings = {}
    for payload in neighbours:
        if payload.get("parent_id") != anchor["parent_id"]:
            continue
        if any(payload.get(field) != anchor.get(field) for field in identity):
            continue
        try:
            item = _candidate(payload)
            key = _key(payload)
        except (ValueError, KeyError, TypeError):
            continue
        if item.chunk_id == hit.chunk_id or not _allowed(item, scope):
            continue
        siblings[item.chunk_id] = (key, item)
    before = sorted((pair for pair in siblings.values() if pair[0] < anchor_key), reverse=True)[
        :radius
    ]
    after = sorted(pair for pair in siblings.values() if pair[0] > anchor_key)[:radius]
    selected = [(anchor_key, hit.model_copy(deep=True))]
    used = len(hit.text)
    # Prefer the immediate predecessor, then successor, then the next pair.
    for distance in range(radius):
        for side in (before, after):
            if distance < len(side):
                key, item = side[distance]
                if used + len(item.text) <= max_chars:
                    selected.append((key, item))
                    used += len(item.text)
    return [item for _, item in sorted(selected, key=lambda pair: pair[0])]


class PGParentExpander:
    def __init__(self, session_factory, *, radius=2, max_chars=6000):
        _limits(radius, max_chars)
        self.session_factory = session_factory
        self.radius, self.max_chars = radius, max_chars

    @staticmethod
    def _payload(row, scope):
        if row is None:
            return None
        projection, generation, chunk = row
        if not visible_projection(projection.payload, scope):
            return None
        expected = {
            "version_id": projection.version_id,
            "generation_id": generation.id,
            "store_id": projection.store_id,
            "metadata_revision": projection.metadata_revision,
            "chunk_id": chunk.chunk_id,
            "content_sha256": chunk.content_sha256,
            "document_id": projection.document_id,
        }
        if any(chunk.payload.get(field) != value for field, value in expected.items()):
            return None
        return {
            **chunk.payload,
            **overlay_candidate(chunk.payload, projection.payload).model_dump(mode="json"),
        }

    async def expand(self, candidate: Candidate, scope: SearchScope) -> list[Candidate]:
        if not _allowed(candidate, scope):
            return []
        narrow_scope = scope.model_copy(
            update={
                "allowed_versions": [
                    v
                    for v in scope.allowed_versions
                    if (v.version_id, v.generation_id, v.metadata_revision)
                    == (candidate.version_id, candidate.generation_id, candidate.metadata_revision)
                ]
            }
        )
        base = (
            scope_query(narrow_scope)
            .add_columns(Chunk)
            .join(Chunk, Chunk.generation_id == IndexGeneration.id)
            .where(
                Chunk.version_id == candidate.version_id,
                Chunk.generation_id == candidate.generation_id,
                Chunk.metadata_revision == candidate.metadata_revision,
                Chunk.store_id == candidate.store_id,
            )
        )
        anchor_query = base.where(Chunk.chunk_id == candidate.chunk_id)
        async with self.session_factory() as session:
            anchor = self._payload((await session.execute(anchor_query)).one_or_none(), scope)
            if anchor is None or not select_parent_candidates(
                candidate, anchor, [], scope, radius=0, max_chars=self.max_chars
            ):
                return []
            ordinal = Chunk.payload["ordinal"].as_integer()
            source = func.coalesce(Chunk.payload["source_ordinal"].as_integer(), ordinal)
            key = tuple_(source, ordinal, Chunk.chunk_id)
            anchor_key = _key(anchor)
            siblings = base.where(Chunk.payload["parent_id"].as_string() == anchor["parent_id"])
            neighbours = []
            if self.radius:
                for query in (
                    siblings.where(key < anchor_key)
                    .order_by(source.desc(), ordinal.desc(), Chunk.chunk_id.desc())
                    .limit(self.radius),
                    siblings.where(key > anchor_key)
                    .order_by(source, ordinal, Chunk.chunk_id)
                    .limit(self.radius),
                ):
                    for row in (await session.execute(query)).all():
                        payload = self._payload(row, scope)
                        if payload is not None:
                            neighbours.append(payload)
            # Metadata may change while the two windows are being read. Never return
            # context if the exact hit is no longer authorized by the current projection.
            current = self._payload((await session.execute(anchor_query)).one_or_none(), scope)
            if current is None:
                return []
            return select_parent_candidates(
                candidate, current, neighbours, scope, radius=self.radius, max_chars=self.max_chars
            )
