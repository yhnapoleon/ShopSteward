from sqlalchemy import select

from app.core.errors import AppError
from app.learning.dispatch import current_owner, enqueue_due
from app.learning.models import (
    AssetRevisionRow,
    AssetRow,
    BatchRow,
    EpisodeRow,
    LearningOutbox,
    LearningPolicyRow,
)
from app.learning.repository import create_candidate
from app.learning.schemas import LearningScope, SkillSpec
from app.scheduling.handlers import Handler

FORBIDDEN_TOOLS = {"memory_edit"}
PRECONDITIONS = {"current_mission", "current_case", "authoritative_snapshot_current"}
EXCLUSIONS = {"unknown_execution", "stale_snapshot", "missing_eta"}


def validate_candidate(candidate, bundle):
    spec = SkillSpec.model_validate(candidate["spec"])
    if bundle.get("family") and spec.task_family != bundle["family"]:
        raise AppError(422, "LEARNING_FAMILY_INVALID", "Candidate changed task family")
    if not set(spec.required_tools) <= set(bundle["allowed_tools"]) - FORBIDDEN_TOOLS:
        raise AppError(422, "LEARNING_TOOL_INVALID", "Candidate requires unavailable tools")
    if not set(spec.preconditions) <= PRECONDITIONS or not set(spec.exclusions) <= EXCLUSIONS:
        raise AppError(
            422, "LEARNING_CONDITION_INVALID", "Candidate conditions cannot be evaluated"
        )
    allowed = {e["id"] for e in bundle["events"]}
    if not candidate["evidence_ids"] or not set(candidate["evidence_ids"]) <= allowed:
        raise AppError(422, "LEARNING_EVIDENCE_INVALID", "Candidate invented evidence")
    return spec.model_dump()


def make_handlers(settings, *, generator=None):
    async def dispatch(db):
        if not settings.learning_enabled:
            return
        async with db.session() as session, session.begin():
            await enqueue_due(session, settings=settings)

    async def run(db, job):
        from app.agent_bridge.tools import catalog

        async with db.session() as session, session.begin():
            batch = await session.get(BatchRow, job.payload["batch_id"], with_for_update=True)
            pol = await session.get(LearningPolicyRow, batch.scope_id)
            principal = current_owner(settings, pol)
            if (
                not settings.learning_enabled
                or not settings.learning_generation_enabled
                or not principal
            ):
                raise AppError(409, "LEARNING_DISABLED", "Learning or authorization is unavailable")
            if pol.mode == "off" or batch.policy_version != pol.version:
                raise AppError(409, "LEARNING_POLICY_CHANGED", "Learning policy changed")
            if batch.status != "QUEUED":
                raise AppError(
                    409, "LEARNING_ATTEMPT_UNCERTAIN", "Previous model attempt will not be repeated"
                )
            episodes = list(
                await session.scalars(
                    select(EpisodeRow).where(
                        EpisodeRow.id.in_(batch.trigger["episode_ids"]),
                        EpisodeRow.scope_id == pol.id,
                    )
                )
            )
            if len(episodes) != len(batch.trigger["episode_ids"]) or any(
                not e.eligible for e in episodes
            ):
                raise AppError(
                    409, "LEARNING_EVIDENCE_STALE", "Source episode is no longer eligible"
                )
            ids = batch.trigger["evidence_ids"]
            events = list(
                await session.scalars(
                    select(LearningOutbox).where(
                        LearningOutbox.id.in_(ids),
                        LearningOutbox.scope_id == pol.id,
                        LearningOutbox.policy_version == pol.version,
                    )
                )
            )
            from app.core.hashing import digest

            if digest(sorted((e.id, e.digest) for e in events)) != batch.evidence_digest or any(
                "source:" + e.id in pol.blocked_concepts for e in events
            ):
                raise AppError(
                    409, "LEARNING_EVIDENCE_STALE", "Batch evidence changed or was forgotten"
                )
            bundle = {
                "events": [{"id": e.id, "document": e.document} for e in events],
                "allowed_tools": sorted(set(catalog(principal, settings)) - FORBIDDEN_TOOLS),
                "family": batch.trigger["family"],
            }
            # Reserve before outbound calls; a crash does not silently retry the model.
            batch.status = "RUNNING"
            batch.usage = {
                "reserved_calls": 3,
                "max_input_tokens": 12000,
                "max_output_tokens": 4000,
                "cost_status": "unknown",
            }
            existing = [
                r.spec
                for r in await session.scalars(
                    select(AssetRevisionRow)
                    .join(AssetRow, AssetRow.id == AssetRevisionRow.asset_id)
                    .where(
                        AssetRow.scope_id == pol.id,
                        AssetRow.task_family == batch.trigger["family"],
                        AssetRevisionRow.revision == AssetRow.latest_revision,
                        AssetRevisionRow.status != "REVOKED",
                    )
                    .limit(20)
                )
            ]
        if generator:
            candidates = await generator(bundle, existing)
        else:
            from shopsteward_agent.context import ModelProfile
            from shopsteward_agent.learning.extractor import extract_candidates
            from shopsteward_agent.model import OpenAIModel

            if not settings.agent_api_key_file:
                raise AppError(503, "AGENT_NOT_CONFIGURED", "Model credentials are not configured")
            profile = ModelProfile(
                model_id=settings.agent_model,
                api_mode=settings.agent_api_mode,
                reasoning_effort=settings.agent_reasoning_effort,
                max_input_tokens=12000,
                max_output_tokens=1000,
                timeout_s=settings.agent_model_timeout_seconds,
            )
            model = OpenAIModel(
                base_url=settings.agent_base_url,
                model=settings.agent_model,
                key_file=settings.agent_api_key_file,
                api_mode=settings.agent_api_mode,
                profile=profile,
            )
            candidates = await extract_candidates(bundle, existing, model)
        if len(candidates) > 3:
            raise AppError(422, "LEARNING_BUDGET", "Too many candidates")
        return {
            "candidates": [
                {"spec": validate_candidate(c, bundle), "evidence_ids": c["evidence_ids"]}
                for c in candidates
            ]
        }

    async def apply(session, job, result):
        batch = await session.get(BatchRow, job.payload["batch_id"], with_for_update=True)
        pol = await session.get(LearningPolicyRow, batch.scope_id, with_for_update=True)
        if (
            not settings.learning_enabled
            or not current_owner(settings, pol)
            or pol.mode == "off"
            or batch.policy_version != pol.version
        ):
            raise AppError(409, "LEARNING_POLICY_CHANGED", "Permission or learning consent changed")
        scope = LearningScope(
            principal_id=pol.principal_id, store_id=pol.store_id, source_domain=pol.source_domain
        )
        assets = []
        for candidate in result["candidates"]:
            rev = await create_candidate(session, scope=scope, **candidate_mapping(candidate))
            from app.learning.evaluation import static_evaluate

            await static_evaluate(
                session,
                scope=scope,
                asset=await session.get(AssetRow, rev.asset_id),
                revision=rev,
                settings=settings,
                principal=current_owner(settings, pol),
            )
            assets.append(rev.asset_id)
        batch.status = "SUCCEEDED"
        batch.usage = {**batch.usage, "asset_ids": assets, "candidates": len(assets)}
        return {
            "summary": "Learning candidates stored; independent validation required",
            "references": [],
        }

    async def failed(session, job, error):
        batch = await session.get(BatchRow, job.payload["batch_id"], with_for_update=True)
        if batch:
            batch.status = "FAILED"
            batch.usage = {
                **batch.usage,
                "error_code": getattr(error, "code", "LEARNING_GENERATION_FAILED"),
            }

    return {
        "learning_batch": Handler(
            run, retry_safe=True, apply=apply, on_error=failed, before_claim=dispatch
        )
    }


def candidate_mapping(candidate):
    return {"spec": candidate["spec"], "evidence": candidate["evidence_ids"]}
