import asyncio
import json
import time
from datetime import timedelta
from uuid import uuid4

from fastapi import Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select, text

from app.agent_bridge import progress
from app.agent_bridge import repository as repo
from app.agent_bridge.models import AgentRun, Conversation, Message, ToolActivity, ToolInvocation
from app.agent_bridge.outcomes import HistoricalEvidence
from app.agent_bridge.schemas import (
    AgentEventPage,
    ConversationCreate,
    ConversationList,
    ConversationView,
    Followup,
    KnowledgeChange,
    KnowledgeList,
    KnowledgeView,
    MessageAccepted,
    MessageCreate,
    MessageList,
    Resume,
    ResumeAccepted,
    RunView,
)
from app.api.dependencies import (
    Id,
    Key,
    Limit,
    User,
    authorize_store,
    require_role,
    require_user,
    visible_mission,
)
from app.api.routing import B0Router, errors
from app.core.errors import AppError
from app.scheduling.models import Job

router = B0Router(tags=["Agent"], responses=errors)
META = {"x-phase": "B2-A", "x-implementation-status": "implemented"}


def enabled(request):
    if not request.app.state.settings.agent_enabled:
        raise AppError(503, "AGENT_NOT_CONFIGURED", "Agent is disabled")


@router.post(
    "/api/v1/missions/{mission_id}/conversations",
    status_code=201,
    response_model=ConversationView,
    operation_id="create_agent_conversation",
    openapi_extra=META,
)
async def create(
    request: Request, principal: User, mission_id: Id, body: ConversationCreate, key: Key
):
    enabled(request)
    async with request.app.state.db.session() as session, session.begin():
        mission = await visible_mission(session, principal, mission_id)
        await session.refresh(mission, with_for_update=True)
        owner = f"conversation:{principal.principal_id}:{mission_id}"
        old = await repo.replay(session, owner, key, body.model_dump())
        if old:
            return repo.conversation_dto(
                await repo.visible_conversation(session, principal, old["id"])
            )
        row = None
        if body.is_default:
            row = await session.scalar(
                select(Conversation).where(
                    Conversation.principal_id == principal.principal_id,
                    Conversation.mission_id == mission_id,
                    Conversation.is_default.is_(True),
                )
            )
        if row is None:
            row = Conversation(
                id=str(uuid4()),
                principal_id=principal.principal_id,
                mission_id=mission_id,
                store_id=mission.store_id,
                **body.model_dump(),
            )
            session.add(row)
            await session.flush()
        repo.receipt(session, owner, key, body.model_dump(), {"id": row.id})
        return repo.conversation_dto(row)


@router.get(
    "/api/v1/missions/{mission_id}/conversations",
    response_model=ConversationList,
    operation_id="list_agent_conversations",
    openapi_extra=META,
)
async def conversations(
    request: Request, principal: User, mission_id: Id, limit: Limit = 20, after: str = ""
):
    async with request.app.state.db.session() as session:
        await visible_mission(session, principal, mission_id)
        rows = (
            await session.scalars(
                select(Conversation)
                .where(
                    Conversation.mission_id == mission_id,
                    Conversation.principal_id == principal.principal_id,
                    Conversation.id > after,
                )
                .order_by(Conversation.id)
                .limit(limit)
            )
        ).all()
        return {
            "items": [repo.conversation_dto(row) for row in rows],
            "next_cursor": rows[-1].id if len(rows) == limit else None,
        }


@router.post(
    "/api/v1/conversations/{conversation_id}/messages",
    status_code=202,
    response_model=MessageAccepted,
    operation_id="send_agent_message",
    openapi_extra=META,
)
async def send(
    request: Request, principal: User, conversation_id: Id, body: MessageCreate, key: Key
):
    enabled(request)
    async with request.app.state.db.session() as session, session.begin():
        conversation = await repo.visible_conversation(
            session, principal, conversation_id, lock=True
        )
        return await repo.send_message(session, conversation, body.content, key)


@router.get(
    "/api/v1/conversations/{conversation_id}/messages",
    response_model=MessageList,
    operation_id="list_agent_messages",
    openapi_extra=META,
)
async def messages(
    request: Request,
    principal: User,
    conversation_id: Id,
    limit: Limit = 20,
    after_seq: int = Query(default=0, ge=0),
):
    async with request.app.state.db.session() as session:
        await repo.visible_conversation(session, principal, conversation_id)
        rows = (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id, Message.seq > after_seq)
                .order_by(Message.seq)
                .limit(limit)
            )
        ).all()
        return {
            "items": [repo.message_dto(row) for row in rows],
            "next_after_seq": rows[-1].seq if len(rows) == limit else None,
        }


async def visible_run(session, principal, run_id, *, lock=False):
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Run is not visible")
    conversation = await repo.visible_conversation(
        session, principal, run.conversation_id, lock=lock
    )
    if lock:
        await session.refresh(run, with_for_update=True)
    return conversation, run


@router.get(
    "/api/v1/agent-runs/{run_id}",
    response_model=RunView,
    operation_id="get_agent_run",
    openapi_extra=META,
)
async def detail(request: Request, principal: User, run_id: Id):
    async with request.app.state.db.session() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        conversation, run = await visible_run(session, principal, run_id)
        result = repo.run_dto(run)
        calls = (
            await session.scalars(
                select(ToolInvocation)
                .where(ToolInvocation.run_id == run.id)
                .order_by(ToolInvocation.created_at)
            )
        ).all()
        result["tools"] = [
            {
                "tool": c.tool,
                "invocation_id": c.invocation_id,
                "ok": c.result.get("ok", True),
                "references": c.result.get("references", []),
            }
            for c in calls
        ]
        activity = (
            await session.scalars(
                select(ToolActivity)
                .where(ToolActivity.run_id == run_id)
                .order_by(ToolActivity.started_at, ToolActivity.invocation_id)
            )
        ).all()
        result["activity"] = [progress.activity_view(row) for row in activity]
        from app.agent_bridge.outcomes import outcomes

        result["outcomes"] = await outcomes(session, conversation, calls)
        return result


@router.post(
    "/api/v1/agent-runs/{run_id}/resume",
    status_code=202,
    response_model=ResumeAccepted,
    operation_id="resume_agent_run",
    openapi_extra=META,
)
async def resume(request: Request, principal: User, run_id: Id, body: Resume, key: Key):
    enabled(request)
    async with request.app.state.db.session() as session, session.begin():
        conversation, run = await visible_run(session, principal, run_id, lock=True)
        old = await repo.replay(session, "resume:" + run.id, key, body.model_dump())
        if old:
            return old
        if run.status != "WAITING_INPUT" or run.interrupt_id != body.interrupt_id:
            raise AppError(409, "INTERRUPT_MISMATCH", "Run is not waiting for this input")
        message = await repo.append_message(session, conversation, "user", body.content, run.id)
        if body.content.strip().lower() in {"取消", "不用了", "算了", "停止", "cancel", "stop"}:
            await repo.close_run(session, conversation, run, "CANCELLED")
        else:
            run.resume_value = body.content
            run.status = "QUEUED"
            await progress.append(session, run, "run.queued", {"status": "QUEUED"})
            await repo.schedule_run(session, conversation, run)
        result = {"agent_run_id": run.id, "message_id": message.id}
        repo.receipt(session, "resume:" + run.id, key, body.model_dump(), result)
        return result


@router.post(
    "/api/v1/agent-runs/{run_id}/cancel",
    response_model=RunView,
    operation_id="cancel_agent_run",
    openapi_extra=META,
)
async def cancel(request: Request, principal: User, run_id: Id, key: Key):
    async with request.app.state.db.session() as session, session.begin():
        conversation, run = await visible_run(session, principal, run_id, lock=True)
        if run.status in {"QUEUED", "RUNNING", "WAITING_INPUT"}:
            if run.job_id:
                job = await session.get(Job, run.job_id, with_for_update=True)
                if job and job.status in {"READY", "RUNNING", "RETRY_WAIT"}:
                    job.status = "CANCELLED"
                    job.lease_token = job.lease_until = None
            await repo.close_run(session, conversation, run, "CANCELLED")
        return repo.run_dto(run)


@router.patch(
    "/api/v1/conversations/{conversation_id}/followup",
    response_model=ConversationView,
    operation_id="configure_agent_followup",
    openapi_extra=META,
)
async def followup(request: Request, principal: User, conversation_id: Id, body: Followup):
    enabled(request)
    require_role(principal, "operator")
    async with request.app.state.db.session() as session, session.begin():
        conversation = await repo.visible_conversation(
            session, principal, conversation_id, lock=True
        )
        if conversation.followup_version != body.expected_version:
            raise AppError(409, "VERSION_CONFLICT", "Follow-up settings changed")
        conversation.followup_enabled = body.enabled
        conversation.followup_interval = body.interval_seconds
        conversation.followup_version += 1
        conversation.next_due = await session.scalar(select(func.clock_timestamp())) + timedelta(
            seconds=body.interval_seconds
        )
        return repo.conversation_dto(conversation)


@router.get(
    "/api/v1/stores/{store_id}/agent-knowledge",
    response_model=KnowledgeList,
    operation_id="list_agent_knowledge",
    openapi_extra=META,
)
async def knowledge_read(request: Request, principal: User, store_id: Id):
    from app.agent_bridge.knowledge import read

    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session:
        return {"items": await read(session, principal.principal_id, store_id)}


@router.post(
    "/api/v1/stores/{store_id}/agent-knowledge",
    response_model=KnowledgeView,
    operation_id="edit_agent_knowledge",
    openapi_extra=META,
)
async def knowledge_write(
    request: Request, principal: User, store_id: Id, body: KnowledgeChange, key: Key
):
    from app.agent_bridge.knowledge import change
    from app.agent_bridge.tools import catalog

    enabled(request)
    authorize_store(principal, store_id)
    async with request.app.state.db.session() as session, session.begin():
        return await change(
            session,
            principal.principal_id,
            store_id,
            body,
            key,
            source={"type": "user_api", "principal_id": principal.principal_id},
            allowed_tools=catalog(principal),
        )


@router.get(
    "/api/v1/agent-runs/{run_id}/events",
    response_model=AgentEventPage,
    operation_id="list_agent_progress_events",
    openapi_extra=META,
)
async def events(
    request: Request,
    principal: User,
    run_id: Id,
    after_seq: int = Query(default=0, ge=0),
    limit: Limit = 100,
):
    return await progress.event_page(request.app.state.db, principal, run_id, after_seq, limit)


@router.get(
    "/api/v1/agent-runs/{run_id}/events/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    operation_id="stream_agent_progress_events",
    openapi_extra=META,
)
async def stream_events(
    request: Request, principal: User, run_id: Id, after_seq: int = Query(default=0, ge=0)
):
    try:
        previous = int(request.headers.get("last-event-id", "0"))
        if previous < 0:
            raise ValueError
        cursor = max(after_seq, previous)
    except ValueError:
        raise AppError(
            422, "INVALID_EVENT_CURSOR", "Event cursor must be a nonnegative integer"
        ) from None
    await progress.event_page(request.app.state.db, principal, run_id, cursor)
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=request.headers.get("authorization", "").partition(" ")[2]
    )

    async def stream():
        after = cursor
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            try:
                current = require_user(request, credentials)
                if current.principal_id != principal.principal_id:
                    raise AppError(401, "UNAUTHENTICATED", "Connection identity changed")
                page = await progress.event_page(request.app.state.db, current, run_id, after)
            except AppError as exc:
                kind = "access_revoked" if exc.status in {401, 403, 404} else "reset"
                yield f"event: {kind}\ndata: " + json.dumps({"code": exc.code}) + "\n\n"
                return
            for item in page.events:
                yield f"id: {item.seq}\nevent: progress\ndata: {item.model_dump_json()}\n\n"
            after = page.next_after_seq
            if page.has_more:
                continue
            yield (
                "event: sync\ndata: "
                + json.dumps(
                    {"run_id": run_id, "latest_seq": page.latest_seq, "status": page.run_status}
                )
                + "\n\n"
            )
            if page.run_status not in {"QUEUED", "RUNNING"}:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/api/v1/agent-runs/{run_id}/evidence",
    response_model=HistoricalEvidence,
    operation_id="get_agent_historical_evidence",
    openapi_extra=META,
)
async def evidence(
    request: Request,
    principal: User,
    run_id: Id,
    id: str = Query(min_length=1, max_length=128),
    version_id: str = Query(min_length=1, max_length=128),
    generation_id: str = Query(min_length=1, max_length=128),
    chunk_id: str = Query(min_length=1, max_length=128),
    metadata_revision: int = Query(ge=1),
    content_sha256: str = Query(pattern=r"^[0-9a-f]{64}$"),
):
    from app.agent_bridge.outcomes import historical_evidence

    async with request.app.state.db.session() as session:
        conversation, run = await visible_run(session, principal, run_id)
        calls = (
            await session.scalars(
                select(ToolInvocation)
                .where(ToolInvocation.run_id == run.id)
                .order_by(ToolInvocation.created_at)
            )
        ).all()
        return await historical_evidence(
            session,
            principal,
            conversation,
            run.id,
            calls,
            {
                "id": id,
                "version_id": version_id,
                "generation_id": generation_id,
                "chunk_id": chunk_id,
                "metadata_revision": metadata_revision,
                "content_sha256": content_sha256,
            },
            request.app.state.settings.knowledge_storage_root,
        )
