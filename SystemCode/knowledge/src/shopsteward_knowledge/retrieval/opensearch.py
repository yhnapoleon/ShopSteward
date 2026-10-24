"""HTTP OpenSearch adapter. Generation IDs never become unchecked URL paths."""

import hashlib
import json
import re

import httpx

from ..contracts import Candidate, SearchRequest, validate_vectors


def complete_response(body):
    if body.get("timed_out") or body.get("_shards", {}).get("failed", 0):
        raise RuntimeError("search returned incomplete shard results")
    return body


def authority_key(value):
    return hashlib.sha256(
        json.dumps([value.version_id, value.generation_id, value.metadata_revision]).encode()
    ).hexdigest()


def storage_id(generation_id, chunk_id):
    return hashlib.sha256(json.dumps([generation_id, chunk_id]).encode()).hexdigest()


def scope_filters(request: SearchRequest):
    scope = request.scope
    filters = [
        {"term": {"store_id": scope.store_id}},
        {"terms": {"authority_key": [authority_key(v) for v in scope.allowed_versions]}},
    ]
    for field, operator in (("valid_from", "lte"), ("valid_until", "gt")):
        filters.append(
            {
                "bool": {
                    "should": [
                        {"bool": {"must_not": [{"exists": {"field": field}}]}},
                        {"range": {field: {operator: scope.as_of.isoformat()}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if request.entity_ids:
        filters.append({"terms": {"entity_refs": request.entity_ids}})
    return filters


def build_query(request: SearchRequest):
    if not request.scope.allowed_versions:
        return {"size": 0, "query": {"match_none": {}}}
    return {
        "size": 50,
        "_source": ["candidate"],
        "query": {
            "bool": {
                "filter": scope_filters(request),
                "should": [{"match": {"text": request.query}}],
                "minimum_should_match": 1,
            }
        },
    }


class OpenSearchIndex:
    def __init__(self, client: httpx.AsyncClient, url: str, prefix: str):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,50}", prefix):
            raise ValueError("invalid index prefix")
        self.client, self.url, self.prefix = client, url.rstrip("/"), prefix

    def index_name(self, generation_id=None, *, embedding_profile=None):
        # Index count follows model spaces, not document or generation count.
        if embedding_profile is None:
            return self.prefix + "-lexical-v1"
        if not re.fullmatch(r"[0-9a-f]{64}", embedding_profile):
            raise ValueError("canonical embedding profile hash required")
        return self.prefix + "-dense-" + embedding_profile

    @property
    def all_indexes(self):
        return self.prefix + "-*"

    async def ready(self):
        response = await self.client.get(self.url + "/_cluster/health", timeout=3)
        response.raise_for_status()
        return response.json().get("status") != "red"

    async def upsert(self, generation_id: str, chunks: list[dict]):
        if not chunks:
            return
        candidates = [
            Candidate.model_validate(row.get("candidate", row))
            if "vector" not in row or "candidate" in row
            else Candidate.model_validate(
                {k: v for k, v in row.items() if k not in {"vector", "embedding_profile"}}
            )
            for row in chunks
        ]
        if any(c.generation_id != generation_id for c in candidates):
            raise ValueError("generation mismatch")
        vectors = [row.get("vector") for row in chunks]
        dimensions = len(vectors[0]) if vectors[0] is not None else None
        profiles = {row.get("embedding_profile") for row in chunks}
        if len(profiles) != 1 or (vectors[0] is not None and not next(iter(profiles))):
            raise ValueError("mixed or missing embedding profile")
        name = self.index_name(embedding_profile=next(iter(profiles)) if dimensions else None)
        if any((v is None) != (dimensions is None) for v in vectors):
            raise ValueError("mixed vector presence")
        if dimensions:
            validate_vectors(vectors, len(vectors), dimensions)
        properties = {
            field: {"type": "keyword"}
            for field in (
                "document_id",
                "chunk_id",
                "version_id",
                "generation_id",
                "store_id",
                "entity_refs",
                "embedding_profile",
                "authority_key",
            )
        }
        properties.update(
            {
                "text": {"type": "text", "analyzer": "cjk"},
                "metadata_revision": {"type": "long"},
                "valid_from": {"type": "date"},
                "valid_until": {"type": "date"},
                "candidate": {"type": "object", "enabled": False},
            }
        )
        settings = {"number_of_shards": 1, "number_of_replicas": 0}
        if dimensions:
            settings["index.knn"] = True
            properties["vector"] = {
                "type": "knn_vector",
                "dimension": dimensions,
                "method": {"name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"},
            }
        response = await self.client.put(
            f"{self.url}/{name}",
            json={
                "settings": settings,
                "mappings": {"dynamic": "strict", "properties": properties},
            },
        )
        if response.status_code == 400:
            if response.json().get("error", {}).get("type") != "resource_already_exists_exception":
                response.raise_for_status()
        else:
            response.raise_for_status()
        lines = []
        for row, candidate, vector in zip(chunks, candidates, vectors, strict=True):
            data = candidate.model_dump(mode="json")
            source = {
                field: data[field]
                for field in (
                    "document_id",
                    "chunk_id",
                    "version_id",
                    "generation_id",
                    "store_id",
                    "metadata_revision",
                    "valid_from",
                    "valid_until",
                    "entity_refs",
                    "text",
                )
            }
            source["candidate"] = data
            source["authority_key"] = authority_key(candidate)
            if vector is not None:
                source.update(vector=vector, embedding_profile=row.get("embedding_profile", ""))
            lines.extend(
                [
                    json.dumps(
                        {
                            "index": {
                                "_index": name,
                                "_id": storage_id(generation_id, candidate.chunk_id),
                            }
                        }
                    ),
                    json.dumps(source, ensure_ascii=False),
                ]
            )
        response = await self.client.post(
            self.url + "/_bulk?refresh=wait_for",
            content=("\n".join(lines) + "\n").encode(),
            headers={"Content-Type": "application/x-ndjson"},
            timeout=60,
        )
        response.raise_for_status()
        if response.json().get("errors"):
            raise RuntimeError("search bulk indexing failed")

    async def count(self, generation_id):
        response = await self.client.post(
            f"{self.url}/{self.all_indexes}/_count",
            json={"query": {"term": {"generation_id": generation_id}}},
        )
        if response.status_code == 404:
            return 0
        response.raise_for_status()
        return complete_response(response.json())["count"]

    async def verify_generation(self, generation_id, chunks):
        expected = {}
        for row in chunks:
            raw = row.get("candidate", row)
            candidate = Candidate.model_validate(
                {key: value for key, value in raw.items() if key in Candidate.model_fields}
            )
            if (
                candidate.generation_id != generation_id
                or storage_id(generation_id, candidate.chunk_id) in expected
            ):
                return False
            expected[storage_id(generation_id, candidate.chunk_id)] = candidate.model_dump(
                mode="json"
            )
        if not expected or await self.count(generation_id) != len(expected):
            return False
        identifiers = list(expected)
        for offset in range(0, len(identifiers), 1000):
            batch = identifiers[offset : offset + 1000]
            response = await self.client.post(
                f"{self.url}/{self.all_indexes}/_search?allow_partial_search_results=false",
                json={
                    "size": len(batch),
                    "query": {"ids": {"values": batch}},
                    "_source": ["candidate"],
                },
                timeout=10,
            )
            response.raise_for_status()
            hits = complete_response(response.json())["hits"]["hits"]
            if {hit["_id"] for hit in hits} != set(batch):
                return False
            if any(hit["_source"]["candidate"] != expected[hit["_id"]] for hit in hits):
                return False
        return True

    async def search(self, request):
        if not request.scope.allowed_versions:
            return []
        return await self._search(request, build_query(request), "lexical")

    async def dense(self, request, vector, profile_id):
        if not request.scope.allowed_versions:
            return []
        filters = scope_filters(request) + [{"term": {"embedding_profile": profile_id}}]
        body = {
            "size": 50,
            "_source": ["candidate"],
            "query": {
                "knn": {
                    "vector": {"vector": vector, "k": 50, "filter": {"bool": {"filter": filters}}}
                }
            },
        }
        return await self._search(
            request, body, "dense", names=self.index_name(embedding_profile=profile_id)
        )

    async def _search(self, request, body, channel, *, names=None):
        names = names or self.all_indexes
        body = body | {"sort": [{"_score": "desc"}, {"chunk_id": "asc"}, {"generation_id": "asc"}]}
        response = await self.client.post(
            f"{self.url}/{names}/_search?allow_partial_search_results=false",
            json=body,
            timeout=request.deadline_ms / 1000,
        )
        response.raise_for_status()
        result = []
        hits = complete_response(response.json())["hits"]["hits"]
        hits.sort(
            key=lambda hit: (
                -(hit.get("_score") or 0),
                hit["_source"]["candidate"]["chunk_id"],
                hit["_source"]["candidate"]["generation_id"],
            )
        )
        for rank, hit in enumerate(hits, 1):
            candidate = Candidate.model_validate(hit["_source"]["candidate"])
            candidate.retrieval_channels = [channel]
            candidate.ranks[channel] = rank
            candidate.scores[channel] = float(hit.get("_score") or 0)
            result.append(candidate)
        return result

    async def delete_generation(self, generation_id):
        response = await self.client.post(
            f"{self.url}/{self.all_indexes}/_delete_by_query?refresh=true",
            json={"query": {"term": {"generation_id": generation_id}}},
            timeout=60,
        )
        if response.status_code == 404:
            return
        response.raise_for_status()
        body = complete_response(response.json())
        if body.get("failures") or body.get("version_conflicts"):
            raise RuntimeError("generation deletion was incomplete")
