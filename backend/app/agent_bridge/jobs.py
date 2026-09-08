import hashlib
import secrets

from sqlalchemy import select

from app.agent_bridge import repository as repo
from app.agent_bridge.models import AgentRun, Conversation, Message
from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.scheduling.handlers import Handler
from app.scheduling.models import Job
from app.scheduling.repository import owned


def current_principal(settings, conversation):
    grants = [
        g
        for g in settings.auth_tokens
        if g.kind == "user" and g.principal_id == conversation.principal_id
    ]
    for grant in grants:
        try:
            authorize_store(grant, conversation.store_id)
            return grant
        except AppError:
            continue
    raise AppError(403, "AGENT_PERMISSION_REVOKED", "Conversation owner no longer has access")


async def assert_lease(session, job):
    row = await session.scalar(
        select(Job.id).where(*owned(job.id, job.lease_token)).with_for_update()
    )
    if row is None:
        raise AppError(409, "AGENT_LEASE_LOST", "Agent no longer owns this execution")


def scheduler_references(references):
    """JobResult has generic pointers; full evidence remains in AgentRun/Message."""
    return [
        {"type": "artifact", "id": ref["id"], "version": ref["version_id"]}
        if ref.get("type") == "document"
        else ref
        for ref in references
    ]


def make_handlers(settings, *, executor=None):
    async def run(db, job):
        token = secrets.token_urlsafe(32)
        async with db.session() as session, session.begin():
            item = await session.get(AgentRun, job.payload["agent_run_id"])
            conversation = await session.get(
                Conversation, item.conversation_id, with_for_update={"key_share": True}
            )
            await session.refresh(item, with_for_update=True)
            if conversation.active_run_id != item.id or item.status not in {"QUEUED", "RUNNING"}:
                raise AppError(409, "AGENT_RUN_INACTIVE", "Run is no longer active")
            if item.graph_version != "agent-v1":
                raise AppError(
                    409, "GRAPH_VERSION_UNAVAILABLE", "Stored graph version is unavailable"
                )
            current_principal(settings, conversation)
            item.status = "RUNNING"
            item.token_hash = hashlib.sha256(token.encode()).hexdigest()
            item.token_job_lease = job.lease_token
            history = (
                await session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation.id,
                        (Message.seq <= item.input_through_seq)
                        | (Message.role == "assistant")
                        | (Message.run_id == item.id),
                    )
                    .order_by(Message.seq.desc())
                    .limit(80)
                )
            ).all()
            # Queued user messages may precede an earlier reply in wall-clock order.
            # Group complete turns so each prior reply follows its own input.
            anchors = {}
            for message in history:
                anchors[message.run_id] = min(anchors.get(message.run_id, message.seq), message.seq)
            history.sort(key=lambda message: (anchors[message.run_id], message.seq))
            context = {
                "db": db,
                "settings": settings,
                "job": job,
                "run_id": item.id,
                "conversation_id": conversation.id,
                "mission_id": conversation.mission_id,
                "store_id": conversation.store_id,
                "principal_id": conversation.principal_id,
                "token": token,
                "resume": item.resume_value,
                "resume_interrupt_id": item.interrupt_id,
                "messages": [{"role": m.role, "content": m.content} for m in history],
            }
            if item.trigger == "FOLLOWUP":
                context["messages"].append(
                    {
                        "role": "user",
                        "content": "后台跟进：检查最新经营变化，解释新增风险、方案或行动结果；"
                        "没有变化时简短说明。",
                    }
                )
            await assert_lease(session, job)
        if executor is not None:
            return await executor(context)
        from app.agent_bridge.composition import execute

        return await execute(context)

    async def apply(session, job, output):
        item = await session.get(AgentRun, job.payload["agent_run_id"])
        conversation = await session.get(
            Conversation, item.conversation_id, with_for_update={"key_share": True}
        )
        await session.refresh(item, with_for_update=True)
        if item.status != "RUNNING" or conversation.active_run_id != item.id:
            raise AppError(409, "AGENT_RUN_INACTIVE", "Run was cancelled")
        current_principal(settings, conversation)
        item.output = output
        item.resume_value = None
        if output["status"] == "WAITING_INPUT":
            item.status = "WAITING_INPUT"
            item.interrupt_id = output["interrupt_id"]
            item.question = output["question"]
            item.token_hash = item.token_job_lease = None
        else:
            await repo.append_message(
                session,
                conversation,
                "assistant",
                output["content"],
                item.id,
                output.get("references", []),
            )
            conversation.consumed_trigger = max(
                conversation.consumed_trigger, item.trigger_watermark
            )
            if item.trigger_fingerprint:
                conversation.last_fingerprint = item.trigger_fingerprint
            await repo.close_run(session, conversation, item, "SUCCEEDED")
        return {
            "summary": "Agent paused for input"
            if item.status == "WAITING_INPUT"
            else "Agent response saved",
            "references": scheduler_references(output.get("references", [])),
        }

    async def on_error(session, job, error):
        item = await session.get(AgentRun, job.payload["agent_run_id"])
        conversation = await session.get(
            Conversation, item.conversation_id, with_for_update={"key_share": True}
        )
        await session.refresh(item, with_for_update=True)
        if item.status == "CANCELLED":
            return
        if isinstance(error, AppError) and error.retryable and job.attempt_count < 3:
            return
        await repo.close_run(
            session, conversation, item, "FAILED", getattr(error, "code", "AGENT_EXECUTION_FAILED")
        )

    async def reconcile(db):
        async with db.session() as session, session.begin():
            conversations = (
                await session.scalars(
                    select(Conversation)
                    .join(AgentRun, Conversation.active_run_id == AgentRun.id)
                    .outerjoin(Job, AgentRun.job_id == Job.id)
                    .where(
                        AgentRun.status.in_(["QUEUED", "RUNNING"]),
                        (Job.status.in_(["FAILED", "CANCELLED"])) | Job.id.is_(None),
                    )
                    .with_for_update(of=Conversation, skip_locked=True, key_share=True)
                    .limit(100)
                )
            ).all()
            for conversation in conversations:
                item = await session.get(AgentRun, conversation.active_run_id, with_for_update=True)
                await repo.close_run(session, conversation, item, "FAILED", "AGENT_JOB_TERMINATED")
        from app.agent_bridge.triggers import dispatch_followups

        await dispatch_followups(db, settings)

    return {
        "agent_followup": Handler(
            run, retry_safe=True, apply=apply, on_error=on_error, before_claim=reconcile
        )
    }
