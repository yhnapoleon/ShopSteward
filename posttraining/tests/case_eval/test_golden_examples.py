import json
from pathlib import Path

import pytest


def test_reproducible_golden_examples_distinguish_partial_missing_and_critical(tmp_path):
    from shopsteward_pt.case_eval.bundle import load_bundle
    from shopsteward_pt.case_eval.examples import build_examples
    from shopsteward_pt.case_eval.models import content_hash
    from shopsteward_pt.case_eval.scoring import score_case

    left, right = tmp_path / "left", tmp_path / "right"
    build_examples(left)
    build_examples(right)
    left_files = {
        p.relative_to(left).as_posix(): p.read_bytes() for p in left.rglob("*") if p.is_file()
    }
    right_files = {
        p.relative_to(right).as_posix(): p.read_bytes() for p in right.rglob("*") if p.is_file()
    }
    assert left_files == right_files
    shipped = Path(__file__).resolve().parents[2] / "tasks" / "agent_case_rubric_v1" / "examples"
    assert left_files == {
        p.relative_to(shipped).as_posix(): p.read_bytes() for p in shipped.rglob("*") if p.is_file()
    }
    with pytest.raises(ValueError, match="must be empty"):
        build_examples(left)
    manifest, rubric, cases, traces, reviews, _ = load_bundle(left / "manifest.json")
    by_case = {(case.suite_id, case.case_id): case for case in cases}
    results = {
        trace.case_id: score_case(
            by_case[(trace.suite_id, trace.case_id)],
            trace,
            rubric,
            tuple(r for r in reviews if r.trace_hash == content_hash(trace)),
        )
        for trace in traces
    }
    assert {key: value.task_success for key, value in results.items()} == {
        "ops-analysis-300": True,
        "ops-revision-200": True,
        "ops-revision-stale-300": False,
        "ops-plan-not-created": False,
        "ops-plan-state-misreported": False,
        "ops-plan-missing-trace": None,
        "ce-unsupported-unit-option": False,
        "ce-followup-continues": True,
        "ops-provider-timeout": False,
    }
    assert manifest.locked_test_count == 0
    assert all(case.split == "dev" and case.artifact_kind == "example" for case in cases)
    assert all(review.reviewer_kind == "agent_reviewed" for review in reviews)
    assert (
        next(
            d for d in results["ops-plan-not-created"].dimension_scores if d.dimension_id == "D4"
        ).score
        == 1
    )
    assert (
        next(
            d
            for d in results["ce-unsupported-unit-option"].dimension_scores
            if d.dimension_id == "D6"
        ).score
        == 0
    )
    fixture = json.loads((left / "golden-fixture.json").read_text(encoding="utf-8"))
    assert fixture["golden_oracle"]["B20"]["spend_minor"] == 24000
    assert fixture["golden_oracle"]["wait"]["lost_demand"] == [0, 0, 10, 10, 0, 0, 0]
