"""Model-independent intake contract. Business writes retain their own APIs."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.agent_bridge.schemas import DTO
from app.missions.schemas import Mission, MissionCreate, MissionList
from app.operations.schemas import Catalog
from app.reporting.schemas import Dashboard

WorkStatus = Literal[
    "RECEIVED", "PROCESSING", "WAITING_INPUT", "RESULT_READY", "BLOCKED", "COMPLETED", "CANCELLED"
]


class WorkInput(DTO):
    content: str = Field(min_length=1, max_length=8000)

    @model_validator(mode="after")
    def not_blank(self):
        if not self.content.strip():
            raise ValueError("Content must not be blank")
        return self


class WorkCreate(WorkInput):
    store_id: str = Field(min_length=1, max_length=128)


class WorkEvidence(DTO):
    type: Literal["store", "mission", "plan", "action"]
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)


class WorkResult(DTO):
    kind: Literal["answer", "analysis", "forecast", "quotation", "brief"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=16000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    references: list[WorkEvidence] = Field(default_factory=list, max_length=20)
    # Structured tables are presentation data, never a replacement for the ledger.
    columns: list[str] = Field(default_factory=list, max_length=12)
    rows: list[list[str]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def table_shape(self):
        if any(
            len(row) != len(self.columns) or any(len(v) > 1000 for v in row) for row in self.rows
        ):
            raise ValueError("Table rows must match columns, with bounded cells")
        return self


class WorkMessage(DTO):
    id: str
    item_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    demonstration: bool = False
    result: WorkResult | None = None


class WorkView(DTO):
    id: str
    store_id: str
    principal_id: str
    title: str
    status: WorkStatus
    version: int
    summary: str
    next_step: str
    question: str | None
    result: WorkResult | None
    mission_id: str | None
    mission_request: MissionCreate | None
    demonstration: bool
    processor_available: bool
    processing_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    mission: Mission | None = None


class WorkDetail(DTO):
    item: WorkView
    messages: list[WorkMessage]


class WorkList(DTO):
    items: list[WorkView]
    next_cursor: str | None
    processor_available: bool


class WorkVersion(DTO):
    expected_version: int = Field(ge=1)


class WorkControl(WorkVersion):
    operation: Literal["cancel", "retry"]


class WorkClaim(WorkVersion):
    lease_seconds: int = Field(default=120, ge=30, le=300)


class WorkContext(DTO):
    work: WorkDetail
    catalog: Catalog
    dashboard: Dashboard
    missions: MissionList


class WorkLease(DTO):
    processing_token: str
    work: WorkDetail


class WorkUpdate(WorkVersion):
    processing_token: str = Field(min_length=20, max_length=128)
    status: Literal["PROCESSING", "WAITING_INPUT", "RESULT_READY", "BLOCKED", "COMPLETED"]
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    next_step: str = Field(default="", max_length=1000)
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=16000)
    result: WorkResult | None = None
    link_mission_id: str | None = Field(default=None, max_length=128)
    mission_request: MissionCreate | None = None
    demonstration: bool = False

    @model_validator(mode="after")
    def meaningful_state(self):
        if self.status == "WAITING_INPUT" and not self.question:
            raise ValueError("Waiting for input requires a question")
        if self.status in {"RESULT_READY", "COMPLETED"} and not self.result:
            raise ValueError("Delivery requires a durable result")
        if self.status == "BLOCKED" and not self.next_step:
            raise ValueError("A blocked item requires an actionable next step")
        if self.link_mission_id and self.mission_request:
            raise ValueError("Link or propose a mission, not both")
        if self.mission_request and self.status != "RESULT_READY":
            raise ValueError("A mission proposal requires a ready result")
        return self
