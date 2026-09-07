from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Health(DTO):
    status: Literal["ok", "unavailable"]
    component: str


class ErrorDetail(DTO):
    code: str
    message: str
    request_id: Identifier
    retryable: bool
    details: dict


class Error(DTO):
    error: ErrorDetail


class Reference(DTO):
    type: Literal[
        "mission", "plan", "action", "event", "forecast", "artifact", "scenario", "store", "alert"
    ]
    id: Identifier
    version: str = Field(default=None)


class JobResult(DTO):
    summary: str
    references: list[Reference]
    # Optional in JSON, but explicit null is not a valid field value in the design contract.
    check_status: Literal["HEALTHY", "ANOMALY", "INCONCLUSIVE", "SKIPPED"] = Field(default=None)
    input_state_version: int = Field(default=None, ge=1)
    output_state_version: int = Field(default=None, ge=1)


JobType = Literal[
    "worker_probe",
    "sync_events",
    "check_mission",
    "execute_purchase",
    "reconcile_action",
    "check_freshness",
    "agent_followup",
    "initialize_scenario",
    "advance_scenario",
]


class JobRun(DTO):
    id: Identifier
    mission_id: Identifier | None
    job_type: JobType
    trigger_source: Literal["INTERVAL", "AT", "EVENT", "MANUAL", "APPROVAL"]
    status: Literal["READY", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "RETRY_WAIT"]
    attempt_count: int = Field(ge=0)
    scheduled_for: datetime
    available_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: JobResult | None
    error_code: str | None
    last_error: str | None
    request_id: Identifier | None


class SourceStatus(DTO):
    source: str
    last_success_at: datetime | None
    last_sequence: int = Field(ge=0)
    status: Literal["FRESH", "STALE", "UNKNOWN"]
    last_error: str | None


class MonitoringStatus(DTO):
    worker_status: Literal["RUNNING", "STALE", "STOPPED", "UNKNOWN"]
    worker_heartbeat_at: datetime | None
    due_job_count: int = Field(ge=0)
    oldest_due_seconds: int = Field(ge=0)
    sources: list[SourceStatus]
    agent_enabled: bool
    forecast_provider: Literal["fixed", "http"]
