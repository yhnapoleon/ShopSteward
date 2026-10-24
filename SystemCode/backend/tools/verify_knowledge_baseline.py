"""K0 read-only RAilG audit and disposable OpenSearch experiments.

Run with the isolated K0 environment, not the application environment. Does not
load RAilG settings, credentials, or production data. No model calls are made.
Only creates/deletes its own random shopsteward_k0_* indices on a loopback URL.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def audit_source(source):
    rules = {
        "ingest/extractors/base.py": (
            "Retain markdown contract; add parse status and stable locators."
        ),
        "ingest/extractors/office.py": (
            "Bound ZIP/XML; preserve sheet/range and formula state; never infer business amounts."
        ),
        "ingest/extractors/pdf.py": (
            "Retain low-text detection; require explicit partial/OCR status and page locators."
        ),
        "ingest/extractors/text_formats.py": (
            "Bound input; UTF-8 validation, CSV row/cell locators; no silent truncation."
        ),
        "ingest/extractors/layout.py": "Optional OCR adapter only after a measured layout failure.",
        "ingest/extractors/ocr_backends.py": (
            "Optional dependency; no automatic download or remote credentials."
        ),
        "ingest/chunker.py": (
            "Keep section/context/chunk idea; benchmark larger chunks and "
            "version-aware parent keys."
        ),
        "ingest/page.py": (
            "Keep table structure; verify table headers, original offsets, and lossless provenance."
        ),
        "schema/document.py": (
            "Adapt to store/document/version/index-profile IDs; fail-closed ACL; no path identity."
        ),
        "schema/mapping.py": (
            "Optional OpenSearch adapter; explicit store/version fields and tested dimensions."
        ),
        "retrieval/builder.py": (
            "Set minimum_should_match for scoring queries; include every "
            "ACL/version/exclusion inside vector filter."
        ),
        "retrieval/processors.py": (
            "Use server-owned scope; separate exact, lexical, and vector branches with RRF."
        ),
        "retrieval/service.py": (
            "Lazy optional embedding; absolute deadline; no model requirement for lexical search."
        ),
        "retrieval/parents.py": (
            "Reauthorize every parent fetch; document/version/profile key; bounded context budget."
        ),
        "providers/base.py": (
            "Keep small provider interfaces; dependency injection from ShopSteward."
        ),
        "providers/openai_compat.py": (
            "Validate dimension, token budget, batch ordering, retry deadline; keys "
            "from own config."
        ),
        "providers/tokens.py": (
            "Replace heuristic budgets with model-specific tokenization where available."
        ),
        "generation/attribution.py": (
            "Citation syntax checks only; similarity is not entailment or factual confidence."
        ),
        "generation/packer.py": (
            "Keep source packing idea; reuse existing Agent output, not RAilG chat stack."
        ),
        "evaluation/metrics.py": (
            "Add split/group, no-answer, ACL, document-version and evidence metrics."
        ),
    }
    head = git(source, "rev-parse", "HEAD")
    files = []
    for relative, adaptation in rules.items():
        path = source / "railg" / relative
        status = git(source, "status", "--porcelain", "--", "railg/" + relative)
        files.append(
            {
                "source_repo": "IH/railg",
                "source_commit": head,
                "dirty": bool(status),
                "source_path": "railg/" + relative,
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "destination_path": "backend/app/knowledge/railg_core/" + relative,
                "destination_status": "candidate_K2_plus_not_copied",
                "license": (
                    "repository MIT; preserve notice and verify upstream provenance before copying"
                ),
                "adaptation": adaptation,
            }
        )
    value = {
        "schema_version": 1,
        "audited_at": datetime.now(UTC).isoformat(),
        "source_commit": head,
        "source_worktree_dirty": bool(git(source, "status", "--porcelain")),
        "source_license_sha256": hashlib.sha256((source / "LICENSE").read_bytes()).hexdigest(),
        "files": files,
        "excluded": ["api.py", "auth.py", "sessions", "web", "ingest/pipeline.py", "config loader"],
        "other_IH_repositories": (
            "Design references only; repository-level license not established in "
            "prior audit. No code copied."
        ),
    }
    write_json(ROOT / "docs/research/2026-09-07-knowledge-reuse-manifest.json", value)
    return {"commit": head, "dirty": value["source_worktree_dirty"], "candidate_files": len(files)}


class Experiment:
    def __init__(self, url):
        parsed = urlparse(url)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.port != 19200:
            raise ValueError("K0 requires the dedicated loopback OpenSearch port 19200")
        self.client = httpx.Client(base_url=url, timeout=30, trust_env=False)
        self.indices = []

    def call(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def create(self, body, label):
        index = "shopsteward_k0_" + label + "_" + uuid.uuid4().hex[:12]
        self.call("PUT", "/" + index, json=body)
        self.indices.append(index)
        return index

    def put_many(self, index, records):
        lines = []
        for key, record in records:
            lines.extend(
                [json.dumps({"index": {"_id": key}}), json.dumps(record, ensure_ascii=False)]
            )
        if lines:
            result = self.call(
                "POST",
                f"/{index}/_bulk?refresh=true",
                content="\n".join(lines) + "\n",
                headers={"Content-Type": "application/x-ndjson"},
            )
            if result["errors"]:
                raise RuntimeError("K0 bulk indexing failed: " + json.dumps(result))

    def search(self, index, body):
        return self.call("POST", f"/{index}/_search", json=body)["hits"]["hits"]

    def close(self):
        try:
            for index in self.indices:
                self.call("DELETE", "/" + index)
        finally:
            self.client.close()


def protocol_probes(experiment):
    from railg.retrieval.builder import QueryBuilder
    from railg.schema.mapping import build_index_body, verify_contract

    verify_contract(4)
    body = build_index_body(4)
    body["mappings"]["properties"].update(
        {"store_id": {"type": "keyword"}, "version_id": {"type": "keyword"}}
    )
    index = experiment.create(body, "protocol")
    records = [
        (
            "east-current",
            {
                "store_id": "east",
                "version_id": "v2",
                "text_to_index": "冷链断电处理记录",
                "acl_principals": ["user:alice"],
                "semantic_vector": [1.0, 0.1, 0.0, 0.0],
            },
        ),
        (
            "east-old",
            {
                "store_id": "east",
                "version_id": "v1",
                "text_to_index": "冷链旧规定",
                "acl_principals": ["user:alice"],
                "semantic_vector": [1.0, 0.0, 0.0, 0.0],
            },
        ),
        (
            "west",
            {
                "store_id": "west",
                "version_id": "v2",
                "text_to_index": "冷链绝密西店",
                "acl_principals": ["user:alice"],
                "semantic_vector": [1.0, 0.0, 0.0, 0.0],
            },
        ),
        (
            "private-bob",
            {
                "store_id": "east",
                "version_id": "v2",
                "text_to_index": "冷链私有",
                "acl_principals": ["user:bob"],
                "semantic_vector": [1.0, 0.0, 0.0, 0.0],
            },
        ),
    ]
    experiment.put_many(index, records)

    def scoped():
        return (
            QueryBuilder()
            .add_filter({"term": {"store_id": "east"}})
            .add_filter({"term": {"version_id": "v2"}})
            .add_filter({"terms": {"acl_principals": ["user:alice"]}})
        )

    original = (
        scoped().add_query({"match": {"text_to_index": {"query": ""}}}).build_body("qzxnomatch987")
    )
    original_hits = experiment.search(index, original)
    strict = json.loads(json.dumps(original))
    strict["query"]["bool"]["minimum_should_match"] = 1
    strict_hits = experiment.search(index, strict)
    assert [h["_id"] for h in original_hits] == ["east-current"]
    assert strict_hits == []
    vector = (
        scoped()
        .add_knn({"semantic_vector": {"vector": [1.0, 0.0, 0.0, 0.0], "k": 1}})
        .build_body(size=5)
    )
    vector["query"]["bool"]["minimum_should_match"] = 1
    vector_hits = experiment.search(index, vector)
    assert [h["_id"] for h in vector_hits] == ["east-current"]
    analyzed = experiment.call(
        "POST", f"/{index}/_analyze", json={"analyzer": "indexing_analyzer", "text": "冷链断电"}
    )
    tokens = [t["token"] for t in analyzed["tokens"]]
    assert "冷链" in tokens
    # Exercise the real parent implementation and Store client, not a mocked DSL.
    parent_index = experiment.create(build_index_body(4), "parents")
    experiment.put_many(
        parent_index,
        [
            (
                str(i),
                {
                    "doc_id": "long-document",
                    "chunk_index": i,
                    "section_id": 0,
                    "context_id": 0,
                    "snippet": f"ROW-{i:03d}",
                    "text_to_index": f"ROW-{i:03d}",
                    "page_no": i + 1,
                    "acl_principals": ["public"],
                },
            )
            for i in range(60)
        ],
    )

    async def probe_parents():
        from railg.config import Settings
        from railg.retrieval.parents import construct_parents
        from railg.schema.document import Candidate
        from railg.store import Store

        settings = Settings.model_validate(
            {
                "store": {"url": str(experiment.client.base_url), "index": parent_index},
                "embedding": {"dims": 4},
            }
        )
        store = Store(settings)
        try:
            siblings = await store.fetch_siblings("long-document", 0, 0)
            parent = await construct_parents(
                store, [Candidate(doc_id="long-document", chunk_index=55, snippet="ROW-055")]
            )
            assert len(siblings) == 50
            assert "ROW-055" not in parent[0].snippet
            return {
                "source_chunks": 60,
                "fetched_siblings": len(siblings),
                "hit_index": 55,
                "returned_parent_contains_hit": False,
                "returned_parent": parent[0].snippet,
                "finding": (
                    "50-sibling limit loses the hit; window falls back to middle of fetched "
                    "siblings"
                ),
            }
        finally:
            await store.aclose()

    parents = asyncio.run(probe_parents())
    return {
        "mapping_contract": "passed",
        "vector_probe_kind": "synthetic_4d_protocol_only_not_embedding_quality",
        "scoped_no_match_original_ids": [h["_id"] for h in original_hits],
        "scoped_no_match_minimum_should_match_1_ids": [],
        "lucene_knn_scope_filter_ids": [h["_id"] for h in vector_hits],
        "chinese_tokens": tokens,
        "long_parent_original": parents,
    }


def metrics(rows):
    answerable = [r for r in rows if r["expected_versions"]]
    recall = [
        len(set(r["returned_versions"][:5]) & set(r["expected_versions"]))
        / len(r["expected_versions"])
        for r in answerable
    ]
    reciprocal, ndcg = [], []
    for row in answerable:
        relevant = set(row["expected_versions"])
        flags = [vid in relevant for vid in row["returned_versions"][:5]]
        reciprocal.append(next((1 / (i + 1) for i, ok in enumerate(flags) if ok), 0))
        ideal = sum(1 / math.log2(i + 2) for i in range(min(5, len(relevant))))
        ndcg.append(sum(ok / math.log2(i + 2) for i, ok in enumerate(flags)) / ideal)
    latencies = sorted(r["latency_ms"] for r in rows)
    return {
        "cases": len(rows),
        "with_gold_documents": len(answerable),
        "document_version_recall_at_5": statistics.mean(recall) if recall else None,
        "mrr_at_5": statistics.mean(reciprocal) if reciprocal else None,
        "ndcg_at_5": statistics.mean(ndcg) if ndcg else None,
        "scope_leaks": sum(len(r["scope_leaks"]) for r in rows),
        "cases_without_gold_documents": len(rows) - len(answerable),
        "empty_result_cases_without_gold": sum(
            not r["returned_versions"] for r in rows if not r["expected_versions"]
        ),
        "p50_ms": statistics.median(latencies),
        "p95_ms": latencies[math.ceil(0.95 * len(latencies)) - 1],
    }


def corpus_baseline(experiment):
    from railg.ingest.chunker import Chunker
    from railg.ingest.extractors import extract
    from railg.retrieval.builder import QueryBuilder
    from railg.schema.mapping import build_index_body

    corpus = ROOT / "docs/evaluation/knowledge"
    manifest = json.loads((corpus / "corpus-manifest.json").read_text("utf-8"))
    cases = [
        json.loads(line)
        for line in (corpus / "cases.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]
    fixture = json.loads((corpus / "entities-fixture.json").read_text("utf-8"))
    documents = manifest["documents"]
    mapping = build_index_body(4)
    mapping["mappings"]["properties"]["version_id"] = {"type": "keyword"}
    index = experiment.create(mapping, "corpus")
    records, parsed = [], []
    chunker = Chunker()

    def compact(value):
        return re.sub(r"\s+", "", value)

    for document in documents:
        path = (corpus / document["source_path"]).resolve()
        if not path.is_relative_to((corpus / "sources").resolve()):
            raise ValueError("Only source files may be parser inputs")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == document["source_sha256"]
        started = time.perf_counter()
        extracted = extract(path)
        chunks = chunker.chunk(
            extracted.file_markdown, extracted.page_markdowns, document["version_id"]
        )
        parsed.append(
            {
                "version_id": document["version_id"],
                "format": document["format"],
                "status": "empty"
                if extracted.is_empty
                else "partial"
                if extracted.meta.get("low_text_pages")
                else "text_extracted",
                "characters": len(extracted.file_markdown),
                "chunks": len(chunks),
                "parse_and_chunk_ms": (time.perf_counter() - started) * 1000,
                "low_text_pages": extracted.meta.get("low_text_pages", []),
                "ocr_pages": extracted.ocr_pages,
                "full_sections_present": [
                    s["section_id"]
                    for s in document["sections"]
                    if compact(s["text"]) in compact(extracted.file_markdown)
                ],
                "section_count": len(document["sections"]),
                "formula_cache_fixture": document.get("formula_fixture"),
                "extracted_formula_sheet": (
                    extracted.page_markdowns[1]
                    if document.get("formula_fixture") and len(extracted.page_markdowns) > 1
                    else None
                ),
                "locator_quality": (
                    "RAilG estimated page/header only; no verified sheet cell/CSV row mapping"
                ),
                "parser_metadata": extracted.meta,
            }
        )
        for chunk in chunks:
            records.append(
                (
                    document["version_id"] + ":" + str(chunk.chunk_index),
                    {
                        "version_id": document["version_id"],
                        "doc_id": document["document_id"],
                        "text_to_index": chunk.page_content,
                        "snippet": chunk.page_content,
                        "file_name": document["title"],
                        "chunk_index": chunk.chunk_index,
                        **chunk.metadata.model_dump(exclude={"source"}),
                    },
                )
            )
    experiment.put_many(index, records)
    rows = []
    for case in cases:
        principal = fixture["principals"][case["store_fixture"]]
        # Scope comes only from fixture metadata and an explicit historical-query
        # mode. Never read expected_document_versions to build this filter.
        allowed = [
            d["version_id"]
            for d in documents
            if d["store_id"] == principal["store_id"]
            and principal["role"] in d["allowed_roles"]
            and d["status"] == "published"
            and (
                case.get("allow_historical", False)
                or d["valid_from"] <= case["as_of"] < d["valid_until"]
            )
        ]
        body = (
            QueryBuilder()
            .add_filter({"terms": {"version_id": allowed}})
            .add_query({"match": {"text_to_index": {"query": ""}}})
            .build_body(case["query"], size=50)
        )
        body["query"]["bool"]["minimum_should_match"] = 1
        started = time.perf_counter()
        hits = experiment.search(index, body) if allowed else []
        elapsed = (time.perf_counter() - started) * 1000
        versions = list(dict.fromkeys(h["_source"]["version_id"] for h in hits))
        row = {
            "id": case["id"],
            "split": case["split"],
            "group": case["group"],
            "returned_versions": versions[:5],
            "expected_versions": case["expected_document_versions"],
            "allowed_version_count": len(allowed),
            "latency_ms": elapsed,
            "scope_leaks": [vid for vid in versions if vid not in allowed],
            "hit_count": len(hits),
            "top_chunk_ids": [h["_id"] for h in hits[:10]],
        }
        assert not row["scope_leaks"]
        rows.append(row)
    groups = {}
    for split in ("dev", "test"):
        part = [r for r in rows if r["split"] == split]
        groups[split] = {
            "all": metrics(part),
            "groups": {
                group: metrics([r for r in part if r["group"] == group])
                for group in sorted({r["group"] for r in part})
            },
        }
    return {
        "source_count": len(documents),
        "indexed_chunk_count": len(records),
        "profile": {
            "retrieval": "A_strict_CJK_BM25_only",
            "chunk_size": 100,
            "context_size_newlines": 20,
            "top_chunks": 50,
            "final_unique_versions": 5,
            "rerank": False,
            "parent": False,
            "query_router": "none; full question sent to match text",
            "ocr": False,
        },
        "limitations": [
            "Synthetic assistant-authored labels; human review pending.",
            "Recall is document-version retrieval, not answer correctness or citation support.",
            "No canonical transcription or label text was indexed.",
            (
                "Single-pass serial warm-service latency includes cold first query; no "
                "load/SLA inference."
            ),
            "No-answer correctness is not inferred from presence/absence of candidate documents.",
        ],
        "input_hashes": {
            name: hashlib.sha256((corpus / name).read_bytes()).hexdigest()
            for name in ["corpus-manifest.json", "cases.jsonl", "entities-fixture.json"]
        },
        "parsing": parsed,
        "metrics_by_split": groups,
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--opensearch-url", default="http://127.0.0.1:19200")
    parser.add_argument("--protocol-only", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    result = {
        "schema_version": 1,
        "ran_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "source": audit_source(args.source_root),
        "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        "image_digest": "opensearchproject/opensearch@sha256:1193b7c29c5d63028523728243cc4da047ac49f697a8f8105e5aeee2f89bcc4c",  # noqa: E501
        "embedding_and_rerank": {
            "status": "not_run",
            "reason": (
                "No configured model endpoint/key or installed local model; no model "
                "downloaded or borrowed key used."
            ),
        },
    }
    experiment = Experiment(args.opensearch_url)
    try:
        result["engine"] = experiment.call("GET", "/")["version"]
        result["protocol_probes"] = protocol_probes(experiment)
        if not args.protocol_only:
            result["corpus"] = corpus_baseline(experiment)
    finally:
        experiment.close()
    source_root = args.source_root.resolve()
    result["imported_source_hashes"] = {
        Path(module.__file__).resolve().relative_to(source_root).as_posix(): hashlib.sha256(
            Path(module.__file__).read_bytes()
        ).hexdigest()
        for name, module in list(sys.modules.items())
        if name.startswith("railg.")
        and getattr(module, "__file__", None)
        and Path(module.__file__).resolve().is_relative_to(source_root)
        and Path(module.__file__).suffix == ".py"
    }
    write_json(ROOT / "docs/api/knowledge-k0-baseline-result.json", result)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in {"packages", "corpus", "imported_source_hashes"}
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
