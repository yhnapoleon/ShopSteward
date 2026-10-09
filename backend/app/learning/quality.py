"""Fail-closed release decisions; subjective totals cannot offset hard failures."""

from datetime import UTC, datetime

from pydantic import ValidationError

from app.learning.schemas import QualityReport

RUBRIC_VERSION = "skill-quality-v1"
HARD = {f"H{i}" for i in range(1, 7)}
SOFT = {f"S{i}" for i in range(1, 7)}
SUITES = {"normal", "negative", "boundary", "recovery", "composition"}
BINDINGS = {
    "asset_id",
    "revision",
    "content_hash",
    "evidence_digest",
    "policy_version",
    "tool_catalog_hash",
    "model_profile_hash",
    "business_rule_version",
    "rubric_version",
}


def decide(report, expected, *, now=None):
    now = now or datetime.now(UTC)
    try:
        r = QualityReport.model_validate(report)
    except (ValidationError, TypeError):
        return {"status": "insufficient_evidence", "reasons": ["invalid_report"]}
    if any(r.checks.get(key) == "fail" for key in HARD):
        return {"status": "fail", "reasons": ["hard_check_failed"]}
    reasons = []
    if set(r.binding) != BINDINGS or r.binding != expected:
        reasons.append("binding_changed")
    if r.binding.get("rubric_version") != RUBRIC_VERSION:
        reasons.append("rubric_changed")
    if r.evaluated_at > now or r.expires_at <= now:
        reasons.append("report_not_current")
    if set(r.checks) != HARD or any(r.checks[key] != "pass" for key in HARD):
        reasons.append("hard_checks_incomplete")
    if set(r.scores) != SOFT or any(r.scores.get(key) is None for key in SOFT):
        reasons.append("unknown_dimension")
    elif any(r.scores[key] < 3 for key in SOFT):
        return {"status": "fail", "reasons": ["rubric_below_threshold"]}
    if r.independent_cases < 20 or not SUITES <= set(r.suite_kinds):
        reasons.append("coverage_insufficient")
    if not r.measured or not r.evidence_refs or not r.reviewed_by:
        reasons.append("missing_independent_evidence")
    if r.reviewer_kind != "human_reviewed":
        reasons.append("uncalibrated_judge")
    if set(r.dimension_reviews) != SOFT or any(
        item.score != r.scores.get(key)
        or not item.evidence_refs
        or not set(item.evidence_refs) <= set(r.evidence_refs)
        for key, item in r.dimension_reviews.items()
    ):
        reasons.append("dimension_evidence_missing")
    if r.quality_delta_lower is None or r.quality_delta_lower < -0.02:
        reasons.append("noninferiority_unproven")
    target = 0.05 if r.target == "coverage_gain" else 0.15
    if r.improvement is None or r.improvement < target:
        reasons.append("incremental_value_unproven")
    if r.target == "coverage_gain" and (
        r.quality_delta_lower is None or r.quality_delta_lower <= 0
    ):
        reasons.append("coverage_gain_unproven")
    return {"status": "insufficient_evidence" if reasons else "pass", "reasons": reasons}
