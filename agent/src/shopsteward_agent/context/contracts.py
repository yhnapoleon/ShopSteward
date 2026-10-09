"""Versioned context contracts; no provider credentials or business authority."""

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "context-v1"


class ModelProfile(Contract):
    profile_id: str = "mission-configured"
    version: str = "1"
    provider: str = "openai"
    model_id: str
    api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    reasoning_effort: str | None = None
    reasoning_context_policy: Literal["run_only"] = "run_only"
    max_input_tokens: int = Field(default=24000, gt=0)
    max_output_tokens: int = Field(default=2048, gt=0)
    timeout_s: float = Field(default=30, gt=0)
    capability_flags: list[str] = Field(default_factory=list)
    price_version: str | None = None


class AdmissionBoundary(Contract):
    kind: Literal["mission", "case"] = "mission"
    run_id: str
    conversation_id: str | None = None
    input_through_seq: int = Field(default=0, ge=0)
    admitted_resume_message_ids: list[str] = Field(default_factory=list)
    prior_run_dependencies: list[str] = Field(default_factory=list)
    case_id: str | None = None
    input_revision: int | None = None


class MessageEnvelope(Contract):
    message_id: str
    run_id: str | None = None
    seq: int = Field(ge=0)
    role: Literal["user", "assistant"]
    content: str
    unavailable_reason: Literal["permission", "stale", "source_unavailable"] | None = None


class Constraint(Contract):
    key: str
    operator: Literal["eq", "lte", "gte", "unset"]
    value: Any = None
    unit: str | None = None
    scope: Literal["one_run", "scenario"] = "one_run"
    source_message_id: str
    exact_quote: str
    source_span: tuple[int, int]
    supersedes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_value(self):
        if self.operator == "unset" and self.value is not None:
            raise ValueError("unset cannot have a value")
        if self.operator != "unset" and self.value is None:
            raise ValueError("setting a constraint requires a value")
        return self


class TaskFrame(Contract):
    run_id: str
    frame_id: str = "initial"
    parent_frame_id: str | None = None
    constraints: list[Constraint] = Field(default_factory=list)
    source_message_ids: list[str] = Field(default_factory=list)
    source_digest: str = ""
    validation_status: Literal["raw_fallback", "validated"] = "raw_fallback"
    unresolved: list[str] = Field(default_factory=list)
    requested_effect: Literal["unspecified", "read_only", "write"] = "unspecified"
    effect_source_message_id: str | None = None
    effect_exact_quote: str | None = None
    effect_source_span: tuple[int, int] | None = None
    denied_tools: list[str] = Field(default_factory=list)
    denied_tool_sources: dict[str, dict] = Field(default_factory=dict)


class ModelView(Contract):
    messages: list[dict]
    manifest: dict
    frame: TaskFrame


class CallRecord(Contract):
    """Observer contract. Raw protocol is stored separately from safe manifests."""

    run_id: str
    call_index: int
    segment_id: int = 0
    role: str = "root"
    purpose: str = "task"
    attempt: int = 1
    status: str
    profile: dict
    manifest: dict
    request_hash: str
    returned_model: str | None = None
    response_id: str | None = None
    usage: dict | None = None
    usage_status: Literal["exact", "unknown"] = "unknown"
    cost_status: Literal["unknown"] = "unknown"
    error_code: str | None = None
    duration_ms: int = 0
