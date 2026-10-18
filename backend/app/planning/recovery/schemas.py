from datetime import timedelta
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Nonnegative, Offer, Positive


class DailyDemand(DTO):
    settlement_at: AwareDatetime
    demand_qty: Nonnegative


class RecoveryArrival(DTO):
    action_id: Identifier
    sku_id: Identifier
    ordered_qty: Positive
    received_qty: Nonnegative
    expected_arrival_at: AwareDatetime | None

    @model_validator(mode="after")
    def remaining(self):
        if self.received_qty > self.ordered_qty:
            raise ValueError("Received quantity exceeds the order")
        return self


class RecoveryInput(DTO):
    solver_version: Literal["recovery_solver_v1"] = "recovery_solver_v1"
    adapter_version: Literal["daily-allocation-v1"] = "daily-allocation-v1"
    store_id: Identifier
    sku_id: Identifier
    on_hand: Nonnegative
    available_cash_minor: Nonnegative
    cash_floor_minor: Nonnegative
    budget_minor: Nonnegative
    max_purchase_qty: Nonnegative | None = None
    daily_demand: list[DailyDemand] = Field(min_length=7, max_length=7)
    demand_source: Literal["user_scenario", "forecast_v6", "simulation"]
    demand_source_id: str | None = None
    arrivals: list[RecoveryArrival] = Field(default_factory=list)
    offers: list[Offer] = Field(max_length=3)
    business_time: AwareDatetime
    evaluated_at: AwareDatetime
    executable: bool
    unresolved_action_id: str | None = None
    completed_purchase_action_id: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        dates = [d.settlement_at for d in self.daily_demand]
        if not self.business_time <= dates[0] < self.business_time + timedelta(days=1):
            raise ValueError("First demand settlement must be within the first business day")
        if any(b - a != timedelta(days=1) for a, b in zip(dates, dates[1:], strict=False)):
            raise ValueError("Demand must contain seven consecutive daily settlements")
        if len({(a.action_id, a.sku_id) for a in self.arrivals}) != len(self.arrivals):
            raise ValueError("Duplicate inbound order")
        if any(a.sku_id != self.sku_id for a in self.arrivals):
            raise ValueError("Inbound SKU does not match recovery scope")
        if len({o.supplier_id for o in self.offers}) != len(self.offers):
            raise ValueError("Duplicate supplier offer")
        return self


class DailyBalance(DailyDemand):
    existing_arrivals: Nonnegative
    proposed_arrivals: Nonnegative
    served_qty: Nonnegative
    lost_qty: Nonnegative
    end_stock: Nonnegative


class RecoveryCandidate(DTO):
    id: Identifier
    supplier_id: Identifier | None
    quantity: Nonnegative
    spend_minor: int
    cash_after_minor: int
    shortage_qty: Nonnegative
    lost_qty: Nonnegative
    end_stock: Nonnegative
    feasible: bool
    executable: bool
    rejection_reasons: list[str]
    daily: list[DailyBalance]


class SolverResult(DTO):
    candidates: list[RecoveryCandidate]
    recommended_candidate_id: str | None
    horizon_tail: list[RecoveryArrival]


class RecoveryProposal(SolverResult):
    id: Identifier
    case_id: Identifier
    revision: Positive
    snapshot_hash: str
    candidate_set_hash: str
    proposal_hash: str
    created_at: AwareDatetime
    expires_at: AwareDatetime


class RecoveryIntent(DTO):
    case_id: Identifier
    revision: Positive
    proposal_id: Identifier
    selected_candidate_id: Identifier
    adopted_by: Identifier
    supplier_override: Identifier
