"""Durable context records in the existing receipt store.

Every access resolves the actual AgentRun -> Conversation owner. Namespace keys
are an application mapping, not new foreign keys; a dedicated-table migration
can preserve these payloads later. No prompts or opaque reasoning are exposed.
"""

from sqlalchemy import select

from app.agent_bridge.models import AgentRun, Receipt
from app.agent_bridge.repository import visible_conversation
from app.core.errors import AppError
from app.core.hashing import digest


def owner(run_id):
    return "context:" + run_id


def configured_profile(settings):
    return {
        "profile_id": settings.agent_profile_id,
        "version": "1",
        "model_id": settings.agent_model,
        "api_mode": settings.agent_api_mode,
        "reasoning_effort": settings.agent_reasoning_effort,
        "max_input_tokens": settings.agent_max_input_tokens,
        "max_output_tokens": settings.agent_max_output_tokens,
        "timeout_s": settings.agent_model_timeout_seconds,
    }


async def freeze_config(session, run, settings):
    row = await session.get(Receipt, (owner(run.id), "config"))
    if row is not None:
        return row.result
    enabled = settings.agent_context_enabled and run.status == "QUEUED" and run.output is None
    config = {
        "schema_version": "context-config-v1",
        "enabled": enabled,
        "builder_version": "context-builder-v1",
        "profile": configured_profile(settings),
    }
    session.add(Receipt(owner=owner(run.id), key="config", args_hash=digest(config), result=config))
    return config


async def save_call(session, run_id, record):
    # Caller has validated current principal/lease and locked the AgentRun.
    key = f"call:{record['role']}:{record['call_index']}"
    row = await session.get(Receipt, (owner(run_id), key))
    request_hash = record["request_hash"]
    if row is None:
        session.add(Receipt(owner=owner(run_id), key=key, args_hash=request_hash, result=record))
    elif row.args_hash != request_hash:
        raise AppError(409, "CONTEXT_CALL_CONFLICT", "Reserved model request has changed")
    elif record["status"] == "reserved":
        raise AppError(
            409,
            "CONTEXT_CALL_ALREADY_SENT",
            "Model call outcome already exists or is unknown; an uncounted replay is forbidden",
        )
    else:
        row.result = record


async def inspect_context(session, principal, run_id):
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "Run is not visible")
    await visible_conversation(session, principal, run.conversation_id)
    rows = (await session.scalars(select(Receipt).where(Receipt.owner == owner(run_id)))).all()
    config = next((row.result for row in rows if row.key == "config"), None)
    calls = sorted(
        [row.result for row in rows if row.key.startswith("call:")],
        key=lambda value: (value["call_index"], value["role"]),
    )
    frame = (run.output or {}).get("context_frame")
    return {
        "run_id": run_id,
        "config": config,
        "frames": [frame] if frame else [],
        "calls": calls,
        "manifests": [call["manifest"] for call in calls if call.get("manifest")],
    }
