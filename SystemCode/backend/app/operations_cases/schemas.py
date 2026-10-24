from typing import Literal

from pydantic import AwareDatetime, Field

from app.api.schemas import DTO, Identifier
from app.operations.schemas import Nonnegative, Positive
from app.planning.recovery.schemas import DailyDemand, RecoveryProposal


class CaseCreate(DTO):
    mission_id: Identifier
    objective: str = Field(min_length=1, max_length=2000)
    budget_minor: Nonnegative
    max_purchase_qty: Nonnegative | None = None
    # Seven days of demand, read as days 1 to 7 from the business clock when analyzed.
    daily_demand: list[DailyDemand] | None = Field(default=None, min_length=7, max_length=7)
    supplier_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=3)
    # Suppliers the owner does not want asked in this case; neither read nor compared.
    excluded_supplier_ids: list[Identifier] | None = Field(default=None, max_length=20)


class CaseAnalyze(DTO):
    expected_revision: Positive


class CaseRevise(CaseAnalyze):
    objective: str | None = Field(default=None, min_length=1, max_length=2000)
    budget_minor: Nonnegative | None = None
    max_purchase_qty: Nonnegative | None = None
    daily_demand: list[DailyDemand] | None = Field(default=None, min_length=7, max_length=7)
    supplier_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=3)
    excluded_supplier_ids: list[Identifier] | None = Field(default=None, max_length=20)


class CaseSource(CaseAnalyze):
    # Reviewers check each supplier's delivery area against where the store is.
    district: str = Field(default="滨江区", min_length=1, max_length=64)


class CaseMaterialize(CaseAnalyze):
    proposal_id: Identifier
    candidate_id: Identifier
    expected_mission_version: Positive
    expected_state_version: Positive
    expected_current_plan_id: Identifier | None
    proposal_hash: str


class CaseControl(CaseAnalyze):
    operation: Literal["cancel", "adopt_waiting", "refresh", "enable_followup", "disable_followup"]


class CaseEvidence(DTO):
    id: str
    kind: str
    version: str
    status: Literal["verified_source", "user_assumption", "unresolved"]
    summary: str


class CasePurchase(DTO):
    """An emergency purchase the case led to: approved, confirmed by the supplier, arrived."""

    action_id: Identifier
    supplier_id: Identifier
    status: str
    planned_qty: Positive
    accepted_qty: Nonnegative | None
    received_qty: Nonnegative | None


class CaseOutcomePurchase(DTO):
    """What one emergency order brought: ordered, confirmed by the supplier, arrived, paid."""

    action_id: Identifier
    supplier_id: Identifier
    planned_qty: Positive
    purchased_qty: Nonnegative
    received_qty: Nonnegative
    spend_minor: Nonnegative


class CaseOutcome(DTO):
    """What a resolved case achieved; shortage is projected over the analyzed seven days.

    The quantities add up every order of the case; `purchases` gives each one. `path` is
    `waiting` when nothing was bought: the original orders arrived, or with none on the way
    the owner chose not to restock.
    """

    path: Literal["purchase", "waiting"]
    planned_qty: Nonnegative
    purchased_qty: Nonnegative
    received_qty: Nonnegative
    spend_minor: Nonnegative
    lost_qty_before: Nonnegative
    lost_qty_after: Nonnegative
    action_ids: list[Identifier]
    purchases: list[CaseOutcomePurchase] = Field(default_factory=list)


class CaseDetail(DTO):
    id: Identifier
    mission_id: Identifier
    store_id: Identifier
    sku_id: Identifier
    status: str
    current_revision: Positive
    objective: str
    budget_minor: Nonnegative
    max_purchase_qty: Nonnegative | None
    daily_demand: list[DailyDemand] | None
    supplier_ids: list[Identifier] | None = None
    # Who this case leaves out: the owner's choice and the suppliers whose order here
    # declined, failed, was taken back or was filled only in part.
    excluded_supplier_ids: list[Identifier] = Field(default_factory=list)
    proposal: RecoveryProposal | None
    plan_id: Identifier | None
    plan_status: str | None
    plan_revision: Positive | None
    # The order the current plan led to, while it stands; one that bought nothing (declined,
    # withdrawn, failed, void) is no longer the case's order and stays in `purchases`.
    action_id: Identifier | None
    execution_status: str | None
    missing_inputs: list[str]
    evidence: list[CaseEvidence]
    current_mission_version: Positive
    current_state_version: Positive
    current_plan_id: Identifier | None
    stale: bool
    expert_analysis: dict | None
    sourcing: dict | None = None
    followup_enabled: bool
    purchases: list[CasePurchase] = Field(default_factory=list)
    # Set while the owner's decision in this case holds routine checks off the item.
    routine_paused: bool = False
    recheck_reason: str | None = None
    outcome: CaseOutcome | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class CaseList(DTO):
    items: list[CaseDetail]
    next_cursor: str | None = None


class CaseEvent(DTO):
    seq: Positive
    kind: str
    revision: Positive
    payload: dict
    created_at: AwareDatetime


class CaseEvents(DTO):
    items: list[CaseEvent]
