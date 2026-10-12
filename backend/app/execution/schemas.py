from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Nonnegative, Positive
from app.planning.schemas import ProposedPurchase

Channel = Literal["simulator", "assisted"]


class PlanDecision(DTO):
    decision: Literal["approve", "reject"]
    expected_plan_version: Positive
    expected_state_version: Positive
    proposal_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    # Omitted: the deployment's PURCHASE_CHANNEL decides.
    channel: Channel | None = None


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


class OrderMessage(DTO):
    reference: str
    supplier_id: Identifier
    sku_id: Identifier
    product_name: str
    quantity: Positive
    unit_price_minor: Positive
    total_minor: Positive
    currency: Literal["CNY"]
    requested_delivery_date: date
    text: dict[Literal["zh", "en"], str]
    generated_at: AwareDatetime


class ReplyDifference(DTO):
    field: Literal["quantity", "unit_price_minor", "total_minor"]
    ordered: int
    replied: int


class SupplierReply(DTO):
    text: str
    read_by: Literal["model", "rules"]
    # confirmed and declined close the order; needs_attention leaves it waiting.
    outcome: Literal["confirmed", "declined", "needs_attention"]
    decision: Literal["accepted", "rejected", "unclear"]
    quantity: int | None
    unit_price_minor: int | None
    total_minor: int | None
    delivery_date: date | None
    supplier_order_ref: str | None
    quotes: dict[str, str]
    differences: list[ReplyDifference]
    recorded_at: AwareDatetime
    recorded_by: Identifier


class SupplierReplyText(DTO):
    text: str = Field(min_length=1, max_length=4000)


class Action(DTO):
    id: Identifier
    mission_id: Identifier
    plan_id: Identifier
    approval_id: Identifier
    status: Literal["QUEUED", "EXECUTING", "SUCCEEDED", "FAILED", "UNKNOWN", "STALE", "CANCELLED"]
    channel: Channel
    order_message: OrderMessage | None
    supplier_reply: SupplierReply | None
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
