"""Explicit adapter for shopsteward_agent.context.contracts.CallRecord v1.

The caller must provide the complete event stream for the task tree. We cannot
discover absent child calls or business effects from model transport metadata.
"""

from .models import CallUsage, FrozenRecord


class RuntimeUsage(FrozenRecord):
    calls: tuple[CallUsage, ...]
    calls_complete: bool


def adapt_runtime_calls(
    records: tuple, *, role_map: dict[str, str] | None = None, ledger_complete: bool = True
) -> RuntimeUsage:
    from shopsteward_agent.context.contracts import CallRecord

    roles = {"root": "root", "helper": "helper", "expert": "expert", **(role_map or {})}
    latest = {}
    terminals = {"completed", "failed", "incomplete"}
    for record in records:
        if not isinstance(record, CallRecord):
            raise TypeError("adapter requires validated context CallRecord instances")
        if record.schema_version != "context-v1":
            raise ValueError("unsupported runtime CallRecord schema version")
        if record.status not in terminals | {"reserved"}:
            raise ValueError(f"unsupported runtime call status: {record.status}")
        if record.role not in roles or roles[record.role] not in {"root", "helper", "expert"}:
            raise ValueError(f"explicit role mapping required for {record.role}")
        key = (record.run_id, record.role, record.call_index)
        previous = latest.get(key)
        if previous is not None and previous.status in terminals:
            if record.status == "reserved":
                raise ValueError("reserved update cannot follow terminal record")
            if previous.model_dump() != record.model_dump():
                raise ValueError("conflicting terminal records for one runtime call")
        latest[key] = record
    calls = []
    complete = ledger_complete
    for key, record in latest.items():
        if record.status == "reserved":
            complete = False
        usage = record.usage if record.usage_status == "exact" and record.usage is not None else {}
        input_detail = usage.get("input_token_details") or {}
        output_detail = usage.get("output_token_details") or {}
        if not isinstance(input_detail, dict) or not isinstance(output_detail, dict):
            raise ValueError("runtime token details must be typed mappings")
        calls.append(
            CallUsage(
                call_id=":".join(str(value) for value in key),
                role=roles[record.role],
                status="completed"
                if record.status == "completed"
                else "timeout"
                if record.error_code == "TimeoutError"
                else "error",
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                reasoning_tokens=output_detail.get("reasoning"),
                cached_input_tokens=input_detail.get("cache_read"),
                cost=None,
            )
        )
    return RuntimeUsage(calls=tuple(calls), calls_complete=complete)
