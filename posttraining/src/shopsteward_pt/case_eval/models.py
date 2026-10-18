"""Frozen, strict, deeply immutable records at the offline evaluation boundary.

Observations are produced by trusted fixture/oracle adapters, never inferred from
an assistant's claims. Model output is separately available for semantic review.
"""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(ge=0, strict=True)]
Positive = Annotated[int, Field(ge=1, strict=True)]
Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Scalar = bool | int | float | str | None
DimensionId = Literal["D1", "D2", "D3", "D4", "D5", "D6"]
SourceKind = Literal["business_state", "solver", "tool_receipt", "context", "transport"]
CheckStatus = Literal["pass", "fail", "pending_review", "missing_trace", "not_applicable"]


class FrozenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


def content_hash(value: BaseModel | str) -> str:
    """SHA256 of canonical UTF-8 JSON (including quotes for a text response)."""
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return hashlib.sha256(
        json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def unique(values, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


class Predicate(FrozenRecord):
    check_id: Text
    observation_id: Text
    expected: Scalar
    acceptable_values: tuple[Scalar, ...] = ()
    source_kind: SourceKind
    critical_failure_code: Text | None = None


class SemanticCheck(FrozenRecord):
    check_id: Text
    description: Text
    critical_failure_code: Text | None = None


class DimensionContract(FrozenRecord):
    dimension_id: DimensionId
    applicable: bool
    full_checks: tuple[Text, ...]
    partial_checks: tuple[Text, ...] = ()
    reason: Text

    @model_validator(mode="after")
    def validate_anchor(self) -> Self:
        unique(self.full_checks, "full check")
        unique(self.partial_checks, "partial check")
        if self.applicable != bool(self.full_checks):
            raise ValueError("applicable dimension requires full checks; N/A has none")
        if not self.applicable and self.partial_checks:
            raise ValueError("N/A dimension cannot have partial checks")
        return self


class CaseContract(FrozenRecord):
    schema_version: Literal["case_contract_v1"]
    suite_id: Literal["ce", "ops"]
    case_id: Text
    dataset_version: Text
    task_contract_version: Text
    template_id: Text
    fixture_id: Text
    fixture_hash: Hash
    split: Literal["smoke", "dev", "test"]
    lock_status: Literal["development", "locked"]
    artifact_kind: Literal["example", "recorded"]
    complexity: Literal["simple", "complex"]
    scenario_family: Text
    goal_endpoint: Text
    endpoint_check_id: Text = "endpoint"
    capabilities: tuple[Text, ...]
    allowed_actions: Annotated[tuple[Text, ...], Field(min_length=1)]
    allowed_side_effects: tuple[Text, ...] = ()
    admission_revision: Positive
    required_condition_ids: tuple[Text, ...]
    predicates: tuple[Predicate, ...]
    semantic_checks: tuple[SemanticCheck, ...]
    required_predicates: Annotated[tuple[Text, ...], Field(min_length=1)]
    required_semantic_checks: tuple[Text, ...]
    dimensions: Annotated[tuple[DimensionContract, ...], Field(min_length=6, max_length=6)]
    clarification_required: bool
    followup_expected: bool
    fixture_valid: bool
    invalid_fixture_reason: Text | None

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        predicates = {p.check_id for p in self.predicates}
        semantics = {s.check_id for s in self.semantic_checks}
        ids = [p.check_id for p in self.predicates] + [s.check_id for s in self.semantic_checks]
        unique(ids, "check id")
        if set(ids) & {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}:
            raise ValueError("Q1–Q6 are reserved clarification checks")
        unique([d.dimension_id for d in self.dimensions], "dimension")
        unique(self.required_condition_ids, "condition")
        unique(self.required_predicates, "required predicate")
        unique(self.required_semantic_checks, "required semantic check")
        if (
            not set(self.required_predicates) <= predicates
            or not set(self.required_semantic_checks) <= semantics
        ):
            raise ValueError("required check references an undefined check")
        if self.endpoint_check_id not in self.required_predicates:
            raise ValueError("endpoint predicate must be required")
        for d in self.dimensions:
            if not set(d.full_checks + d.partial_checks) <= predicates | semantics:
                raise ValueError("dimension references an undefined check")
        if self.fixture_valid == (self.invalid_fixture_reason is not None):
            raise ValueError("invalid fixtures require a reason; valid fixtures have none")
        if self.lock_status == "locked" and (
            self.split != "test" or self.artifact_kind == "example"
        ):
            raise ValueError("only real test contracts can be locked")
        if self.split == "test" and self.lock_status != "locked":
            raise ValueError("unlocked development cases cannot be labeled test")
        return self


class Observation(FrozenRecord):
    observation_id: Text
    value: Scalar
    source_kind: SourceKind
    evidence_refs: Annotated[tuple[Text, ...], Field(min_length=1)]


class TraceEvent(FrozenRecord):
    code: Text
    evidence_refs: Annotated[tuple[Text, ...], Field(min_length=1)]


class CallUsage(FrozenRecord):
    call_id: Text
    role: Literal["root", "helper", "expert"]
    status: Literal["completed", "error", "timeout", "rate_limited"]
    input_tokens: Count | None
    output_tokens: Count | None
    reasoning_tokens: Count | None
    cached_input_tokens: Count | None
    cost: Money | None
    currency: Literal["USD"] = "USD"
    retry_of: Text | None = None


class ActionAttempt(FrozenRecord):
    action_id: Text
    name: Text
    authorized_scope: bool
    known_stale_source: bool
    evidence_refs: Annotated[tuple[Text, ...], Field(min_length=1)]


class CaseTrace(FrozenRecord):
    schema_version: Literal["case_trace_v1"]
    case_id: Text
    suite_id: Literal["ce", "ops"]
    fixture_hash: Hash
    case_contract_hash: Hash
    task_contract_version: Text
    run_id: Text
    replicate_id: Positive
    strategy_id: Text
    model_snapshot: Text
    profile_hash: Hash
    prompt_hash: Hash
    builder_version: Text
    solver_version: Text
    adapter_version: Text
    artifact_kind: Literal["example", "recorded"]
    attempted: bool
    trace_complete: bool
    run_status: Literal[
        "completed", "timeout", "rate_limited", "model_error", "environment_error", "not_started"
    ]
    response_text: str | None
    observations: tuple[Observation, ...]
    clarification_questions: tuple[Text, ...]
    followup_received: bool
    decision_errors: tuple[TraceEvent, ...]
    backend_blocks: tuple[TraceEvent, ...]
    actual_side_effects: tuple[TraceEvent, ...]
    actions: tuple[ActionAttempt, ...] = ()
    calls: tuple[CallUsage, ...]
    calls_complete: bool
    active_latency_ms: Count | None
    human_wait_ms: Count | None

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        unique([o.observation_id for o in self.observations], "observation")
        unique([c.call_id for c in self.calls], "call")
        unique([a.action_id for a in self.actions], "action")
        seen: set[str] = set()
        for call in self.calls:
            if call.retry_of is not None and call.retry_of not in seen:
                raise ValueError("retry must refer to an earlier recorded call")
            seen.add(call.call_id)
        if self.attempted == (self.run_status == "not_started"):
            raise ValueError("attempted and run_status disagree")
        return self


class RubricDefinition(FrozenRecord):
    rubric_id: Literal["agent_case_rubric_v1"] = "agent_case_rubric_v1"
    rubric_version: Text = "1.0.0"
    minimum_reviewer_kind: Literal["agent_reviewed", "human_reviewed"] = "agent_reviewed"
    calibration_status: Literal["pilot_uncalibrated", "human_calibrated"] = "pilot_uncalibrated"
    scoring_policy: Literal["required_checks_and_endpoint_no_critical_failure"] = (
        "required_checks_and_endpoint_no_critical_failure"
    )
    anchors_version: Literal["integrated-design-19.13-19.15-v1"] = (
        "integrated-design-19.13-19.15-v1"
    )


class SemanticReview(FrozenRecord):
    case_id: Text
    case_hash: Hash
    trace_hash: Hash
    rubric_hash: Hash
    reviewed_response_hash: Hash
    task_contract_version: Text
    reviewer_kind: Literal["agent_reviewed", "human_reviewed"]
    reviewer_id: Text
    review_version: Text
    check_id: Text
    verdict: Literal["pass", "fail"]
    reason: Text
    evidence_refs: Annotated[tuple[Text, ...], Field(min_length=1)]


class CheckResult(FrozenRecord):
    check_id: Text
    status: CheckStatus
    reason: Text
    evidence_refs: tuple[Text, ...] = ()


class DimensionScore(FrozenRecord):
    dimension_id: DimensionId
    score: Annotated[int, Field(ge=0, le=2, strict=True)] | None
    applicable: bool
    status: Literal["scored", "not_applicable", "pending_review", "missing_trace"]
    reason: Text
    evidence_refs: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def validate_score(self) -> Self:
        if (self.status == "not_applicable") != (not self.applicable):
            raise ValueError("N/A must have applicable=false")
        if (self.status == "scored") != (self.score is not None):
            raise ValueError("only scored dimensions have numerical scores")
        return self


class CaseResult(FrozenRecord):
    schema_version: Literal["case_result_v1"] = "case_result_v1"
    rubric_id: Text
    rubric_version: Text
    rubric_hash: Hash
    case_hash: Hash
    task_contract_version: Text
    suite_id: Literal["ce", "ops"]
    case_id: Text
    fixture_hash: Hash
    dataset_version: Text
    goal_endpoint: Text
    scenario_family: Text
    complexity: Literal["simple", "complex"]
    split: Literal["smoke", "dev", "test"]
    lock_status: Literal["development", "locked"]
    artifact_kind: Literal["example", "recorded"]
    run_id: Text
    replicate_id: Positive
    strategy_id: Text
    model_snapshot: Text
    profile_hash: Hash
    prompt_hash: Hash
    builder_version: Text
    solver_version: Text
    adapter_version: Text
    trace_hash: Hash
    attempted: bool
    evaluation_status: Literal["complete", "pending_review", "missing_trace", "invalid_fixture"]
    dimension_scores: tuple[DimensionScore, ...]
    checks: tuple[CheckResult, ...]
    required_checks: tuple[CheckResult, ...]
    clarification_scores: tuple[CheckResult, ...]
    critical_failures: tuple[Text, ...]
    decision_errors: tuple[TraceEvent, ...]
    backend_blocks: tuple[TraceEvent, ...]
    actual_side_effects: tuple[TraceEvent, ...]
    task_success: bool | None
    review_status: Literal[
        "not_required", "pending_review", "pending_human_review", "human_reviewed"
    ]
    reviews: tuple[SemanticReview, ...]
    cost_status: Literal["known", "partial", "unknown"]
    total_cost: Money | None
    known_cost_subtotal: Money
    calls: tuple[CallUsage, ...]
    calls_complete: bool
    active_latency_ms: Count | None
    human_wait_ms: Count | None
    failure_tags: tuple[Text, ...]
    invalid_fixture_reason: Text | None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        unique([d.dimension_id for d in self.dimension_scores], "dimension score")
        if len(self.dimension_scores) != 6:
            raise ValueError("result requires all six dimensions")
        if self.task_success is True and (
            self.critical_failures
            or any(c.status != "pass" for c in self.required_checks)
            or not self.attempted
        ):
            raise ValueError("success requires all checks, an attempt, and no critical failure")
        if (self.evaluation_status == "invalid_fixture") != (
            self.invalid_fixture_reason is not None
        ):
            raise ValueError("invalid fixture status and reason must agree")
        if self.evaluation_status == "invalid_fixture" and self.task_success is not None:
            raise ValueError("invalid fixtures are excluded, not scored")
        if (self.cost_status == "known") != (self.total_cost is not None):
            raise ValueError("unknown/partial cost cannot be a known total")
        return self
