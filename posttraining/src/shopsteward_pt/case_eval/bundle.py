"""Read-only hash validation of frozen case, rubric, trace and review assets."""

import hashlib
from pathlib import Path
from typing import Literal

from .models import (
    CaseContract,
    CaseTrace,
    Count,
    FrozenRecord,
    Hash,
    RubricDefinition,
    SemanticReview,
    Text,
    content_hash,
    unique,
)


class FileReference(FrozenRecord):
    path: Text
    sha256: Hash


class FixtureReference(FileReference):
    fixture_id: Text


class BundleManifest(FrozenRecord):
    schema_version: Literal["case_manifest_v1"]
    dataset_version: Text
    artifact_kind: Literal["example", "recorded"]
    rubric: FileReference
    cases: FileReference
    traces: FileReference
    reviews: FileReference
    fixtures: tuple[FixtureReference, ...]
    research_status: Literal[
        "development_only_pending_human_calibration", "locked_pending_execution", "human_calibrated"
    ]
    locked_test_count: Count


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path, model):
    return tuple(
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def load_bundle(path: Path):
    path = path.resolve()
    manifest = BundleManifest.model_validate_json(path.read_text(encoding="utf-8"))
    root = path.parent

    def verify(reference):
        resolved = (root / reference.path).resolve()
        if resolved == root or root not in resolved.parents:
            raise ValueError("manifest file path must remain within bundle")
        if sha256_file(resolved) != reference.sha256:
            raise ValueError(f"frozen asset hash mismatch: {reference.path}")
        return resolved

    assets = [
        verify(ref)
        for ref in (
            manifest.rubric,
            manifest.cases,
            manifest.traces,
            manifest.reviews,
            *manifest.fixtures,
        )
    ]
    unique([ref.fixture_id for ref in manifest.fixtures], "fixture id")
    rubric = RubricDefinition.model_validate_json(assets[0].read_text(encoding="utf-8"))
    cases = read_jsonl(assets[1], CaseContract)
    traces = read_jsonl(assets[2], CaseTrace)
    reviews = read_jsonl(assets[3], SemanticReview)
    unique([(c.suite_id, c.case_id) for c in cases], "case id")
    unique([t.run_id for t in traces], "run id")
    fixtures = {ref.fixture_id: ref.sha256 for ref in manifest.fixtures}
    template_splits = {}
    for case in cases:
        if (
            case.dataset_version != manifest.dataset_version
            or case.artifact_kind != manifest.artifact_kind
        ):
            raise ValueError("case and manifest dataset identity disagree")
        if fixtures.get(case.fixture_id) != case.fixture_hash:
            raise ValueError("case fixture hash not bound to a manifest fixture")
        partition = "test" if case.split == "test" else "development"
        if case.template_id in template_splits and template_splits[case.template_id] != partition:
            raise ValueError(
                "template crosses development/test partitions, including across suites"
            )
        template_splits[case.template_id] = partition
    if sum(c.lock_status == "locked" for c in cases) != manifest.locked_test_count:
        raise ValueError("locked_test_count must equal actual locked case contracts")
    by_case = {(c.suite_id, c.case_id): c for c in cases}
    for trace in traces:
        case = by_case.get((trace.suite_id, trace.case_id))
        if case is None or (case.fixture_hash, case.artifact_kind) != (
            trace.fixture_hash,
            trace.artifact_kind,
        ):
            raise ValueError("trace is not bound to a frozen case")
    trace_hashes = {content_hash(trace) for trace in traces}
    if any(review.trace_hash not in trace_hashes for review in reviews):
        raise ValueError("orphan semantic review: no exact trace in bundle")
    return manifest, rubric, cases, traces, reviews, (path, *assets)
