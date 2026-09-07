from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "agent_conversations"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(128))
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    title: Mapped[str] = mapped_column(String(200), default="经营对话")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active_run_id: Mapped[str | None] = mapped_column(String(128))
    next_seq: Mapped[int] = mapped_column(BigInteger, default=1)
    followup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    followup_interval: Mapped[int] = mapped_column(BigInteger, default=300)
    followup_version: Mapped[int] = mapped_column(BigInteger, default=1)
    next_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fingerprint: Mapped[str | None] = mapped_column(String(64))
    consumed_trigger: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    __table_args__ = (
        Index(
            "uq_agent_default",
            "principal_id",
            "mission_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("agent_conversations.id"), index=True)
    input_through_seq: Mapped[int] = mapped_column(BigInteger)
    trigger: Mapped[str] = mapped_column(String(24), default="USER")
    trigger_watermark: Mapped[int] = mapped_column(BigInteger, default=0)
    trigger_fingerprint: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED")
    job_id: Mapped[str | None] = mapped_column(ForeignKey("job_runs.id", ondelete="SET NULL"))
    graph_version: Mapped[str] = mapped_column(String(40), default="agent-v1")
    resume_value: Mapped[str | None] = mapped_column(Text)
    interrupt_id: Mapped[str | None] = mapped_column(String(128))
    question: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[str | None] = mapped_column(String(64))
    token_job_lease: Mapped[str | None] = mapped_column(String(128))
    output: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "agent_messages"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("agent_conversations.id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    references: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq"),
        Index("uq_agent_final", "run_id", unique=True, postgresql_where=text("role = 'assistant'")),
    )


class Receipt(Base):
    __tablename__ = "agent_receipts"
    owner: Mapped[str] = mapped_column(String(256), primary_key=True)
    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    args_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)


class ToolInvocation(Base):
    __tablename__ = "agent_tool_calls"
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), primary_key=True)
    invocation_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    tool: Mapped[str] = mapped_column(String(64))
    args_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class Trigger(Base):
    __tablename__ = "agent_triggers"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("agent_conversations.id"))
    source_key: Mapped[str] = mapped_column(String(256))
    references: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    __table_args__ = (UniqueConstraint("conversation_id", "source_key"),)


class KnowledgeScope(Base):
    __tablename__ = "agent_knowledge_scopes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(128))
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    kind: Mapped[str] = mapped_column(String(16))
    task_type: Mapped[str] = mapped_column(String(80), default="")
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    entries: Mapped[list] = mapped_column(JSONB, default=list)
    __table_args__ = (
        UniqueConstraint("principal_id", "store_id", "kind", "task_type"),
        {"schema": "agent_data"},
    )


class KnowledgeRevision(Base):
    __tablename__ = "agent_knowledge_revisions"
    __table_args__ = {"schema": "agent_data"}
    scope_id: Mapped[str] = mapped_column(
        ForeignKey("agent_data.agent_knowledge_scopes.id"), primary_key=True
    )
    version: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entries: Mapped[list] = mapped_column(JSONB)
    source: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
