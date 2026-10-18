from datetime import UTC, datetime, timedelta

import pytest


def report():
    now = datetime.now(UTC)
    return dict(
        binding={
            "asset_id": "a",
            "revision": 1,
            "content_hash": "h",
            "evidence_digest": "e",
            "policy_version": 1,
            "tool_catalog_hash": "t",
            "model_profile_hash": "m",
            "business_rule_version": "business-v1",
            "rubric_version": "skill-quality-v1",
        },
        dataset_hash="independent-dataset",
        baseline="without-skill",
        independent_cases=20,
        suite_kinds=["normal", "negative", "boundary", "recovery", "composition"],
        checks={f"H{i}": "pass" for i in range(1, 7)},
        scores={f"S{i}": 3 for i in range(1, 7)},
        evidence_refs=["test-report-1"],
        reviewed_by=["reviewer-1"],
        reviewer_kind="human_reviewed",
        measured=True,
        evaluated_at=now.isoformat(),
        expires_at=(now + timedelta(days=7)).isoformat(),
        quality_delta_lower=-0.01,
        improvement=0.2,
        target="corrections_reduction",
        dimension_reviews={
            f"S{i}": {
                "score": 3,
                "evidence_refs": ["test-report-1"],
                "reason": "Independent test fixture",
            }
            for i in range(1, 7)
        },
    )


def test_unknown_is_not_pass_and_hard_failure_cannot_be_offset():
    from app.learning.quality import decide

    r = report()
    assert decide(r, r["binding"])["status"] == "pass"
    r["checks"]["H3"] = "fail"
    assert decide(r, r["binding"])["status"] == "fail"
    r["checks"]["H3"] = "pass"
    r["scores"]["S5"] = None
    assert decide(r, r["binding"])["status"] == "insufficient_evidence"


@pytest.mark.parametrize(
    "change", [{"revision": 2}, {"evidence_digest": "changed"}, {"tool_catalog_hash": "new"}]
)
def test_quality_report_is_bound_to_exact_revision_and_dependencies(change):
    from app.learning.quality import decide

    r = report()
    assert decide(r, r["binding"] | change)["status"] != "pass"


def test_missing_independence_and_unreviewed_self_scores_cannot_activate():
    from app.learning.quality import decide

    r = report()
    for patch in [
        {"independent_cases": 19},
        {"measured": False},
        {"reviewer_kind": "model"},
        {"quality_delta_lower": None},
        {"suite_kinds": ["normal"]},
        {"expires_at": "2020-01-01T00:00:00Z"},
    ]:
        assert decide(r | patch, r["binding"])["status"] != "pass"


def test_unknown_field_or_out_of_range_score_is_rejected():
    from app.learning.quality import decide

    r = report()
    r["scores"]["S1"] = 5
    assert decide(r, r["binding"])["status"] != "pass"
