from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ConversationCreate(DTO):
    title: str = Field(default="经营对话", min_length=1, max_length=200)
    is_default: bool = False


class MessageCreate(DTO):
    content: str = Field(min_length=1, max_length=8000)


class Resume(DTO):
    interrupt_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=8000)


class Followup(DTO):
    enabled: bool
    interval_seconds: int = Field(default=300, ge=60, le=86400)
    expected_version: int = Field(ge=1)


class KnowledgeChange(DTO):
    kind: Literal["USER", "NOTES", "SKILL"] = "USER"
    task_type: str = Field(default="", max_length=80)
    expected_version: int = Field(ge=0)
    operation: Literal["add", "replace", "remove"] = Field(
        description="新增偏好或scope为空时必须add；replace仅替换已存在entry_id；remove仅删除已存在entry_id。读取偏好不调用此工具。"
    )
    entry_id: str | None = Field(
        default=None,
        max_length=128,
        description="replace/remove必须来自当前knowledge.entries[].id；add省略。不是scope_id或用户消息ID。",
    )
    content: str = Field(default="", max_length=6000)
    source_message_id: str | None = Field(default=None, max_length=128)
    required_tools: list[str] = Field(default_factory=list, max_length=20)


class ToolCall(DTO):
    run_id: str = Field(min_length=1, max_length=128)
    invocation_id: str = Field(min_length=1, max_length=256)
    arguments: dict = Field(default_factory=dict)


class ConversationView(DTO):
    id: str
    principal_id: str
    mission_id: str
    store_id: str
    title: str
    is_default: bool
    active_run_id: str | None
    followup_enabled: bool
    followup_interval: int
    followup_version: int
    created_at: datetime


class ConversationList(DTO):
    items: list[ConversationView]
    next_cursor: str | None


class MessageView(DTO):
    id: str
    conversation_id: str
    seq: int
    role: Literal["user", "assistant"]
    content: str
    run_id: str | None
    references: list[dict]
    created_at: datetime


class MessageList(DTO):
    items: list[MessageView]
    next_after_seq: int | None


class MessageAccepted(DTO):
    message_id: str
    agent_run_id: str
    conversation_id: str


class RunView(DTO):
    id: str
    conversation_id: str
    status: Literal["QUEUED", "RUNNING", "WAITING_INPUT", "SUCCEEDED", "FAILED", "CANCELLED"]
    input_through_seq: int
    trigger: Literal["USER", "FOLLOWUP"]
    graph_version: str
    interrupt_id: str | None
    question: str | None
    output: dict | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
    tools: list[dict] = Field(default_factory=list)


class ResumeAccepted(DTO):
    agent_run_id: str
    message_id: str


class KnowledgeView(DTO):
    id: str
    kind: Literal["USER", "NOTES", "SKILL"]
    task_type: str
    version: int
    entries: list[dict]


class KnowledgeList(DTO):
    items: list[KnowledgeView]


class ToolResult(DTO):
    ok: bool
    data: dict
    references: list[dict]
    error: dict | None = None
