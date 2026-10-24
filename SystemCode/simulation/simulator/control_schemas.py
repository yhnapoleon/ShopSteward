"""Typed manual source changes; deliberately no arbitrary event or cash injection."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from simulator.schemas import (
    DTO,
    BusinessEvent,
    Identifier,
    Nonnegative,
    ScenarioCreate,
    ScenarioRun,
    State,
)

Quantity = Annotated[int, Field(strict=True, ge=1, le=10**6)]


class TimedTrigger(DTO):
    expected_sequence: Nonnegative
    advance_seconds: Annotated[int, Field(strict=True, ge=0, le=604800)] = 0


class SaleTrigger(TimedTrigger):
    kind: Literal["sale"]
    quantity: Quantity
    unit_price_minor: Annotated[int, Field(strict=True, ge=1, le=10**8)]


class DemandTrigger(TimedTrigger):
    kind: Literal["demand"]
    remaining_demand: Annotated[int, Field(strict=True, ge=0, le=10**6)]


class ReceiptTrigger(DTO):
    kind: Literal["receipt"]
    expected_sequence: Nonnegative
    action_id: Identifier
    quantity: Quantity | None = None


TriggerRequest = Annotated[
    SaleTrigger | DemandTrigger | ReceiptTrigger, Field(discriminator="kind")
]


class TriggerResult(DTO):
    scenario_run_id: Identifier
    first_sequence: Nonnegative
    last_sequence: Nonnegative
    simulation_time: AwareDatetime
    before: State
    after: State
    events: list[BusinessEvent]


class RunSummary(DTO):
    scenario_run_id: Identifier
    store_id: Identifier
    scenario: Literal["SC01", "SANDBOX"]
    label: str
    created_at: AwareDatetime
    simulation_time: AwareDatetime
    last_sequence: Nonnegative


class RunList(DTO):
    items: list[RunSummary]
    next_cursor: str | None


class OrderSummary(DTO):
    action_id: Identifier
    status: Literal["ACCEPTED", "REJECTED", "PENDING"]
    quantity: Nonnegative
    received_quantity: Nonnegative
    remaining_quantity: Nonnegative
    eta: AwareDatetime | None
    total_minor: Nonnegative


class RunDetail(RunSummary):
    state: State
    initial_snapshot: ScenarioRun
    configuration: ScenarioCreate
    step_index: Nonnegative
    orders: list[OrderSummary]
