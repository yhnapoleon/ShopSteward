"""Strict public input contract: complete contiguous integer sales only."""

from datetime import date, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str, Field(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
]


class HistoryDay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    sold_quantity: Annotated[StrictInt, Field(ge=0, le=1_000_000_000)]
    complete: StrictBool

    @field_validator("date", mode="before")
    @classmethod
    def iso_date(cls, value):
        if isinstance(value, date) and type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("DATE_MUST_BE_YYYY_MM_DD")
        return date.fromisoformat(value)

    @field_validator("complete")
    @classmethod
    def complete_required(cls, value):
        if not value:
            raise ValueError("COMPLETE_HISTORY_REQUIRED")
        return value


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_id: Identifier
    sku_id: Identifier
    series_id: Identifier
    history: Annotated[list[HistoryDay], Field(min_length=84, max_length=374)]
    observation_end_date: date
    timezone: Annotated[str, Field(strict=True, min_length=1, max_length=64)] = "UTC"
    input_state_version: Annotated[StrictInt, Field(ge=0)]

    _date = field_validator("observation_end_date", mode="before")(HistoryDay.iso_date.__func__)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("UNKNOWN_TIMEZONE") from exc
        return value

    @model_validator(mode="after")
    def causal_history(self):
        if self.history[-1].date != self.observation_end_date:
            raise ValueError("HISTORY_MUST_END_AT_OBSERVATION_DATE")
        if self.observation_end_date < date(1900, 1, 1) or self.observation_end_date > date(
            2200, 1, 1
        ):
            raise ValueError("OBSERVATION_DATE_OUT_OF_RANGE")
        if any(
            b.date - a.date != timedelta(days=1) for a, b in zip(self.history, self.history[1:])
        ):
            raise ValueError("ASCENDING_CONTIGUOUS_HISTORY_REQUIRED")
        return self
