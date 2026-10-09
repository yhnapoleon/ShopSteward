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
    daily_demand: list[DailyDemand] | None = Field(default=None, min_length=7, max_length=7)
    supplier_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=3)


class CaseAnalyze(DTO):
    expected_revision: Positive


class CaseRevise(CaseAnalyze):
    objective: str | None = Field(default=None, min_length=1, max_length=2000)
    budget_minor: Nonnegative | None = None
    max_purchase_qty: Nonnegative | None = None
    daily_demand: list[DailyDemand] | None = Field(default=None, min_length=7, max_length=7)
    supplier_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=3)


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
    proposal: RecoveryProposal | None
    plan_id: Identifier | None
    plan_status: str | None
    plan_revision: Positive | None
    action_id: Identifier | None
    execution_status: str | None
    missing_inputs: list[str]
    evidence: list[CaseEvidence]
    current_mission_version: Positive
    current_state_version: Positive
    current_plan_id: Identifier | None
    stale: bool
    expert_analysis: dict | None
    followup_enabled: bool
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
