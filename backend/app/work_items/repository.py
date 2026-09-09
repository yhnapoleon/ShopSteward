"""Durable intake, optimistic handoff and links; no intent classifier or model calls."""

import hashlib
import secrets
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, tuple_, update

from app.api.dependencies import authorize_store, require_role, visible_mission
from app.core.errors import AppError
from app.core.pagination import decode_cursor, encode_cursor
from app.execution.models import ActionRow
from app.missions import repository as missions
from app.missions.models import MissionRow, PlanRow
from app.missions.schemas import MissionCreate
from app.work_items.models import WorkItem, WorkMessageRow
from app.work_items.schemas import WorkDetail, WorkMessage, WorkView


def unavailable():
    return AppError(404, "RESOURCE_NOT_FOUND", "Work item is not visible")


async def visible(session, principal, identifier, *, service=False, lock=False):
    row = await session.get(WorkItem, identifier)
    if row is None or (not service and row.principal_id != principal.principal_id):
        raise unavailable()
    authorize_store(principal, row.store_id)
    if lock:
        # Same ordering as the existing business boundary: store first.
        await missions.lock_store(session, row.store_id)
        await session.refresh(row)
    if row.canonical_id:
        row = await session.get(WorkItem, row.canonical_id)
    if lock:
        await session.refresh(row, with_for_update=True)
    return row


def current_owner(settings, row):
    for grant in settings.auth_tokens:
        if grant.kind == "user" and grant.principal_id == row.principal_id:
            try:
                authorize_store(grant, row.store_id)
                return grant
            except AppError:
                continue
    raise AppError(403, "WORK_OWNER_REVOKED", "The originating user no longer has access")


def check_version(row, expected):
    if row.version != expected:
        raise AppError(409, "WORK_VERSION_CONFLICT", "事项已有新进展或补充，请读取后继续。")


def release(row):
    row.processing_hash = row.processing_owner = row.processing_expires_at = None


async def changed(session, row):
    row.version += 1
    row.updated_at = await session.scalar(select(func.clock_timestamp()))


async def append(session, row, role, content, *, result=None, demonstration=False):
    session.add(
        WorkMessageRow(
            id=str(uuid4()),
            item_id=row.id,
            role=role,
            content=content,
            result=result,
            demonstration=demonstration,
        )
    )
    await session.flush()


async def view(session, row, settings):
    data = {
        k: getattr(row, k)
        for k in WorkView.model_fields
        if k not in {"mission", "processor_available"}
    }
    return WorkView(
        **data,
        processor_available=settings.work_processor_enabled,
        mission=await missions.read_mission(session, row.mission_id) if row.mission_id else None,
    )


async def detail(session, row, settings):
    members = select(WorkItem.id).where(or_(WorkItem.id == row.id, WorkItem.canonical_id == row.id))
    messages = list(
        await session.scalars(
            select(WorkMessageRow)
            .where(WorkMessageRow.item_id.in_(members))
            .order_by(WorkMessageRow.created_at, WorkMessageRow.id)
        )
    )
    return WorkDetail(
        item=await view(session, row, settings),
        messages=[WorkMessage.model_validate(m) for m in messages],
    )


async def create(session, principal, body, key, settings):
    authorize_store(principal, body.store_id)
    await missions.lock_store(session, body.store_id)
    receipt, replay = await missions.command(
        session, principal.principal_id, "work_create", key, body.model_dump()
    )
    if replay:
        return await detail(
            session, await visible(session, principal, receipt.response["id"]), settings
        )
    row = WorkItem(
        id=str(uuid4()),
        principal_id=principal.principal_id,
        store_id=body.store_id,
        title=body.content.strip()[:80],
        next_step="等待助手处理；你可以继续补充要求。",
    )
    session.add(row)
    await session.flush()
    await append(session, row, "user", body.content)
    receipt.response = {"id": row.id}
    return await detail(session, row, settings)


async def send(session, principal, identifier, body, key, settings):
    row = await visible(session, principal, identifier, lock=True)
    receipt, replay = await missions.command(
        session,
        principal.principal_id,
        "work_message",
        key,
        {"item_id": identifier, **body.model_dump()},
    )
    if not replay:
        await append(session, row, "user", body.content)
        row.status = "RECEIVED"
        row.question = row.mission_request = None
        row.next_step = "新要求已保存，等待助手结合之前的内容继续处理。"
        release(row)
        await changed(session, row)
        receipt.response = {"id": row.id}
    return await detail(session, row, settings)


async def listing(session, principal, store_id, cursor, limit, settings):
    authorize_store(principal, store_id)
    scope = ["work_items", principal.principal_id, store_id]
    anchor = decode_cursor(cursor, scope)
    query = select(WorkItem).where(
        WorkItem.store_id == store_id,
        WorkItem.principal_id == principal.principal_id,
        WorkItem.canonical_id.is_(None),
    )
    if anchor:
        query = query.where(tuple_(WorkItem.created_at, WorkItem.id) < anchor)
    rows = list(
        await session.scalars(
            query.order_by(WorkItem.created_at.desc(), WorkItem.id.desc()).limit(limit + 1)
        )
    )
    return {
        "items": [await view(session, row, settings) for row in rows[:limit]],
        "next_cursor": encode_cursor(scope, rows[limit - 1]) if len(rows) > limit else None,
        "processor_available": settings.work_processor_enabled,
    }


async def from_mission(session, principal, mission_id, settings):
    mission = await visible_mission(session, principal, mission_id)
    await missions.lock_store(session, mission.store_id)
    row = await session.scalar(
        select(WorkItem).where(
            WorkItem.principal_id == principal.principal_id, WorkItem.mission_id == mission_id
        )
    )
    if row is None:
        row = WorkItem(
            id=str(uuid4()),
            principal_id=principal.principal_id,
            store_id=mission.store_id,
            title=mission.objective[:200],
            mission_id=mission.id,
            status="RESULT_READY",
            summary="原备货安排继续保留，采购和到货状态以业务记录为准。",
        )
        session.add(row)
        await session.flush()
        await append(session, row, "system", "已接回原备货事项。原方案、采购及到货记录保持关联。")
    return await detail(session, row, settings)


async def link(session, row, mission_id, owner):
    mission = await visible_mission(session, owner, mission_id)
    if mission.store_id != row.store_id or (row.mission_id and row.mission_id != mission_id):
        raise AppError(409, "WORK_SCOPE_CONFLICT", "不能把已关联的事项换到另一项备货工作。")
    target = await session.scalar(
        select(WorkItem).where(
            WorkItem.principal_id == row.principal_id,
            WorkItem.mission_id == mission_id,
            WorkItem.id != row.id,
        )
    )
    if target:
        # Retain both histories in place; aliases resolve to one card, with no message copy.
        await session.execute(
            update(WorkItem).where(WorkItem.canonical_id == row.id).values(canonical_id=target.id)
        )
        row.canonical_id = target.id
        row.mission_request = None
        release(row)
        target.status = "RECEIVED"
        target.question = target.mission_request = None
        target.next_step = "已接回原事项，等待助手结合补充要求继续。"
        release(target)
        await changed(session, row)
        await changed(session, target)
        await append(session, target, "system", "从新入口提出的要求已接回本事项，原对话保留。")
        return target
    row.mission_id = mission_id
    return row


async def accept_mission(session, principal, identifier, body, key, settings):
    require_role(principal, "operator")
    row = await visible(session, principal, identifier, lock=True)
    receipt, replay = await missions.command(
        session,
        principal.principal_id,
        "work_accept",
        key,
        {"item_id": identifier, **body.model_dump()},
    )
    if replay:
        return await detail(session, row, settings)
    check_version(row, body.expected_version)
    if (
        row.demonstration
        or row.status != "RESULT_READY"
        or not row.mission_request
        or row.mission_id
    ):
        raise AppError(409, "WORK_NOT_READY", "当前没有可建立的真实备货委托。")
    request = MissionCreate.model_validate(row.mission_request)
    if request.store_id != row.store_id:
        raise AppError(409, "WORK_SCOPE_CONFLICT", "Store mismatch")
    mission = await missions.create_mission(
        session, request, principal.principal_id, "work:" + row.id
    )
    row.mission_id = mission.id
    row.mission_request = None
    row.status = "RESULT_READY"
    row.next_step = "备货委托已建立，等待业务检查；每笔采购仍需单独确认。"
    release(row)
    await changed(session, row)
    await append(session, row, "system", row.next_step)
    receipt.response = {"id": row.id}
    return await detail(session, row, settings)


async def control(session, principal, identifier, body, key, settings):
    row = await visible(session, principal, identifier, lock=True)
    receipt, replay = await missions.command(
        session,
        principal.principal_id,
        "work_control",
        key,
        {"item_id": identifier, **body.model_dump()},
    )
    if not replay:
        check_version(row, body.expected_version)
        if body.operation == "retry" and row.status not in {
            "BLOCKED",
            "CANCELLED",
            "PROCESSING",
            "RECEIVED",
        }:
            raise AppError(409, "WORK_NOT_RETRYABLE", "当前无需重试，可以直接补充要求。")
        if (
            body.operation == "retry"
            and row.processing_expires_at
            and row.processing_expires_at > await session.scalar(select(func.clock_timestamp()))
        ):
            raise AppError(409, "WORK_BUSY", "助手仍在处理，可补充要求或停止本轮处理。")
        row.status = "CANCELLED" if body.operation == "cancel" else "RECEIVED"
        row.question = row.mission_request = None
        row.next_step = (
            "本轮处理已停止；已建立的备货跟进和采购不受此操作影响。"
            if body.operation == "cancel"
            else "等待重新处理，已保存的内容仍可查看。"
        )
        release(row)
        await changed(session, row)
        await append(session, row, "system", row.next_step)
        receipt.response = {"id": row.id}
    return await detail(session, row, settings)


async def claim(session, service, identifier, body, key, settings):
    require_role(service, "operator")
    if not settings.work_processor_enabled:
        raise AppError(503, "WORK_PROCESSOR_DISABLED", "Work processor is not connected")
    row = await visible(session, service, identifier, service=True, lock=True)
    current_owner(settings, row)
    receipt, replay = await missions.command(
        session,
        service.principal_id,
        "work_claim",
        key,
        {"item_id": identifier, **body.model_dump()},
    )
    if replay:
        return receipt.response
    check_version(row, body.expected_version)
    now = await session.scalar(select(func.clock_timestamp()))
    if row.status not in {"RECEIVED", "PROCESSING"} or (
        row.processing_expires_at and row.processing_expires_at > now
    ):
        raise AppError(409, "WORK_BUSY", "Work is not available for processing")
    token = secrets.token_urlsafe(32)
    row.processing_hash = hashlib.sha256(token.encode()).hexdigest()
    row.processing_owner = service.principal_id
    row.processing_expires_at = now + timedelta(seconds=body.lease_seconds)
    row.status = "PROCESSING"
    row.next_step = "助手正在处理；你可以继续补充或停止本轮处理。"
    await changed(session, row)
    result = {
        "processing_token": token,
        "work": (await detail(session, row, settings)).model_dump(mode="json"),
    }
    receipt.response = result
    return result


async def publish(session, service, identifier, body, key, settings):
    require_role(service, "operator")
    row = await visible(session, service, identifier, service=True, lock=True)
    owner = current_owner(settings, row)
    receipt, replay = await missions.command(
        session,
        service.principal_id,
        "work_update",
        key,
        {"item_id": identifier, **body.model_dump()},
    )
    if replay:
        return await detail(session, row, settings)
    check_version(row, body.expected_version)
    now = await session.scalar(select(func.clock_timestamp()))
    if (
        row.status != "PROCESSING"
        or row.processing_owner != service.principal_id
        or not row.processing_hash
        or not secrets.compare_digest(
            row.processing_hash, hashlib.sha256(body.processing_token.encode()).hexdigest()
        )
        or not row.processing_expires_at
        or row.processing_expires_at <= now
    ):
        raise AppError(409, "WORK_LEASE_LOST", "Processing lease expired or was superseded")
    if body.demonstration and settings.app_env == "production":
        raise AppError(403, "DEMO_NOT_ALLOWED", "Demonstration updates are disabled in production")
    if body.mission_request and row.mission_id:
        raise AppError(409, "WORK_SCOPE_CONFLICT", "已关联备货的事项不能再提出新委托。")
    if body.mission_request and body.mission_request.store_id != row.store_id:
        raise AppError(409, "WORK_SCOPE_CONFLICT", "Mission proposal must use the same store")
    if body.result:
        for ref in body.result.references:
            if ref.type == "store":
                valid = ref.id == row.store_id
            elif ref.type == "mission":
                value = await session.get(MissionRow, ref.id)
                valid = value is not None and value.store_id == row.store_id
            elif ref.type == "plan":
                value = await session.get(PlanRow, ref.id)
                mission = await session.get(MissionRow, value.mission_id) if value else None
                valid = mission is not None and mission.store_id == row.store_id
            else:
                value = await session.get(ActionRow, ref.id)
                valid = value is not None and value.store_id == row.store_id
            if not valid:
                raise AppError(
                    422, "WORK_EVIDENCE_INVALID", "Result reference is outside the store"
                )
    if body.link_mission_id:
        target = await link(session, row, body.link_mission_id, owner)
        if target.id != row.id:
            receipt.response = {"id": target.id}
            return await detail(session, target, settings)
    if body.status == "COMPLETED" and row.mission_id:
        raise AppError(
            409,
            "BUSINESS_COMPLETION_REQUIRED",
            "助手回答完成不能结束备货事项，请使用RESULT_READY。",
        )
    row.status = body.status
    row.title = body.title or row.title
    row.summary, row.next_step, row.question = body.summary, body.next_step, body.question
    row.mission_request = (
        body.mission_request.model_dump(mode="json") if body.mission_request else None
    )
    # A progress/question update must not relabel an older simulated result as real.
    if body.result or row.result is None:
        row.demonstration = body.demonstration
    if body.result:
        row.result = body.result.model_dump(mode="json")
    if body.answer or body.question or body.result:
        await append(
            session,
            row,
            "assistant",
            body.answer or body.question or body.result.content,
            result=body.result.model_dump(mode="json") if body.result else None,
            demonstration=body.demonstration,
        )
    if body.status == "PROCESSING":
        row.processing_expires_at = now + timedelta(seconds=120)
    else:
        release(row)
    await changed(session, row)
    receipt.response = {"id": row.id}
    return await detail(session, row, settings)
