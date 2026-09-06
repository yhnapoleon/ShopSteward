from typing import Literal

from pydantic import AwareDatetime

from app.api.schemas import DTO, Identifier, Reference
from app.operations.schemas import Nonnegative, State


class Freshness(DTO):
    status: Literal["FRESH", "STALE", "UNKNOWN"]
    data_as_of: AwareDatetime | None
    last_sync_at: AwareDatetime | None


class Dashboard(DTO):
    state: State
    freshness: Freshness
    active_mission_count: Nonnegative
    active_alert_count: Nonnegative
    last_check_at: AwareDatetime | None
    next_check_at: AwareDatetime | None


class TimelineEntry(DTO):
    id: Identifier
    mission_id: Identifier
    type: str
    summary: str
    actor_type: Literal["USER", "SERVICE", "SYSTEM"]
    actor_id: Identifier | None
    references: list[Reference]
    created_at: AwareDatetime


class TimelineEntryList(DTO):
    items: list[TimelineEntry]
    next_cursor: str | None
