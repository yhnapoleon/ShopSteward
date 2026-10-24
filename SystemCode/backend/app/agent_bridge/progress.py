"""Durable public progress. Payloads contain no prompts, arguments, or lease credentials."""

import hashlib
import re
import secrets

from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.agent_bridge import repository as repo
from app.agent_bridge.models import AgentRun, Conversation, RunEvent, ToolActivity, ToolInvocation
from app.agent_bridge.schemas import AgentEvent, AgentEventPage, ToolActivityView
from app.core.errors import AppError
from app.core.hashing import digest


def activity_view(row):
    return ToolActivityView.model_validate(row).model_dump(mode="json")


async def append(session, run, kind, payload, invocation_id=None):
    # Callers own the run row lock (or are creating this run in their transaction).
    run.progress_seq = (run.progress_seq or 0) + 1
    event = RunEvent(
        run_id=run.id,
        seq=run.progress_seq,
        type=kind,
        invocation_id=invocation_id,
        payload=payload,
        created_at=await session.scalar(select(func.clock_timestamp())),
    )
    session.add(event)
    await session.flush()


async def finish(session, run, row, status, *, references=None, error_code=None):
    if row.status != "RUNNING":
        return
    now = await session.scalar(select(func.clock_timestamp()))
    row.status = status
    row.finished_at = now
    row.duration_ms = max(0, int((now - row.started_at).total_seconds() * 1000))
    row.references = references or []
    row.error_code = error_code
    await append(
        session,
        run,
        {"SUCCEEDED": "tool.completed", "FAILED": "tool.failed", "INTERRUPTED": "tool.interrupted"}[
            status
        ],
        {"activity": activity_view(row)},
        row.invocation_id,
    )


async def interrupt_open(session, run, reason):
    rows = (
        await session.scalars(
            select(ToolActivity).where(
                ToolActivity.run_id == run.id, ToolActivity.status == "RUNNING"
            )
        )
    ).all()
    for row in rows:
        await finish(session, run, row, "INTERRUPTED", error_code=reason)


async def start_tool(request, name, body, token):
    """Commit admission before tool work; never hold this transaction over execution/HTTP."""
    from app.agent_bridge.document_evidence import DEFINITIONS as DOCUMENT_DEFINITIONS
    from app.agent_bridge.jobs import assert_lease, current_principal
    from app.agent_bridge.tools import DEFINITIONS, DOCUMENT_TOOLS, catalog
    from app.missions.repository import lock_mission
    from app.scheduling.models import Job
    from app.scheduling.repository import owned

    settings = request.app.state.settings
    async with request.app.state.db.session() as session, session.begin():
        run = await session.get(AgentRun, body.run_id)
        if run is None or not secrets.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(), run.token_hash or ""
        ):
            raise AppError(401, "INVALID_AGENT_TOKEN", "Current run credential required")
        conversation = await session.get(Conversation, run.conversation_id)
        principal = current_principal(settings, conversation)
        if name not in catalog(principal, settings):
            raise AppError(403, "TOOL_NOT_ALLOWED", "Tool is not authorized for this user")
        definitions = DOCUMENT_DEFINITIONS if name in DOCUMENT_TOOLS else DEFINITIONS
        try:
            definitions[name][0].model_validate(body.arguments)
        except ValidationError:
            raise AppError(
                422, "INVALID_TOOL_ARGUMENTS", "Arguments do not match this tool schema"
            ) from None
        # Match the existing tool fence: store -> mission -> run -> job.
        await lock_mission(session, conversation.mission_id)
        await session.refresh(run, with_for_update=True)
        await session.refresh(conversation)
        job = await session.scalar(select(Job).where(*owned(run.job_id, run.token_job_lease)))
        if (
            job is None
            or run.status != "RUNNING"
            or conversation.active_run_id != run.id
            or not secrets.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), run.token_hash or ""
            )
        ):
            raise AppError(401, "INVALID_AGENT_TOKEN", "Run credential expired or was revoked")
        await assert_lease(session, job)
        signature = digest([name, body.arguments])
        cached = await session.get(ToolInvocation, (run.id, body.invocation_id))
        if cached:
            if cached.args_hash != signature:
                raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Tool invocation arguments changed")
            return
        started_at = await session.scalar(select(func.clock_timestamp()))
        row = await session.get(ToolActivity, (run.id, body.invocation_id))
        lease = hashlib.sha256((run.token_job_lease or "").encode()).hexdigest()
        if row:
            if row.args_hash != signature:
                raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Tool invocation arguments changed")
            if row.status == "RUNNING" and row.lease_fingerprint == lease:
                return  # Concurrent transport retry, not another logical tool start.
            if row.status == "RUNNING":
                await finish(session, run, row, "INTERRUPTED", error_code="WORKER_RESTARTED")
            row.attempt += 1
        else:
            row = ToolActivity(
                run_id=run.id,
                invocation_id=body.invocation_id,
                tool=name,
                args_hash=signature,
                attempt=1,
            )
            session.add(row)
        row.lease_fingerprint = lease
        row.status = "RUNNING"
        row.started_at = started_at
        row.finished_at = row.duration_ms = row.error_code = None
        row.references = []
        await append(
            session, run, "tool.started", {"activity": activity_view(row)}, row.invocation_id
        )


async def complete_tool(session, run, invocation_id, result):
    # Called inside the SAME transaction as the persistent result / business mutation.
    row = await session.get(ToolActivity, (run.id, invocation_id))
    if row is None:
        return  # Legacy/direct invocation without progress, still readable in tools[].
    code = str((result.get("error") or {}).get("code") or "TOOL_FAILED")
    if not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
        code = "TOOL_FAILED"
    await finish(
        session,
        run,
        row,
        "SUCCEEDED" if result.get("ok") else "FAILED",
        references=result.get("references", []),
        error_code=None if result.get("ok") else code,
    )


async def interrupted_tool(request, body, token):
    async with request.app.state.db.session() as session, session.begin():
        run = await session.get(AgentRun, body.run_id, with_for_update=True)
        if (
            run is None
            or run.status != "RUNNING"
            or not secrets.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), run.token_hash or ""
            )
        ):
            return
        row = await session.get(ToolActivity, (run.id, body.invocation_id))
        if row:
            await finish(session, run, row, "INTERRUPTED", error_code="TOOL_EXECUTION_INTERRUPTED")


async def event_page(db, principal, run_id, after_seq, limit=100):
    async with db.session() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Run is not visible")
        await repo.visible_conversation(session, principal, run.conversation_id)
        watermark = run.progress_seq
        if after_seq > watermark:
            raise AppError(
                409, "EVENT_CURSOR_AHEAD", "Reload the run snapshot before resuming progress"
            )
        rows = (
            await session.scalars(
                select(RunEvent)
                .where(
                    RunEvent.run_id == run_id,
                    RunEvent.seq > after_seq,
                    RunEvent.seq <= watermark,
                )
                .order_by(RunEvent.seq)
                .limit(limit)
            )
        ).all()
        events = [
            AgentEvent(
                event_id=f"{run_id}:{r.seq}",
                run_id=run_id,
                seq=r.seq,
                at=r.created_at,
                type=r.type,
                invocation_id=r.invocation_id,
                payload=r.payload,
            )
            for r in rows
        ]
        cursor = rows[-1].seq if rows else after_seq
        return AgentEventPage(
            run_id=run_id,
            events=events,
            latest_seq=watermark,
            next_after_seq=cursor,
            has_more=cursor < watermark,
            run_status=run.status,
        )
