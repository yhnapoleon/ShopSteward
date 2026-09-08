from uuid import uuid4

from sqlalchemy import func, select

from app.agent_bridge.models import AgentRun, Conversation, Message, Receipt
from app.api.dependencies import visible_mission
from app.core.errors import AppError
from app.core.hashing import digest
from app.scheduling.repository import enqueue


def fields(row, names):
    return {name: getattr(row, name) for name in names.split()}


def conversation_dto(row):
    return fields(
        row,
        "id principal_id mission_id store_id title is_default active_run_id "
        "followup_enabled followup_interval followup_version created_at",
    )


def message_dto(row):
    return fields(row, "id conversation_id seq role content run_id references created_at")


def run_dto(row):
    return fields(
        row,
        "id conversation_id status input_through_seq trigger graph_version interrupt_id "
        "question output error_code created_at finished_at progress_seq",
    )


async def visible_conversation(session, principal, identifier, *, lock=False):
    row = await session.scalar(
        select(Conversation).where(Conversation.id == identifier).with_for_update(key_share=True)
        if lock
        else select(Conversation).where(Conversation.id == identifier)
    )
    if row is None or row.principal_id != principal.principal_id:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Conversation is not visible")
    await visible_mission(session, principal, row.mission_id)
    return row


async def replay(session, owner, key, content):
    row = await session.get(Receipt, (owner, key))
    if row is not None:
        if row.args_hash != digest(content):
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Key was used with different content")
        return row.result
    return None


def receipt(session, owner, key, content, result):
    session.add(Receipt(owner=owner, key=key, args_hash=digest(content), result=result))


async def append_message(session, conversation, role, content, run_id=None, references=None):
    row = Message(
        id=str(uuid4()),
        conversation_id=conversation.id,
        seq=conversation.next_seq,
        role=role,
        content=content,
        run_id=run_id,
        references=references or [],
    )
    conversation.next_seq += 1
    session.add(row)
    await session.flush()
    return row


async def schedule_run(session, conversation, run):
    job = await enqueue(
        session,
        job_type="agent_followup",
        dedup_key=f"agent:{run.id}:{conversation.next_seq}",
        store_id=conversation.store_id,
        mission_id=conversation.mission_id,
        payload={"agent_run_id": run.id},
    )
    conversation.active_run_id = run.id
    run.job_id = job.id


async def promote(session, conversation):
    if conversation.active_run_id:
        return
    run = await session.scalar(
        select(AgentRun)
        .where(AgentRun.conversation_id == conversation.id, AgentRun.status == "QUEUED")
        .order_by(AgentRun.created_at, AgentRun.id)
        .limit(1)
    )
    if run:
        await schedule_run(session, conversation, run)


async def send_message(session, conversation, content, key):
    owner = "message:" + conversation.id
    value = {"content": content}
    old = await replay(session, owner, key, value)
    if old is not None:
        return old
    run = AgentRun(
        id=str(uuid4()),
        conversation_id=conversation.id,
        input_through_seq=conversation.next_seq,
        status="QUEUED",
    )
    session.add(run)
    await session.flush()
    message = await append_message(session, conversation, "user", content, run.id)
    from app.agent_bridge.progress import append

    await append(session, run, "run.queued", {"status": "QUEUED"})
    await promote(session, conversation)
    result = {"message_id": message.id, "agent_run_id": run.id, "conversation_id": conversation.id}
    receipt(session, owner, key, value, result)
    return result


async def close_run(session, conversation, run, status, error_code=None):
    from app.agent_bridge.progress import append, interrupt_open

    await interrupt_open(session, run, "RUN_" + status)
    run.status = status
    run.error_code = error_code
    run.token_hash = run.token_job_lease = None
    run.finished_at = await session.scalar(select(func.clock_timestamp()))
    if conversation.active_run_id == run.id:
        conversation.active_run_id = None
    await append(
        session,
        run,
        {"SUCCEEDED": "run.completed", "FAILED": "run.failed", "CANCELLED": "run.cancelled"}[
            status
        ],
        {"status": status, "error_code": error_code, "finished_at": run.finished_at.isoformat()},
    )
    await session.flush()
    await promote(session, conversation)
