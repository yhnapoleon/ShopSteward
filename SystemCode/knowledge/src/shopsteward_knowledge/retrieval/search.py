import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import Candidate, EmbeddingProfile, RelationPath, SearchResponse
from .fusion import rrf


async def measure(timings, name, operation):
    started = time.monotonic()
    try:
        return await operation
    finally:
        timings[name] = round(timings.get(name, 0) + (time.monotonic() - started) * 1000, 3)


def allowed(candidate, scope):
    versions = {
        (v.version_id, v.generation_id, v.metadata_revision) for v in scope.allowed_versions
    }
    return (
        candidate.store_id == scope.store_id
        and (candidate.version_id, candidate.generation_id, candidate.metadata_revision) in versions
        and (candidate.valid_from is None or candidate.valid_from <= scope.as_of)
        and (candidate.valid_until is None or scope.as_of < candidate.valid_until)
    )


def profile_key(profile):
    canonical = EmbeddingProfile.model_validate(profile).model_dump(mode="json")
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


class SearchService:
    def __init__(
        self,
        index,
        *,
        evidence_loader=None,
        scope_filter=None,
        embedder=None,
        embedding_profile=None,
        parent_expander=None,
        relation_loader=None,
        reranker=None,
    ):
        self.index = index
        self.evidence_loader, self.scope_filter = evidence_loader, scope_filter
        self.embedder = embedder
        self.embedding_profile = (
            EmbeddingProfile.model_validate(embedding_profile).model_dump(mode="json")
            if embedding_profile
            else None
        )
        self.parent_expander, self.relation_loader = parent_expander, relation_loader
        self.reranker = reranker

    async def _scope(self, scope):
        if scope.expires_at <= datetime.now(UTC):
            raise ValueError("search scope expired")
        return await self.scope_filter(scope) if self.scope_filter else scope

    async def _dense(self, request, timings):
        profile = EmbeddingProfile.model_validate(self.embedding_profile).model_dump()
        vectors = await measure(
            timings,
            "query_embedding",
            self.embedder.embed(
                [request.query],
                input_type="query",
                profile=profile,
                deadline_ms=request.deadline_ms,
            ),
        )
        return await measure(
            timings, "dense_index", self.index.dense(request, vectors[0], profile_key(profile))
        )

    async def _relations(self, request, warnings):
        paths = await self.relation_loader(
            request.entity_ids,
            [
                "APPLIES_TO",
                "REQUIRES_EVIDENCE",
                "SUPERSEDES",
                "SUBSTITUTES",
                "COMPATIBLE_WITH",
                "SUPPLIES",
                "HAS_APPLICABLE_DOCUMENT",
            ],
            request.scope,
            context=request.relation_context,
        )
        if getattr(paths, "truncated", False):
            warnings.append("relations_truncated")
        accepted, ids = [], set()
        for raw in paths:
            path = RelationPath.model_validate(raw)
            proposed = ids | set(path.evidence_chunk_ids)
            if len(proposed) > 20:
                warnings.append("relations_truncated")
                continue
            accepted.append(path)
            ids = proposed
        if not ids:
            return []
        values = await self.evidence_loader(request.scope, sorted(ids))
        evidence = {
            c.chunk_id: c
            for c in map(Candidate.model_validate, values)
            if c.chunk_id in ids and allowed(c, request.scope)
        }
        for path in accepted:
            if not all(
                identifier in evidence
                and (
                    evidence[identifier].version_id,
                    evidence[identifier].generation_id,
                    evidence[identifier].metadata_revision,
                )
                == (edge.version_id, edge.generation_id, edge.metadata_revision)
                for edge in path.edges
                for identifier in edge.evidence_chunk_ids
            ):
                continue
            for identifier in path.evidence_chunk_ids:
                if len(evidence[identifier].relation_paths) < 20:
                    evidence[identifier].relation_paths.append(path)
        return [c for c in evidence.values() if c.relation_paths]

    async def search(self, request):
        started = time.monotonic()
        tasks = {}
        warnings, timings = [], {}
        scope = request.scope
        lists = {}
        try:
            # Reserve part of the tool budget for final projection checks and serialization.
            async with asyncio.timeout(request.deadline_ms / 1000 * 0.85):
                scope = await measure(timings, "initial_scope", self._scope(request.scope))
                request = request.model_copy(update={"scope": scope})
                if scope.allowed_versions:
                    tasks["lexical"] = asyncio.create_task(
                        measure(timings, "lexical", self.index.search(request))
                    )
                    if request.entity_ids and self.relation_loader and self.evidence_loader:
                        tasks["relations"] = asyncio.create_task(
                            measure(timings, "relations", self._relations(request, warnings))
                        )
                    if request.profile_id != "lexical-v1":
                        if self.embedder is not None and self.embedding_profile:
                            tasks["dense"] = asyncio.create_task(self._dense(request, timings))
                        else:
                            warnings.append("dense_disabled")
                    # Shield lets the outer timeout retain a completed lexical result.
                    await asyncio.shield(asyncio.gather(*tasks.values(), return_exceptions=True))
        except TimeoutError:
            warnings.append("retrieval_deadline")
        finally:
            for channel, task in tasks.items():
                if not task.done():
                    task.cancel()
                    warnings.append(channel + "_timeout")
                elif task.cancelled() or task.exception() is not None:
                    warnings.append(channel + "_unavailable")
                else:
                    lists[channel] = [Candidate.model_validate(c) for c in task.result()]
            if tasks:
                await asyncio.gather(*tasks.values(), return_exceptions=True)
        candidates = {}
        rankings = []
        for channel, values in lists.items():
            visible = [c for c in values if allowed(c, scope)]
            rankings.append([c.chunk_id for c in visible])
            for rank, c in enumerate(visible, 1):
                if c.chunk_id not in candidates:
                    candidates[c.chunk_id] = c.model_copy(deep=True)
                merged = candidates[c.chunk_id]
                merged.ranks[channel] = rank
                merged.scores.update(c.scores)
                if channel == "relations":
                    merged.relation_paths = c.relation_paths
                merged.retrieval_channels = sorted(set(merged.retrieval_channels) | {channel})
        ranked = []
        for identifier, score in rrf(rankings):
            candidates[identifier].fusion_score = score
            ranked.append(candidates[identifier])
        if request.profile_id != "lexical-v1" and self.reranker and ranked:
            remaining = request.deadline_ms / 1000 * 0.85 - (time.monotonic() - started)
            try:
                async with asyncio.timeout(max(0, remaining)):
                    pool = ranked[:30]
                    reranked = await measure(
                        timings,
                        "rerank",
                        self.reranker.rerank(
                            request.query, pool, deadline_ms=max(1, int(remaining * 1000))
                        ),
                    )
                    by_id = {c.chunk_id: c for c in pool}
                    if len(reranked) != len(pool) or {c.chunk_id for c in reranked} != set(by_id):
                        raise ValueError("rerank changed candidate identities")
                    ordered = []
                    for value in reranked:
                        item = by_id[value.chunk_id].model_copy(deep=True)
                        item.rerank_score = value.rerank_score
                        ordered.append(item)
                    ranked = ordered + ranked[30:]
            except TimeoutError:
                warnings.append("rerank_timeout")
            except Exception:
                warnings.append("rerank_unavailable")
        chosen, remaining_chars = [], 12000
        for item in ranked:
            if len(chosen) >= request.limit or remaining_chars <= 0:
                break
            if len(item.text) > remaining_chars:
                item.text = item.text[:remaining_chars]
                item.content_sha256 = hashlib.sha256(item.text.encode()).hexdigest()
                item.truncated = True
            remaining_chars -= len(item.text)
            chosen.append(item)
        if self.parent_expander and chosen:
            remaining = request.deadline_ms / 1000 * 0.85 - (time.monotonic() - started)
            try:
                async with asyncio.timeout(max(0, remaining)):
                    existing = {c.chunk_id for c in chosen}
                    for hit in list(chosen):
                        for raw in await measure(
                            timings, "parent", self.parent_expander(hit, scope)
                        ):
                            neighbour = Candidate.model_validate(raw)
                            if (
                                not allowed(neighbour, scope)
                                or neighbour.chunk_id in existing
                                or len(chosen) >= request.limit
                                or len(neighbour.text) > remaining_chars
                            ):
                                continue
                            neighbour.retrieval_channels = ["parent"]
                            hit.context_chunk_ids.append(neighbour.chunk_id)
                            chosen.append(neighbour)
                            existing.add(neighbour.chunk_id)
                            remaining_chars -= len(neighbour.text)
            except TimeoutError:
                warnings.append("parent_timeout")
            except Exception:
                warnings.append("parent_unavailable")
        # Recheck projection after asynchronous retrieval; the backend rechecks authority again.
        remaining = request.deadline_ms / 1000 - (time.monotonic() - started)
        try:
            async with asyncio.timeout(max(0, remaining)):
                scope = await measure(timings, "final_scope", self._scope(scope))
            chosen = [c for c in chosen if allowed(c, scope)]
            authorities = {
                (v.version_id, v.generation_id, v.metadata_revision) for v in scope.allowed_versions
            }
            selected = {c.chunk_id for c in chosen}
            for hit in chosen:
                hit.relation_paths = [
                    p
                    for p in hit.relation_paths
                    if all(
                        (e.version_id, e.generation_id, e.metadata_revision) in authorities
                        for e in p.edges
                    )
                ]
                hit.context_chunk_ids = [i for i in hit.context_chunk_ids if i in selected]
        except TimeoutError:
            chosen = []
            warnings.append("final_scope_deadline")
        timings["total"] = round((time.monotonic() - started) * 1000, 3)
        return SearchResponse(
            request_id=str(uuid4()),
            retrieval_profile=request.profile_id,
            embedding_profile=profile_key(self.embedding_profile)
            if self.embedding_profile and request.profile_id != "lexical-v1"
            else None,
            rerank_profile=getattr(self.reranker, "model", None)
            if request.profile_id != "lexical-v1"
            else None,
            index_watermark={v.version_id: v.metadata_revision for v in scope.allowed_versions},
            timings_ms=timings,
            warnings=sorted(set(warnings + ["context_budget_chars_12000_estimate"])),
            degraded=bool(warnings),
            candidates=chosen,
        )

    async def evidence(self, request):
        async with asyncio.timeout(8):
            scope = await self._scope(request.scope)
            if not scope.allowed_versions:
                values = []
            elif self.evidence_loader is None:
                raise RuntimeError("evidence loader not configured")
            else:
                values = await self.evidence_loader(scope, request.chunk_ids)
                values = [Candidate.model_validate(value) for value in values]
            scope = await self._scope(scope)
        return SearchResponse(
            request_id=str(uuid4()),
            retrieval_profile="evidence-v1",
            candidates=[c for c in values if c.chunk_id in request.chunk_ids and allowed(c, scope)],
        )
