from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Nonnegative, Offer, Positive, State


class Policy(DTO):
    cash_floor_minor: Nonnegative
    candidate_quantities: list[Nonnegative] = Field(min_length=1, max_length=20)
    supplier_id: Identifier

    @field_validator("candidate_quantities")
    @classmethod
    def unique_sorted(cls, quantities):
        if len(quantities) != len(set(quantities)):
            raise ValueError("Candidate quantities must be unique")
        return sorted(quantities)


class ForecastSnapshot(DTO):
    forecast_id: Identifier
    forecast_version: str = Field(min_length=1)
    store_id: Identifier
    sku_id: Identifier
    remaining_demand: Nonnegative
    unit: Literal["piece"]
    data_as_of: AwareDatetime
    source_sequence: Nonnegative
    horizon_start: AwareDatetime
    horizon_end: AwareDatetime
    valid_until: AwareDatetime
    source: Literal["fixed", "manual", "model"]
    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    assumptions: list[str]


class InboundSnapshot(DTO):
    action_id: Identifier
    sku_id: Identifier
    remaining_quantity: Positive
    expected_arrival_at: AwareDatetime | None
    eligible: bool


class DecisionSnapshot(DTO):
    snapshot_version: Literal["decision-v1"]
    state: State
    mission_version: Positive
    policy: Policy
    task_constraints: dict[Literal["max_purchase_qty"], Nonnegative] = Field(default_factory=dict)
    policy_version: str = Field(min_length=1)
    forecast: ForecastSnapshot
    offer: Offer
    inbound_items: list[InboundSnapshot]
    eligible_inbound_qty: Nonnegative
    rule_version: str = Field(min_length=1)
    evaluated_at: AwareDatetime
    last_successful_sync_at: AwareDatetime
    source_fresh_until: AwareDatetime


class Candidate(DTO):
    id: Identifier
    quantity: Nonnegative
    spend_minor: Annotated[int, Field(strict=True, ge=0)]
    cash_after_minor: Annotated[int, Field(strict=True)]
    shortage_qty: Nonnegative
    feasible: bool
    rejection_reasons: list[str]


class ProposedPurchase(DTO):
    store_id: Identifier
    sku_id: Identifier
    supplier_id: Identifier
    quantity: Positive
    unit_price_minor: Positive
    total_minor: Positive
    currency: Literal["CNY"]
    expected_arrival_at: AwareDatetime


class Plan(DTO):
    id: Identifier
    mission_id: Identifier
    plan_version: Positive
    state_version: Positive
    forecast_version: str
    policy_version: str
    rule_version: str
    status: Literal["PENDING_APPROVAL", "APPROVED", "REJECTED", "SUPERSEDED", "EXPIRED"]
    input_snapshot: DecisionSnapshot
    candidates: list[Candidate] = Field(min_length=1)
    recommended_candidate_id: Identifier | None
    proposal_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    explanation: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    proposed_purchase: ProposedPurchase | None


class PlanList(DTO):
    items: list[Plan]
    next_cursor: str | None


class PlanRevisionRequest(DTO):
    expected_mission_version: Positive
    max_purchase_qty: Annotated[int, Field(strict=True, ge=0, le=1000000)] | None
