from typing import Literal

from pydantic import AwareDatetime, Field

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Nonnegative, Positive

AlertType = Literal["STOCKOUT_RISK", "CASH_CONSTRAINT", "ACTION_EXCEPTION", "DATA_STALE"]
Severity = Literal["INFO", "WARNING", "CRITICAL"]
AlertStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class AlertFacts(DTO):
    shortage_qty: Nonnegative = Field(default=None)
    cash_floor_minor: Nonnegative = Field(default=None)
    available_cash_minor: Nonnegative = Field(default=None)
    action_id: Identifier = Field(default=None)
    data_as_of: AwareDatetime = Field(default=None)
    reason: str = Field(default=None)


class Alert(DTO):
    id: Identifier
    store_id: Identifier
    mission_id: Identifier | None
    sku_id: Identifier | None
    type: AlertType
    severity: Severity
    status: AlertStatus
    summary: str
    facts: AlertFacts
    state_version: Positive | None
    related_plan_id: Identifier | None
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    resolved_at: AwareDatetime | None


class AlertList(DTO):
    items: list[Alert]
    next_cursor: str | None
