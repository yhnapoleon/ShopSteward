from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.agent_bridge.models import KnowledgeRevision, KnowledgeScope
from app.agent_bridge.repository import receipt, replay
from app.core.errors import AppError
from app.core.hashing import digest


def dto(scope):
    return {
        "id": scope.id,
        "kind": scope.kind,
        "task_type": scope.task_type,
        "version": scope.version,
        "entries": scope.entries,
    }


async def read(session, principal_id, store_id):
    scopes = (
        await session.scalars(
            select(KnowledgeScope)
            .where(KnowledgeScope.principal_id == principal_id, KnowledgeScope.store_id == store_id)
            .order_by(KnowledgeScope.kind, KnowledgeScope.task_type)
        )
    ).all()
    return [dto(scope) for scope in scopes]


async def change(session, principal_id, store_id, body, key, *, source, allowed_tools):
    from shopsteward_agent.memory.hermes_policy import apply_memory_changes

    if body.kind == "SKILL" and not body.task_type:
        raise AppError(422, "SKILL_TASK_REQUIRED", "Task skills require a task type")
    if body.kind != "SKILL" and (body.task_type or body.required_tools):
        raise AppError(
            422, "INVALID_MEMORY_SCOPE", "Only skills have task type and tool requirements"
        )
    if not set(body.required_tools) <= set(allowed_tools):
        raise AppError(422, "SKILL_TOOL_UNAVAILABLE", "Skill requires an unavailable tool")
    scope_id = digest([principal_id, store_id, body.kind, body.task_type])
    await session.execute(
        insert(KnowledgeScope)
        .values(
            id=scope_id,
            principal_id=principal_id,
            store_id=store_id,
            kind=body.kind,
            task_type=body.task_type,
            version=0,
            entries=[],
        )
        .on_conflict_do_nothing()
    )
    scope = await session.get(KnowledgeScope, scope_id, with_for_update=True)
    old = await replay(session, "knowledge:" + scope_id, key, body.model_dump())
    if old is not None:
        return old
    if scope.version != body.expected_version:
        raise AppError(
            409, "VERSION_CONFLICT", "Knowledge changed; read current version before editing"
        )
    entries = [dict(entry) for entry in scope.entries]
    target = next((entry for entry in entries if entry["id"] == body.entry_id), None)
    if body.operation != "add" and target is None:
        raise AppError(
            404,
            "MEMORY_ENTRY_NOT_FOUND",
            "没有该偏好条目。若当前scope为空，保存新偏好请使用operation=add，expected_version取当前scope版本；不要向用户索要内部ID。",
        )
    content = body.content.strip()
    if body.operation != "remove" and not content:
        raise AppError(422, "EMPTY_KNOWLEDGE", "Knowledge cannot be empty")
    if body.operation == "remove":
        entries.remove(target)
    elif body.operation == "replace":
        target.update(content=content, required_tools=body.required_tools)
    elif not any(entry["content"] == content for entry in entries):
        entries.append(
            {"id": str(uuid4()), "content": content, "required_tools": body.required_tools}
        )
    if body.kind != "SKILL":
        # Stable IDs select edits; Hermes normalizes duplicates and checks final budget.
        # Never reintroduce substring ambiguity after an unambiguous ID selection.
        try:
            resulting = apply_memory_changes(
                [], [{"action": "add", "content": e["content"]} for e in entries], body.kind
            )
        except ValueError as exc:
            raise AppError(422, "MEMORY_CHANGE_REJECTED", str(exc)) from None
        entries = [entry for entry in entries if entry["content"] in resulting]
        entries = list({entry["content"]: entry for entry in entries}.values())
    if body.kind == "SKILL" and (
        sum(len(e["content"]) for e in entries) > 6000 or len(entries) > 12
    ):
        raise AppError(422, "SKILL_BUDGET_EXCEEDED", "Task skill scope exceeds budget")
    if entries != scope.entries:
        scope.entries = entries
        scope.version += 1
        session.add(
            KnowledgeRevision(
                scope_id=scope.id, version=scope.version, entries=entries, source=source
            )
        )
    result = dto(scope)
    receipt(session, "knowledge:" + scope_id, key, body.model_dump(), result)
    return result
