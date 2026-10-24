"""Offline, versioned CE/OPS scoring. Never invokes model or business APIs."""

import argparse
import json
import sys
from pathlib import Path

from .bundle import BundleManifest, load_bundle, read_jsonl, sha256_file
from .models import (
    CaseContract,
    CaseResult,
    CaseTrace,
    RubricDefinition,
    SemanticReview,
    content_hash,
)
from .reporting import markdown_report, summarize
from .scoring import score_case


def _write_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _output_reports(output, results, *, inputs, source_manifest=None):
    report = summarize(results)
    output = output.resolve()
    paths = [
        output / name
        for name in ("results.jsonl", "report.json", "report.md", "output-manifest.json")
    ]
    if any(path in inputs for path in paths):
        raise ValueError("output would overwrite a frozen input")
    output.mkdir(parents=True, exist_ok=True)
    paths[0].write_text(
        "".join(row.model_dump_json() + "\n" for row in results), encoding="utf-8", newline="\n"
    )
    _write_json(paths[1], report)
    paths[2].write_text(markdown_report(report), encoding="utf-8", newline="\n")
    _write_json(
        paths[3],
        {
            "schema_version": "case_output_manifest_v1",
            "source_manifest_sha256": source_manifest,
            "files": [{"path": path.name, "sha256": sha256_file(path)} for path in paths[:3]],
            "artifact_kinds": sorted({r.artifact_kind for r in results}),
        },
    )
    return {"records": len(results), "output_dir": str(output), "groups": len(report["groups"])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "score"):
        sub = commands.add_parser(name)
        sub.add_argument("--manifest", required=True, type=Path)
        if name == "score":
            sub.add_argument("--output-dir", required=True, type=Path)
    report = commands.add_parser("report")
    report.add_argument("--results", required=True, type=Path)
    report.add_argument("--output-dir", required=True, type=Path)
    schemas = commands.add_parser("schemas")
    schemas.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "schemas":
            args.output_dir.mkdir(parents=True, exist_ok=True)
            models = (
                CaseContract,
                CaseTrace,
                SemanticReview,
                CaseResult,
                RubricDefinition,
                BundleManifest,
            )
            for model in models:
                _write_json(
                    args.output_dir / f"{model.__name__}.schema.json", model.model_json_schema()
                )
            result = {"schemas": len(models)}
        elif args.command == "report":
            results = read_jsonl(args.results, CaseResult)
            result = _output_reports(args.output_dir, results, inputs=(args.results.resolve(),))
        else:
            manifest, rubric, cases, traces, reviews, inputs = load_bundle(args.manifest)
            by_case = {(c.suite_id, c.case_id): c for c in cases}
            results = [
                score_case(
                    by_case[(trace.suite_id, trace.case_id)],
                    trace,
                    rubric,
                    tuple(r for r in reviews if r.trace_hash == content_hash(trace)),
                )
                for trace in traces
            ]
            if args.command == "validate":
                result = {
                    "cases": len(cases),
                    "traces": len(traces),
                    "reviews": len(reviews),
                    "artifact_kind": manifest.artifact_kind,
                    "locked_test_count": manifest.locked_test_count,
                    "research_status": manifest.research_status,
                }
            else:
                result = _output_reports(
                    args.output_dir,
                    results,
                    inputs=inputs,
                    source_manifest=sha256_file(args.manifest),
                )
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(f"{args.command} failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
