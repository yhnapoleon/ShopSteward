from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from app.api.schemas import DTO, Identifier


class HistoryDay(DTO):
    date: date
    sold_quantity: Annotated[int, Field(strict=True, ge=0, le=1000000000)]
    complete: StrictBool


class ForecastV6Refresh(DTO):
    sku_id: Identifier
    series_id: Identifier | None = None
    mode: Literal["observed", "historical_demo"] | None = None
    history: list[HistoryDay] | None = Field(default=None, min_length=84, max_length=374)
    observation_end_date: date | None = None
    activate_for_planning: StrictBool = False

    @model_validator(mode="after")
    def complete_history(self):
        if self.history is not None:
            validate_history(self.history, self.observation_end_date)
        if self.mode == "historical_demo" and self.activate_for_planning:
            raise ValueError("Historical demonstration cannot be activated for planning")
        return self


def validate_history(history, cutoff):
    if not 84 <= len(history) <= 374:
        raise ValueError("Import 84 to 374 complete consecutive daily observations")
    if cutoff is None or history[-1].date != cutoff:
        raise ValueError("Observation end date must equal the final imported date")
    if any(not row.complete for row in history):
        raise ValueError("Incomplete observations cannot be inferred as zero sales")
    if any(
        b.date != a.date + timedelta(days=1) for a, b in zip(history, history[1:], strict=False)
    ):
        raise ValueError("History must be in date order with no gaps or duplicates")


class ForecastV6Model(DTO):
    model_version: str
    feature_profile: str
    minimum_history_days: int
    recommended_history_days: int
    weights: dict
    evaluation: dict
    supported_series: list[dict]
    limitations: list[str]


class ForecastV6Current(DTO):
    status: Literal["READY", "STALE", "UNAVAILABLE"]
    reason: str | None
    store_id: str
    sku_id: str
    mode: Literal["observed", "historical_demo"] | None
    usable_for_planning: bool
    activate_for_planning: bool = False
    forecast: dict | None
    history: list[dict]
    model: dict | None
