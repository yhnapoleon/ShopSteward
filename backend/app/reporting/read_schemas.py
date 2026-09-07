from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.api.schemas import DTO, Identifier
from app.execution.schemas import Action
from app.operations.schemas import Nonnegative, Positive, State
from app.reporting.schemas import Freshness

SignedInt64 = Annotated[int, Field(strict=True, ge=-9223372036854775807, le=9223372036854775807)]
Cursor = Annotated[str, Field(min_length=1, max_length=2048)]
Role = Literal["viewer", "operator", "approver", "admin"]


class CurrentUser(DTO):
    principal_id: Identifier
    roles: list[Role] = Field(json_schema_extra={"uniqueItems": True})
    store_scope: Literal["ALL", "ASSIGNED"]

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Roles must be unique")
        return value


class StoreSummary(DTO):
    store_id: Identifier
    currency: Literal["CNY"]
    source_type: Literal["simulation"]
    simulation_time: AwareDatetime | None


class StoreList(DTO):
    items: list[StoreSummary]
    next_cursor: Cursor | None
    active_store: StoreSummary | None = None


class ReadContext(DTO):
    store_id: Identifier
    currency: Literal["CNY"]
    state_version: Positive
    as_of: AwareDatetime
    simulation_time: AwareDatetime | None
    source_sequence: Nonnegative | None
    freshness: Freshness


class SaleRecord(DTO):
    event_id: Identifier
    sequence: Positive
    sku_id: Identifier
    quantity: Positive
    unit_price_minor: Positive
    sales_amount_minor: Positive
    occurred_at: AwareDatetime
    simulation_time: AwareDatetime


class SaleBucket(DTO):
    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime
    record_count: Nonnegative
    recorded_quantity: Nonnegative
    recorded_sales_amount_minor: Nonnegative


class SaleSummary(DTO):
    context: ReadContext
    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime
    time_basis: Literal["simulation_time"]
    timezone: Literal["UTC"]
    granularity: Literal["day"]
    coverage: Literal["RECORDED_EVENTS_ONLY"]
    record_count: Nonnegative
    recorded_quantity: Nonnegative
    recorded_sales_amount_minor: Nonnegative
    buckets: list[SaleBucket] = Field(max_length=91)


class SaleList(DTO):
    context: ReadContext
    items: list[SaleRecord]
    next_cursor: Cursor | None


class ActionList(DTO):
    context: ReadContext
    items: list[Action]
    next_cursor: Cursor | None


class InboundItem(DTO):
    action_id: Identifier
    mission_id: Identifier
    sku_id: Identifier
    external_order_id: Identifier | None
    ordered_quantity: Positive
    received_quantity: Nonnegative
    remaining_quantity: Nonnegative
    expected_arrival_at: AwareDatetime | None
    arrival_status: Literal["NOT_RECEIVED", "PARTIALLY_RECEIVED", "RECEIVED"]
    is_overdue: bool | None

    @model_validator(mode="after")
    def coherent_quantities(self):
        if self.received_quantity + self.remaining_quantity != self.ordered_quantity:
            raise ValueError("Inbound quantities are inconsistent")
        expected = (
            "NOT_RECEIVED"
            if self.received_quantity == 0
            else "RECEIVED"
            if self.remaining_quantity == 0
            else "PARTIALLY_RECEIVED"
        )
        if self.arrival_status != expected:
            raise ValueError("Inbound status is inconsistent")
        if expected == "RECEIVED" and self.is_overdue is not False:
            raise ValueError("A received inbound is not overdue")
        return self


class InboundList(DTO):
    context: ReadContext
    items: list[InboundItem]
    next_cursor: Cursor | None


class LedgerChanges(DTO):
    cash_delta_minor: SignedInt64
    receivables_delta_minor: SignedInt64
    on_hand_delta: SignedInt64
    in_transit_delta: SignedInt64


class LedgerEntryView(DTO):
    id: Identifier
    state_version: Positive
    effect_type: Literal[
        "INIT", "PURCHASE_ACCEPTED", "GOODS_RECEIVED", "SALE_RECORDED", "DEMAND_REVISED"
    ]
    sku_id: Identifier | None
    action_id: Identifier | None
    source_event_id: Identifier | None
    occurred_at: AwareDatetime | None
    simulation_time: AwareDatetime | None
    changes: LedgerChanges | None
    opening_state: State | None
    remaining_demand_after: Nonnegative | None

    @model_validator(mode="after")
    def effect_shape(self):
        if self.effect_type == "INIT":
            if self.changes is not None or self.opening_state is None or self.sku_id is not None:
                raise ValueError("INIT requires an opening state only")
        elif self.changes is None or self.opening_state is not None or self.sku_id is None:
            raise ValueError("Non-INIT effects require changes and a SKU")
        if (self.effect_type == "DEMAND_REVISED") != (self.remaining_demand_after is not None):
            raise ValueError("Only demand revisions contain remaining demand")
        return self


class LedgerEntryList(DTO):
    context: ReadContext
    items: list[LedgerEntryView]
    next_cursor: Cursor | None
