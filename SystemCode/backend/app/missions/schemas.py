from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Positive
from app.planning.schemas import Policy

MissionStatus = Literal["ACTIVE", "PAUSED", "COMPLETED", "CANCELLED"]


class Schedule(DTO):
    id: Identifier
    job_type: Literal["check_mission"]
    mission_id: Identifier
    trigger: Literal["INTERVAL"]
    interval_seconds: Annotated[int, Field(strict=True, ge=5, le=3600)]
    enabled: bool
    version: Positive
    next_run_at: AwareDatetime | None


class MissionCreate(DTO):
    store_id: Identifier
    sku_id: Identifier
    objective: str = Field(min_length=1, max_length=2000)
    policy: Policy
    check_interval_seconds: Annotated[int, Field(strict=True, ge=5, le=3600)]


class MissionControl(DTO):
    operation: Literal["pause", "resume", "complete", "cancel"]
    expected_mission_version: Positive


class ScheduleUpdate(DTO):
    interval_seconds: Annotated[int, Field(strict=True, ge=5, le=3600)]
    enabled: Annotated[bool, Field(strict=True)]
    expected_schedule_version: Positive


class Mission(DTO):
    id: Identifier
    store_id: Identifier
    sku_id: Identifier
    objective: str
    status: MissionStatus
    mission_version: Positive
    policy: Policy
    policy_version: str
    schedule: Schedule
    current_plan_id: Identifier | None
    current_action_id: Identifier | None
    completion_criteria: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class MissionList(DTO):
    items: list[Mission]
    next_cursor: str | None


class CheckRequest(DTO):
    reason: str = Field(default="", max_length=1000)


class JobAccepted(DTO):
    job_run_id: Identifier
    status: Literal["READY", "RUNNING", "RETRY_WAIT"]
    merged: bool
