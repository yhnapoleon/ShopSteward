"""Allowlisted, version-bound projections of committed business tool results."""

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import Field, ValidationError

from app.api.schemas import DTO
from app.core.errors import AppError
from app.knowledge import repository as documents
from app.knowledge.storage import original_path
from app.missions.models import PlanRow
from app.planning.schemas import Candidate, Plan


class PlanComparison(DTO):
    plan_id: str
    plan_version: int = Field(strict=True, ge=1)
    state_version: int = Field(strict=True, ge=1)
    mission_version: int = Field(strict=True, ge=1)
    currency: Literal["CNY"]
    cash_floor_minor: int = Field(strict=True, ge=0)
    max_purchase_qty: int | None = Field(ge=0)
    candidates: list[Candidate]
    recommended_candidate_id: str | None
    evaluated_at: datetime


class BusinessOutcome(DTO):
    invocation_id: str
    kind: Literal["evaluation", "revision"]
    recorded_at: datetime
    availability: Literal["available", "unavailable"]
    reason: str | None = None
    before: PlanComparison | None = None
    after: PlanComparison | None = None


class HistoricalEvidence(DTO):
    run_id: str
    reference: dict
    title: str
    version_no: int
    text: str
    truncated: bool
    recorded_at: datetime
    historical: Literal[True] = True


def comparison(plan):
    parsed = Plan.model_validate(plan)
    snapshot = parsed.input_snapshot
    return PlanComparison(
        plan_id=parsed.id,
        plan_version=parsed.plan_version,
        state_version=parsed.state_version,
        mission_version=snapshot.mission_version,
        currency=snapshot.state.currency,
        cash_floor_minor=snapshot.policy.cash_floor_minor,
        max_purchase_qty=snapshot.task_constraints.get("max_purchase_qty"),
        candidates=parsed.candidates,
        recommended_candidate_id=parsed.recommended_candidate_id,
        evaluated_at=snapshot.evaluated_at,
    )


async def outcomes(session, conversation, calls):
    result = []
    for call in calls:
        if call.tool not in {"evaluate_plan", "revise_plan"} or call.result.get("ok") is not True:
            continue
        outcome = BusinessOutcome(
            invocation_id=call.invocation_id,
            kind="evaluation" if call.tool == "evaluate_plan" else "revision",
            recorded_at=call.created_at,
            availability="unavailable",
            reason="历史结果缺少完整版本关联，无法可靠比较。",
        )
        data = call.result.get("data", {})
        try:
            base = await session.get(PlanRow, data.get("base_plan_id", ""))
            if base is None or base.mission_id != conversation.mission_id:
                result.append(outcome)
                continue
            before = comparison(base.document)
            if call.tool == "evaluate_plan":
                if (
                    data.get("hypothetical") is not True
                    or data["state_version"] != before.state_version
                ):
                    raise ValueError("Invalid evaluation provenance")
                after = PlanComparison.model_validate(
                    before.model_dump()
                    | {
                        "candidates": [Candidate.model_validate(c) for c in data["candidates"]],
                        "recommended_candidate_id": data["recommended_candidate_id"],
                        "max_purchase_qty": data["task_constraints"].get("max_purchase_qty"),
                        "evaluated_at": call.created_at,
                    }
                )
            else:
                revised = await session.get(PlanRow, data.get("id", ""))
                if revised is None or revised.mission_id != conversation.mission_id:
                    raise ValueError("Missing revised plan")
                after = comparison(revised.document)
                if (
                    after.plan_version != before.plan_version + 1
                    or after.mission_version != before.mission_version + 1
                    or after.state_version != before.state_version
                ):
                    raise ValueError("Invalid revision link")
            if after.recommended_candidate_id not in {c.id for c in after.candidates} | {None}:
                raise ValueError("Invalid recommendation")
            outcome.before, outcome.after = before, after
            outcome.availability, outcome.reason = "available", None
        except (ValidationError, ValueError, KeyError, TypeError, AttributeError):
            pass
        result.append(outcome)
    return result


async def historical_evidence(
    session, principal, conversation, run_id, calls, identity, storage_root
):
    """Read the actual saved excerpt, never re-search current publications."""
    fields = (
        "id",
        "version_id",
        "generation_id",
        "chunk_id",
        "metadata_revision",
        "content_sha256",
    )
    for call in calls:
        if (
            call.tool not in {"search_documents", "read_document_evidence"}
            or call.result.get("ok") is not True
        ):
            continue
        for ref in call.result.get("references", []):
            if any(str(ref.get(k, "")) != str(identity[k]) for k in fields):
                continue
            version = await documents.version(session, principal, ref["id"], ref["version_id"])
            doc = await documents.visible(session, principal, ref["id"], content=True)
            if doc.store_id != conversation.store_id or version.content_sha256 != ref.get(
                "original_sha256"
            ):
                break
            if not original_path(storage_root, version.raw_key).is_file():
                break
            for c in call.result.get("data", {}).get("candidates", []):
                if any(c.get("document_id" if k == "id" else k) != ref.get(k) for k in fields):
                    continue
                excerpt = c.get("text")
                if (
                    not isinstance(excerpt, str)
                    or len(excerpt) > 24000
                    or hashlib.sha256(excerpt.encode()).hexdigest() != ref["content_sha256"]
                    or c.get("original_sha256") != version.content_sha256
                    or c.get("locator") != ref.get("locator")
                ):
                    break
                # Snapshot title belongs to the cited metadata revision, not today's rename.
                return HistoricalEvidence(
                    run_id=run_id,
                    reference={k: ref[k] for k in (*fields, "original_sha256", "locator")},
                    title=c.get("title") or version.original_name,
                    version_no=version.version_no,
                    text=excerpt,
                    truncated=bool(c.get("truncated")),
                    recorded_at=call.created_at,
                )
    raise AppError(
        404,
        "HISTORICAL_EVIDENCE_UNAVAILABLE",
        "该历史片段不存在、校验不通过或当前不可访问；未替换为最新版本。",
    )
