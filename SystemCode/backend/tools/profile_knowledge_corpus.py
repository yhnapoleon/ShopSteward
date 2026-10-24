"""Reproducible read-only parse/locator/worker DTO profiling against a fixed manifest."""

import argparse
import collections
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shopsteward_knowledge.contracts import IngestionRequest, OriginalRef, Projection
from shopsteward_knowledge.parsing import parse_original
from shopsteward_knowledge.parsing.chunking import chunk_blocks
from shopsteward_knowledge.worker import Claim, candidate_chunks

from tools.import_knowledge_corpus import prepare_upload


def main():
    parser = argparse.ArgumentParser(
        description="Profile actual corpus parsing; no database, index or model calls."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    root = (
        manifest_path.parent.parent
        if manifest_path.parent.name == "manifests"
        else manifest_path.parent
    )
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    mapping = json.loads(args.mapping.read_text("utf-8"))
    started = time.perf_counter()
    cpu = time.process_time()
    rows = []
    statuses = collections.Counter()
    try:
        import psutil

        process = psutil.Process()
        sampled_peak = process.memory_info().rss
    except ImportError:
        process = None
        sampled_peak = None
    for record in manifest["documents"]:
        t = time.perf_counter()
        try:
            prepared = prepare_upload(record, root, mapping)
            content = prepared["path"].read_bytes()
            ref = OriginalRef(
                version_id=record["version_fixture_id"],
                sha256=prepared["content_sha256"],
                mime=record["mime"],
                storage_key=record["original_path"],
                size_bytes=len(content),
            )
            parsed = parse_original(ref, content)
            chunks = chunk_blocks(parsed.blocks, {"id": "lexical-v1"})
            projection = Projection(
                document_id=record["document_fixture_id"],
                version_id=ref.version_id,
                store_id=prepared["store_id"],
                metadata_revision=1,
                title=prepared["metadata"]["title"],
                entity_refs=prepared["metadata"]["sku_ids"] + prepared["metadata"]["supplier_ids"],
                valid_from=prepared["metadata"].get("valid_from"),
                valid_until=prepared["metadata"].get("valid_until"),
                provenance=prepared["metadata"]["provenance"],
            )
            ingest = IngestionRequest(original=ref, projection=projection)
            claim = Claim(
                "profile-job",
                "profile-generation",
                "profile-lease",
                1,
                ingest.model_dump(mode="json"),
                projection.model_dump(mode="json"),
            )
            candidates = candidate_chunks(claim, parsed, chunks)
            statuses[parsed.status] += 1
            rows.append(
                {
                    "version_fixture_id": ref.version_id,
                    "sha256": ref.sha256,
                    "status": parsed.status,
                    "chunks": len(candidates),
                    "chars": sum(len(c["text"]) for c in candidates),
                    "parse_ms": round((time.perf_counter() - t) * 1000, 3),
                    "warnings": parsed.warnings,
                }
            )
        except Exception as exc:
            statuses["ERROR"] += 1
            rows.append(
                {
                    "version_fixture_id": record["version_fixture_id"],
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )
        if process:
            sampled_peak = max(sampled_peak, process.memory_info().rss)
    peak_working_set = None
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t)
                for n in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        process_handle = ctypes.windll.kernel32.GetCurrentProcess
        process_handle.restype = wintypes.HANDLE
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if get_info(process_handle(), ctypes.byref(counters), counters.cb):
            peak_working_set = counters.PeakWorkingSetSize
    result = {
        "peak_process_working_set_bytes": peak_working_set,
        "memory_scope": "entire parser process, excludes DB/index/worker containers",
        "mode": "actual_local_parse_no_index_no_model",
        "python": platform.python_version(),
        "platform": platform.system(),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "manifest_unchanged": manifest_path.read_bytes() == raw,
        "versions": len(rows),
        "statuses": dict(statuses),
        "chunks": sum(r.get("chunks", 0) for r in rows),
        "chars": sum(r.get("chars", 0) for r in rows),
        "wall_seconds": round(time.perf_counter() - started, 3),
        "cpu_seconds": round(time.process_time() - cpu, 3),
        "rss_sampled_after_each_document_max_bytes": sampled_peak,
        "rss_limitations": "sampling can miss within-document peaks",
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=True))
    print(json.dumps([r for r in rows if "error_type" in r][:8], ensure_ascii=True))
    raise SystemExit(1 if statuses["ERROR"] else 0)


if __name__ == "__main__":
    main()
