from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.agent_bridge.schemas import DTO

SortBy = Literal["unit_price", "source"]


class QuoteUpload(DTO):
    expected_work_version: int = Field(ge=1)
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200000)


class QuoteCorrection(DTO):
    record: int = Field(ge=1, le=100)
    field: str = Field(min_length=1, max_length=80)
    value: str = Field(max_length=1000)


class QuoteProcessArgs(DTO):
    file_id: str = Field(min_length=1, max_length=128)
    base_result_id: str | None = Field(default=None, max_length=128)
    rule_version: int | None = Field(default=None, ge=0)
    corrections: list[QuoteCorrection] = Field(default_factory=list, max_length=800)
    sort_by: SortBy | None = None


class QuoteProcess(QuoteProcessArgs):
    expected_work_version: int = Field(ge=1)
    persist_rule: bool = False
    expected_rule_version: int | None = Field(default=None, ge=0)
    correction_content: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def persistent_rule_version(self):
        if self.persist_rule and self.expected_rule_version is None:
            raise ValueError("expected_rule_version is required to save a rule")
        return self


class QuoteFile(DTO):
    id: str
    work_id: str
    filename: str
    sha256: str
    size_bytes: int
    created_at: datetime


class QuoteFiles(DTO):
    items: list[QuoteFile]


class QuoteRule(DTO):
    scope_id: str
    version: int
    sort_by: SortBy
    source: dict
    validated: bool = True


class QuoteRuleState(DTO):
    version: int
    rule: QuoteRule | None


class QuoteRow(DTO):
    record: int
    product: str
    price: str | None
    pack: str | None
    moq: str | None
    moq_unit: str
    unit: str
    currency: str
    source: str
    unit_price: str | None
    moq_pieces: str | None
    basis: str


class QuoteResult(DTO):
    id: str
    work_id: str
    file_id: str
    filename: str
    version: int
    input_sha256: str
    calculation_version: str = "quotation-decimal-v1"
    sort_by: SortBy
    rows: list[QuoteRow]
    issues: list[str]
    rule: QuoteRule | None
    corrections: list[QuoteCorrection]
    correction_content: str
    created_at: datetime


class QuoteResults(DTO):
    items: list[QuoteResult]


class QuoteRuleRemove(DTO):
    expected_work_version: int = Field(ge=1)
    expected_rule_version: int = Field(ge=0)
    operation: Literal["remove"]
    correction_content: str = Field(default="取消长期报价规则", min_length=1, max_length=8000)
