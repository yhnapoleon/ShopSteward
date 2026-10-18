"""Specification records, distinct from the model-visible PolicyContext."""

from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator
from shopsteward_agent.task_policy.contracts import (
    ActionName,
    Contract,
    Decision,
    DecisionRecord,
    Identifier,
    PolicyContext,
    Quantity,
    ShortText,
    Version,
)

TaskType = Literal[
    "PT-01", "PT-02", "PT-03", "PT-04", "PT-05", "PT-06", "PT-07", "PT-08", "PT-09", "PT-10"
]
Predicate = Literal[
    "receipt_ok",
    "current_plan_unchanged",
    "task_constraints_unchanged",
    "cash_stock_transit_unchanged",
    "no_purchase_created",
    "revision_cap_matches",
    "purchase_within_cap",
    "old_plan_document_preserved",
    "new_plan_pending",
    "policy_unchanged",
    "clarification_relevant",
    "no_mutation_before_reply",
    "no_business_mutation",
    "request_ended",
    "mission_not_cancelled",
    "handoff_recorded",
]
ClarificationSlot = Literal[
    "max_purchase_qty", "valid_quantity", "quantity_semantics", "quantity_unit", "history_reference"
]
SYMBOLS = {
    "plan_id": {"$current_plan_id": "current-plan", "$historical_plan_id": "old-plan"},
    "expected_mission_version": {"$current_mission_version": 1},
}


class ExpectedStep(Contract):
    allowed_actions: Annotated[list[ActionName], Field(min_length=1, max_length=1)]
    arguments: dict[str, Any]
    clarification_slot: ClarificationSlot | None

    @model_validator(mode="after")
    def check_target(self) -> Self:
        name = self.allowed_actions[0]
        if name == "clarify":
            if self.arguments or self.clarification_slot is None:
                raise ValueError("clarify targets require a slot and no exact question arguments")
            return self
        if self.clarification_slot is not None:
            raise ValueError("only clarify targets may specify a clarification slot")
        arguments = dict(self.arguments)
        for key, value in arguments.items():
            if isinstance(value, str) and value.startswith("$"):
                if value not in SYMBOLS.get(key, {}):
                    raise ValueError(f"unknown or misplaced fixture reference: {key}={value}")
                arguments[key] = SYMBOLS[key][value]
        Decision.model_validate({"name": name, "arguments": arguments})
        return self


class HistoryTurn(Contract):
    """Recipe for a prior interaction; E3 must execute it before freezing context."""

    user_message: ShortText
    action: Literal["evaluate_plan", "revise_plan"]
    max_purchase_qty: Quantity | None
    plan_reference: Literal["$current_plan_id", "$historical_plan_id"] = "$current_plan_id"


class Review(Contract):
    reviewer: Identifier
    status: Literal["unreviewed", "agent_reviewed", "human_reviewed"]
    rationale: Annotated[str, Field(min_length=1)]


class EpisodeSpec(Contract):
    episode_id: Identifier
    task_type: TaskType
    scenario_family: Identifier
    split: Literal["train", "dev", "test"]
    suite: Literal["core", "challenge"]
    fixture_recipe: Identifier
    fixture_mission_version: Version = 1
    history: Annotated[list[HistoryTurn], Field(max_length=4)] = Field(default_factory=list)
    user_message: ShortText
    followup_user_message: ShortText | None
    expected_steps: Annotated[list[ExpectedStep], Field(min_length=1, max_length=2)]
    final_predicates: Annotated[list[Predicate], Field(min_length=1)]
    review: Review
    execution_status: Literal["not_run", "verified"] = "not_run"
    known_limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_episode(self) -> Self:
        expected_suite = (
            "core" if self.task_type in {"PT-01", "PT-02", "PT-03", "PT-04"} else "challenge"
        )
        if self.suite != expected_suite:
            raise ValueError(f"{self.task_type} belongs to {expected_suite}")
        if len(set(self.final_predicates)) != len(self.final_predicates):
            raise ValueError("duplicate final predicates")
        has_second = len(self.expected_steps) == 2
        if has_second != (self.followup_user_message is not None):
            raise ValueError("a second target requires exactly one followup user message")
        if has_second and (
            self.expected_steps[0].allowed_actions != ["clarify"]
            or self.expected_steps[1].allowed_actions == ["clarify"]
        ):
            raise ValueError("second decisions are allowed only after one clarification")
        return self


class EpisodeTrace(Contract):
    episode_id: Identifier
    policy_id: Identifier
    mode: Literal["decision", "execution"]
    context: PolicyContext | None = None
    steps: list[DecisionRecord] = Field(default_factory=list)
    step_contexts: list[PolicyContext] = Field(default_factory=list)
    receipts: list[dict[str, Any]] = Field(default_factory=list)
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    state_after_clarify: dict[str, Any] | None = None
    delivery: dict[str, Any] = Field(default_factory=dict)
    environment_error: str | None = None
    timing: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)


class StepScore(Contract):
    expected_action: ActionName
    predicted_action: ActionName | None
    attempted: bool
    expected_tool: bool
    action_correct: bool | None
    arguments_correct: bool | None
    format_valid: bool | None
    clarification_correct: bool | None = None
    argument_errors: list[str] = Field(default_factory=list)


class EpisodeScore(Contract):
    episode_id: Identifier
    policy_id: Identifier
    mode: Literal["decision", "execution"]
    task_type: TaskType
    suite: Literal["core", "challenge"]
    scenario_family: Identifier
    per_step: list[StepScore]
    predicate_results: dict[str, bool | None]
    decision_success: bool | None
    episode_success: bool | None
    failure_tags: list[str]
    review_status: Literal["complete", "pending_review"]
    wrong_write_attempts: int = 0
    unexpected_business_mutation: bool = False
