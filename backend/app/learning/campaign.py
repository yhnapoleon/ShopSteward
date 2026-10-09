"""Trusted offline reviewer workflow. Deliberately absent from agent/public tools."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.evaluation import paired_metrics, static_evaluate
from app.learning.lifecycle import binding
from app.learning.models import AssetRevisionRow, EvaluationRow
from app.learning.quality import HARD, SOFT, SUITES, decide
from app.learning.repository import evidence_rows, get_asset, policy
from app.learning.schemas import DimensionReview


def adjudicate(reviews, known_refs):
    if (
        len(reviews) != 2
        or len({r["reviewer"] for r in reviews}) != 2
        or any(not r["reviewer"].strip() for r in reviews)
    ):
        raise ValueError("Two named independent human reviews are required")
    parsed = []
    for review in reviews:
        if set(review["dimensions"]) != SOFT:
            raise ValueError("Every rubric dimension is required")
        dimensions = {k: DimensionReview.model_validate(v) for k, v in review["dimensions"].items()}
        if any(
            not d.evidence_refs or not set(d.evidence_refs) <= known_refs
            for d in dimensions.values()
        ):
            raise ValueError("Review references must resolve to verified artifacts")
        parsed.append(dimensions)
    scores, details = {}, {}
    for key in SOFT:
        a, b = parsed[0][key], parsed[1][key]
        scores[key] = a.score if a.score == b.score else None
        details[key] = {
            "score": scores[key],
            "evidence_refs": sorted(set(a.evidence_refs + b.evidence_refs)),
            "reason": a.reason + " / " + b.reason
            if a.score == b.score
            else "Reviewer disagreement; adjudication required",
        }
    return scores, details


async def prepare(session, *, scope, asset_id, revision, settings, principal, cases, target):
    if target not in {"corrections_reduction", "tool_calls_reduction", "coverage_gain"}:
        raise ValueError("Choose the improvement target before executing replays")
    await policy(session, scope, lock=True)
    asset = await get_asset(session, scope, asset_id)
    rev = await session.get(AssetRevisionRow, (asset.id, revision))
    if not rev or rev.status == "REVOKED":
        raise AppError(409, "LEARNING_STATE_CONFLICT", "Revision unavailable")
    sources = await evidence_rows(session, scope, rev.evidence_ids)
    source_ids = (
        {r.id for r in sources}
        | {r.document["source_id"] for r in sources}
        | {r.document["intent_key"] for r in sources}
    )
    ids = [c["id"] for c in cases]
    if len(ids) < 20 or len(ids) != len(set(ids)) or not SUITES <= {c["suite"] for c in cases}:
        raise ValueError("At least 20 unique cases across all five suites required")
    for case in cases:
        if (
            case["id"] in source_ids
            or set(case["source_ids"]) & source_ids
            or case.get("origin") != "locked_test"
            or not case.get("input_hash")
        ):
            raise ValueError("Cases must be locked, independent and input-bound")
    result = await static_evaluate(
        session, scope=scope, asset=asset, revision=rev, settings=settings, principal=principal
    )
    await session.flush()
    row = await session.get(EvaluationRow, result["id"])
    manifest = {
        "id": str(uuid4()),
        "cases": cases,
        "target": target,
        "source_ids": sorted(source_ids),
        "created_at": datetime.now(UTC).isoformat(),
        "baseline_revision": asset.active_revision,
        "binding": row.report["binding"],
        "dataset_hash": digest(cases),
    }
    row.decision = {"status": "pending", "manifest": manifest, "completed": False}
    asset.version += 1
    return {"campaign_id": row.id, **manifest}


async def complete(
    session,
    *,
    scope,
    campaign_id,
    settings,
    principal,
    results,
    reviews,
    checks,
    verified_artifacts,
):
    await policy(session, scope, lock=True)
    campaign = await session.get(EvaluationRow, campaign_id, with_for_update=True)
    if not campaign or campaign.decision.get("completed") or "manifest" not in campaign.decision:
        raise ValueError("A fresh preregistered campaign is required")
    asset = await get_asset(session, scope, campaign.asset_id)
    rev = await session.get(AssetRevisionRow, (asset.id, campaign.revision))
    manifest = campaign.decision["manifest"]
    expected = await binding(
        session, scope=scope, asset=asset, revision=rev, settings=settings, principal=principal
    )
    if expected != manifest["binding"] or asset.active_revision != manifest["baseline_revision"]:
        raise ValueError("Dependencies changed; prepare a new campaign")
    cases = {c["id"]: c for c in manifest["cases"]}
    if {r["id"] for r in results} != set(cases):
        raise ValueError("Replay coverage must exactly match the frozen manifest")
    now = datetime.now(UTC)
    prepared = datetime.fromisoformat(manifest["created_at"])
    for row in results:
        case = cases[row["id"]]
        if any(row.get(k) != case[k] for k in ("input_hash", "suite", "source_ids")):
            raise ValueError("Replay does not match frozen case")
        at = datetime.fromisoformat(row["completed_at"])
        if at.tzinfo is None or not prepared <= at <= now:
            raise ValueError("Replay must follow preregistration")
        if not row.get("artifact_ref") or row["artifact_ref"] not in verified_artifacts:
            raise ValueError("Replay artifact is unavailable")
    metrics = paired_metrics(
        results, target=manifest["target"], source_ids=set(manifest["source_ids"])
    )
    if manifest["baseline_revision"] is not None:
        if any("without_skill" not in row for row in results):
            raise ValueError("Compare against both the previous revision and no skill")
        no_skill = paired_metrics(
            [{**row, "baseline": row["without_skill"]} for row in results],
            target=manifest["target"],
            source_ids=set(manifest["source_ids"]),
        )
        metrics["quality_delta_lower"] = min(
            metrics["quality_delta_lower"], no_skill["quality_delta_lower"]
        )
        metrics["improvement"] = (
            min(metrics["improvement"], no_skill["improvement"])
            if metrics["improvement"] is not None and no_skill["improvement"] is not None
            else None
        )
    scores, dimensions = adjudicate(reviews, set(verified_artifacts))
    if set(checks) != HARD or any(
        c.get("status") not in {"pass", "fail", "unknown"}
        or not c.get("evidence_refs")
        or not set(c["evidence_refs"]) <= set(verified_artifacts)
        for c in checks.values()
    ):
        raise ValueError("Hard checks require verified artifacts")
    report = {
        **campaign.report,
        **metrics,
        "dataset_hash": manifest["dataset_hash"],
        "baseline": "active:" + str(manifest["baseline_revision"])
        if manifest["baseline_revision"]
        else "without-skill",
        "checks": {k: v["status"] for k, v in checks.items()},
        "scores": scores,
        "dimension_reviews": dimensions,
        "evidence_refs": sorted(verified_artifacts),
        "reviewed_by": [r["reviewer"] for r in reviews],
        "reviewer_kind": "human_reviewed",
        "measured": True,
        "evaluated_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
    }
    identifier = digest([campaign.id, report])
    decision = decide(report, expected)
    session.add(
        EvaluationRow(
            id=identifier,
            asset_id=asset.id,
            revision=rev.revision,
            report=report,
            decision={
                **decision,
                "campaign_id": campaign.id,
                "artifact_hashes": verified_artifacts,
                "hard_check_evidence": checks,
                "reviews": reviews,
                "results": results,
            },
        )
    )
    campaign.decision = {**campaign.decision, "completed": True, "report_id": identifier}
    rev.evaluation_id = identifier
    asset.version += 1
    return {"evaluation_id": identifier, "decision": decision}
