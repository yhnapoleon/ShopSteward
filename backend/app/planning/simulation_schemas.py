"""Independent comparisons contain no Mission, Plan or purchase authorization."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Nonnegative, Offer, Positive, State
from app.planning.schemas import Candidate, InboundSnapshot, Policy

Quantity = Annotated[int, Field(strict=True, ge=0, le=1000000)]


class QuantitySimulationRequest(DTO):
    expected_state_version: Positive
    sku_id: Identifier
    supplier_id: Identifier
    cash_floor_minor: Annotated[int, Field(strict=True, ge=0, le=10**12)]
    candidate_quantities: list[Quantity] = Field(min_length=2, max_length=20)
    remaining_demand: Quantity | None = None
    horizon_days: Annotated[int, Field(strict=True, ge=1, le=90)] | None = None
    work_item_id: Identifier | None = None
    expected_work_version: Positive | None = None

    @model_validator(mode="after")
    def coherent_comparison(self):
        if 0 not in self.candidate_quantities or len(set(self.candidate_quantities)) != len(
            self.candidate_quantities
        ):
            raise ValueError("候选必须包含不买（0件），且数量不能重复。")
        if (self.remaining_demand is None) != (self.horizon_days is None):
            raise ValueError("自定义需求必须同时给出需求件数和假设期间。")
        if (self.work_item_id is None) != (self.expected_work_version is None):
            raise ValueError("继续试算需要同时提供事项及其当前版本。")
        self.candidate_quantities = sorted(self.candidate_quantities)
        return self


class QuantitySimulationInput(DTO):
    state: State
    sku_id: Identifier
    product_name: str
    policy: Policy
    remaining_demand: Nonnegative
    horizon_start: AwareDatetime
    horizon_end: AwareDatetime
    demand_source: Literal["fixed", "manual", "model", "assumption"]
    forecast_id: str | None
    forecast_version: str | None
    forecast_valid_until: AwareDatetime | None
    offer: Offer
    inbound_items: list[InboundSnapshot]
    eligible_inbound_qty: Nonnegative
    source_sequence: Nonnegative
    source_type: str
    evaluated_at: AwareDatetime
    source_fresh_until: AwareDatetime


class QuantitySimulation(DTO):
    schema_version: Literal["quantity-simulation-v1"] = "quantity-simulation-v1"
    rule_version: str
    input_hash: str
    input: QuantitySimulationInput
    candidates: list[Candidate]
    recommended_candidate_id: str | None
    expected_arrival_at: AwareDatetime | None
    valid_until: AwareDatetime
    request: QuantitySimulationRequest
