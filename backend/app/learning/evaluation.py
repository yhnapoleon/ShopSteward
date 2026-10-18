"""Offline evaluation. Generation never supplies its own release verdict.

Static reports intentionally retain unknowns. Paired results must come from a
trusted isolated runner; they are not inferred from historical agent replies.
"""

from datetime import UTC, datetime, timedelta
from math import sqrt
from statistics import mean

from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.jobs import validate_candidate
from app.learning.lifecycle import binding
from app.learning.models import EvaluationRow
from app.learning.quality import HARD, SOFT, decide
from app.learning.repository import evidence_rows


def _wilson(k, n):
    # Simultaneous one-sided 97.5% bounds for gain and loss frequencies.
    z = 1.959963984540054
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0, center - half), min(1, center + half)


def paired_metrics(rows, *, target, source_ids):
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Evaluation cases must be nonempty and unique")
    if any(r["id"] in source_ids or set(r.get("source_ids", [])) & source_ids for r in rows):
        raise ValueError("Evaluation cases must be independent of generation sources")
    for row in rows:
        for variant in ("baseline", "candidate"):
            item = row[variant]
            if type(item.get("success")) is not bool:
                raise ValueError("Unresolved outcome cannot be scored as success")
            if any(
                type(item.get(k)) is not int or item[k] < 0 for k in ("corrections", "tool_calls")
            ):
                raise ValueError("Measured nonnegative counts required")
    gains = sum(r["candidate"]["success"] and not r["baseline"]["success"] for r in rows)
    losses = sum(r["baseline"]["success"] and not r["candidate"]["success"] for r in rows)
    lower = _wilson(gains, len(rows))[0] - _wilson(losses, len(rows))[1]
    if target == "coverage_gain":
        improvement = (gains - losses) / len(rows)
    else:
        key = {"corrections_reduction": "corrections", "tool_calls_reduction": "tool_calls"}[target]
        base = mean(r["baseline"][key] for r in rows)
        improvement = 1 - mean(r["candidate"][key] for r in rows) / base if base else None
    return dict(
        independent_cases=sum(r.get("applicable", r["suite"] != "negative") is True for r in rows),
        suite_kinds=sorted({r["suite"] for r in rows}),
        quality_delta_lower=lower,
        improvement=improvement,
        target=target,
    )


async def replay_suite(cases, *, candidate, baseline, execute):
    """execute(case, spec) must create/reset its own isolated environment per call.

    No live-business adapter is installed. A failed/unknown oracle stays unresolved.
    Alternating order limits systematic warm-cache bias; seeds belong in cases.
    """
    rows = []
    for index, case in enumerate(cases):
        outcomes = {}
        variants = [("baseline", baseline), ("candidate", candidate)]
        for label, spec in variants if index % 2 == 0 else reversed(variants):
            outcomes[label] = await execute(case, spec)
        rows.append({**{k: case[k] for k in ("id", "suite", "source_ids")}, **outcomes})
    return rows


async def static_evaluate(session, *, scope, asset, revision, settings, principal):
    from app.agent_bridge.tools import catalog

    expected = await binding(
        session, scope=scope, asset=asset, revision=revision, settings=settings, principal=principal
    )
    rows = await evidence_rows(session, scope, revision.evidence_ids)
    checks = {key: "unknown" for key in HARD}
    try:
        validate_candidate(
            {"spec": revision.spec, "evidence_ids": revision.evidence_ids},
            {
                "allowed_tools": list(catalog(principal, settings)),
                "events": [{"id": r.id} for r in rows],
            },
        )
        checks["H1"] = "pass"
    except (ValueError, AppError):
        checks["H1"] = "fail"
    now = datetime.now(UTC)
    report = dict(
        binding=expected,
        dataset_hash="not-run",
        baseline="without-skill",
        independent_cases=0,
        suite_kinds=[],
        checks=checks,
        scores={key: None for key in SOFT},
        evidence_refs=revision.evidence_ids,
        reviewed_by=[],
        reviewer_kind="model",
        measured=False,
        evaluated_at=now.isoformat(),
        expires_at=(now + timedelta(days=7)).isoformat(),
        target="tool_calls_reduction",
        dimension_reviews={
            key: {
                "score": None,
                "evidence_refs": [],
                "reason": "Independent replay and human review are not yet available",
            }
            for key in SOFT
        },
    )
    identifier = digest([revision.asset_id, revision.revision, report])
    decision = decide(report, expected)
    session.add(
        EvaluationRow(
            id=identifier,
            asset_id=asset.id,
            revision=revision.revision,
            report=report,
            decision=decision,
        )
    )
    # A diagnostic check is not a release decision for an already admitted version.
    if revision.status not in {"ACTIVE", "SUPERSEDED"}:
        revision.evaluation_id = identifier
    return {"id": identifier, "report": report, "decision": decision}
