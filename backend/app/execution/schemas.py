from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Nonnegative, Positive
from app.planning.schemas import ProposedPurchase


class PlanDecision(DTO):
    decision: Literal["approve", "reject"]
    expected_plan_version: Positive
    expected_state_version: Positive
    proposal_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class DecisionApproved(DTO):
    plan_id: Identifier
    decision: Literal["approve"]
    action_id: Identifier
    job_run_id: Identifier


class DecisionRejected(DTO):
    plan_id: Identifier
    decision: Literal["reject"]
    action_id: None
    job_run_id: None


class PurchaseRequest(DTO):
    action_id: Identifier
    scenario_run_id: Identifier
    store_id: Identifier
    sku_id: Identifier
    supplier_id: Identifier
    quantity: Positive
    expected_total_minor: Positive
    currency: Literal["CNY"]


class PurchaseReceipt(DTO):
    action_id: Identifier
    status: Literal["ACCEPTED", "REJECTED", "PENDING"]
    external_order_id: Identifier | None
    quantity: Nonnegative
    total_minor: Nonnegative
    currency: Literal["CNY"]
    recorded_at: AwareDatetime
    reason: str | None

    @model_validator(mode="after")
    def evidence(self):
        if self.status == "ACCEPTED" and (
            not self.external_order_id or not self.quantity or not self.total_minor
        ):
            raise ValueError("Acceptance requires order, quantity and amount")
        if self.status == "REJECTED" and not self.reason:
            raise ValueError("Rejection requires a reason")
        return self


class Action(DTO):
    id: Identifier
    mission_id: Identifier
    plan_id: Identifier
    approval_id: Identifier
    status: Literal["QUEUED", "EXECUTING", "SUCCEEDED", "FAILED", "UNKNOWN", "STALE", "CANCELLED"]
    quantity: Positive
    amount_minor: Nonnegative
    currency: Literal["CNY"]
    external_order_id: Identifier | None
    receipt: PurchaseReceipt | None
    last_error: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    purchase_snapshot: ProposedPurchase


class ScenarioAdvance(DTO):
    steps: int = Field(strict=True, ge=1, le=100)


class AdvanceResult(DTO):
    scenario_run_id: Identifier
    simulation_time: AwareDatetime
    last_sequence: Nonnegative
