from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Family = Literal[
    "replenishment",
    "cash_constrained",
    "supply_delay_recovery",
    "quotation",
    "execution_verification",
    "business_review",
    "unclassified",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearningScope(Contract):
    principal_id: Identifier
    store_id: Identifier
    source_domain: Literal["simulation", "observed"] = "simulation"


class SourceRef(Contract):
    kind: Identifier
    id: Identifier
    version: int = Field(ge=1, strict=True)
    available_at: AwareDatetime
    digest: str = Field(min_length=1, max_length=64)


class LearningEvent(Contract):
    source_kind: Literal["case", "mission", "run", "work_item", "execution", "knowledge"]
    source_id: Identifier
    source_version: int = Field(ge=1, strict=True)
    event_type: Identifier
    intent_key: str = Field(min_length=1, max_length=256)
    task_family: Family
    observed_at: AwareDatetime
    available_at: AwareDatetime
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def availability(self):
        if self.available_at < self.observed_at:
            raise ValueError("availability precedes observation")
        return self


Nonempty = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=1000)]], Field(min_length=1, max_length=20)
]


class SkillSpec(Contract):
    title: str = Field(min_length=1, max_length=160)
    task_family: Family
    summary: str = Field(min_length=1, max_length=1000)
    inputs: Nonempty
    preconditions: Nonempty
    exclusions: Nonempty
    required_tools: Nonempty
    procedure: Nonempty
    outputs: Nonempty
    exceptions: Nonempty


class PolicyChange(Contract):
    expected_version: int = Field(ge=0, strict=True)
    mode: Literal["off", "suggest", "assist"]


class Transition(Contract):
    expected_version: int = Field(ge=1, strict=True)
    revision: int = Field(ge=1, strict=True)
    action: Literal["shadow", "activate", "suspend", "archive", "revoke", "rollback"]
    evaluation_id: str | None = None


class ForgetRequest(Contract):
    expected_version: int = Field(ge=0, strict=True)
    asset_id: Identifier


class EvaluationRequest(Contract):
    expected_version: int = Field(ge=1, strict=True)
    revision: int = Field(ge=1, strict=True)


class ApplicationFeedback(Contract):
    expected_feedback_version: int = Field(ge=0, strict=True)
    executed: bool = Field(strict=True)
    status: Literal["pass", "fail", "unknown"]
    attribution: Literal[
        "skill_defect",
        "retrieval_mismatch",
        "executor_noncompliance",
        "tool_failure",
        "changed_environment",
        "unresolved",
    ]
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)


class DimensionReview(Contract):
    score: int | None = Field(default=None, ge=0, le=4, strict=True)
    evidence_refs: list[str]
    reason: str = Field(min_length=1)


class QualityReport(Contract):
    binding: dict
    dataset_hash: str = Field(min_length=1)
    baseline: str = Field(min_length=1)
    independent_cases: int = Field(ge=0, strict=True)
    suite_kinds: list[str]
    checks: dict[str, Literal["pass", "fail", "unknown"]]
    scores: dict[str, int | None]
    evidence_refs: list[str]
    reviewed_by: list[str]
    reviewer_kind: Literal["human_reviewed", "model"]
    measured: bool = Field(strict=True)
    evaluated_at: AwareDatetime
    expires_at: AwareDatetime
    quality_delta_lower: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    improvement: float | None = Field(default=None, ge=-1, allow_inf_nan=False)
    target: Literal["corrections_reduction", "tool_calls_reduction", "coverage_gain"]
    dimension_reviews: dict[str, DimensionReview] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded(self):
        if self.expires_at <= self.evaluated_at:
            raise ValueError("invalid report window")
        if any(
            v is not None and (type(v) is not int or not 0 <= v <= 4) for v in self.scores.values()
        ):
            raise ValueError("scores must be integers 0..4 or unknown")
        return self


class LearningView(Contract):
    policy: dict
    progress: dict
    assets: list[dict]
    enabled: bool
