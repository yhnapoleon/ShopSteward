from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.api.schemas import DTO, Identifier

Nonnegative = Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]
Positive = Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]


class Product(DTO):
    sku_id: Identifier
    name: str
    unit: Literal["piece"]


class Offer(DTO):
    supplier_id: Identifier
    sku_id: Identifier
    unit_price_minor: Positive
    minimum_order_quantity: Positive
    pack_size: Positive
    offer_version: str = Field(min_length=1)
    currency: Literal["CNY"]
    lead_time_seconds: Nonnegative
    valid_from: AwareDatetime
    valid_until: AwareDatetime

    @model_validator(mode="after")
    def interval(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("Offer validity interval must be positive")
        return self


class Catalog(DTO):
    store_id: Identifier
    currency: Literal["CNY"]
    products: list[Product]
    offers: list[Offer]


class Stock(DTO):
    sku_id: Identifier
    on_hand: Nonnegative
    in_transit: Nonnegative
    remaining_demand: Nonnegative | None
    forecast_version: str | None


class State(DTO):
    store_id: Identifier
    state_version: Positive
    currency: Literal["CNY"]
    cash_minor: Nonnegative
    reserved_cash_minor: Nonnegative
    available_cash_minor: Nonnegative
    receivables_minor: Nonnegative
    stocks: list[Stock]
    data_as_of: AwareDatetime | None
    simulation_time: AwareDatetime | None

    @model_validator(mode="after")
    def available(self):
        if self.available_cash_minor != self.cash_minor - self.reserved_cash_minor:
            raise ValueError("Available cash must equal cash minus reserved cash")
        return self


class Forecast(DTO):
    forecast_id: Identifier
    store_id: Identifier
    sku_id: Identifier
    input_state_version: Positive
    predicted_quantity: Nonnegative
    unit: Literal["piece"]
    data_as_of: AwareDatetime
    horizon_start: AwareDatetime
    horizon_end: AwareDatetime
    valid_until: AwareDatetime
    model_name: str
    model_version: str
    source: Literal["fixed", "manual", "model"]
    assumptions: list[str]
    lower_quantity: Nonnegative = Field(default=None)
    upper_quantity: Nonnegative = Field(default=None)

    @model_validator(mode="after")
    def interval(self):
        if self.horizon_end <= self.horizon_start or self.valid_until <= self.data_as_of:
            raise ValueError("Forecast validity and horizon must be positive")
        return self


class ScenarioParameters(DTO):
    cash_minor: Annotated[int, Field(strict=True, ge=0, le=10**12)] = 100000
    on_hand: Annotated[int, Field(strict=True, ge=0, le=10**6)] = 20
    remaining_demand: Annotated[int, Field(strict=True, ge=0, le=10**6)] = 60
    unit_price_minor: Annotated[int, Field(strict=True, ge=1, le=10**8)] = 1000
    minimum_order_quantity: Annotated[int, Field(strict=True, ge=1, le=10**6)] = 20
    pack_size: Annotated[int, Field(strict=True, ge=1, le=10**6)] = 20
    lead_time_seconds: Annotated[int, Field(strict=True, ge=0, le=7776000)] = 86400
    horizon_days: Annotated[int, Field(strict=True, ge=1, le=90)] = 7

    @model_validator(mode="after")
    def delivery_window(self):
        if self.lead_time_seconds > self.horizon_days * 86400:
            raise ValueError("Lead time must fit the scenario horizon")
        return self


class ScenarioCreate(DTO):
    scenario: Literal["SC01", "SANDBOX"]
    label: str | None = Field(default=None, min_length=1, max_length=120)
    parameters: ScenarioParameters | None = None

    @model_validator(mode="after")
    def baseline(self):
        if self.scenario == "SC01" and (self.parameters is not None or self.label is not None):
            raise ValueError("SC01 is a fixed baseline; use SANDBOX for custom scenarios")
        return self


class ScenarioRun(DTO):
    scenario_run_id: Identifier
    store_id: Identifier
    simulation_time: AwareDatetime
    initial_state: State
    initial_forecast: Forecast
    initial_catalog: Catalog

    @model_validator(mode="after")
    def coherent_seed(self):
        state, forecast, catalog = self.initial_state, self.initial_forecast, self.initial_catalog
        stocks = {row.sku_id: row for row in state.stocks}
        products = {row.sku_id for row in catalog.products}
        if any(row.store_id != self.store_id for row in (state, forecast, catalog)):
            raise ValueError("Initial resources must belong to the same store")
        if (
            len(stocks) != len(state.stocks)
            or len(products) != len(catalog.products)
            or set(stocks) != products
            or forecast.sku_id not in products
            or any(offer.sku_id not in products for offer in catalog.offers)
        ):
            raise ValueError("Initial catalog and stock identities are inconsistent")
        if (
            state.state_version != 1
            or forecast.input_state_version != 1
            or state.reserved_cash_minor != 0
            or any(s.in_transit for s in state.stocks)
            or state.simulation_time != self.simulation_time
        ):
            raise ValueError("Bootstrap must be version one without reservations or inbound orders")
        stock = stocks[forecast.sku_id]
        if (
            stock.remaining_demand != forecast.predicted_quantity
            or stock.forecast_version != forecast.model_version
        ):
            raise ValueError("Initial stock and forecast disagree")
        return self


class ScenarioAccepted(DTO):
    job_run_id: Identifier
    status: Literal["READY", "RUNNING", "RETRY_WAIT"]
    scenario_run_id: Identifier | None
    store_id: Identifier | None


class SalePayload(DTO):
    sku_id: Identifier
    quantity: Positive
    unit_price_minor: Positive


class DemandPayload(DTO):
    sku_id: Identifier
    remaining_demand: Nonnegative
    forecast_version: str
    data_as_of: AwareDatetime
    valid_until: AwareDatetime
    horizon_start: AwareDatetime
    horizon_end: AwareDatetime

    @model_validator(mode="after")
    def interval(self):
        if self.horizon_end <= self.horizon_start or self.valid_until <= self.data_as_of:
            raise ValueError("Forecast validity and horizon must be positive")
        return self


class ReceivedPayload(DTO):
    action_id: Identifier
    sku_id: Identifier
    quantity: Positive


class PurchasePayload(ReceivedPayload):
    external_order_id: Identifier
    total_minor: Nonnegative


class Event(DTO):
    event_id: Identifier
    sequence: Positive
    schema_version: Literal["1.0"]
    store_id: Identifier
    occurred_at: AwareDatetime
    simulation_time: AwareDatetime


class SaleEvent(Event):
    event_type: Literal["SALE_RECORDED"]
    payload: SalePayload


class DemandEvent(Event):
    event_type: Literal["DEMAND_REVISED"]
    payload: DemandPayload


class ReceivedEvent(Event):
    event_type: Literal["GOODS_RECEIVED"]
    payload: ReceivedPayload


class PurchaseEvent(Event):
    event_type: Literal["PURCHASE_ACCEPTED"]
    payload: PurchasePayload


BusinessEvent = Annotated[
    SaleEvent | DemandEvent | ReceivedEvent | PurchaseEvent, Field(discriminator="event_type")
]


class EventBatch(DTO):
    source: Literal["simulation"]
    scenario_run_id: Identifier
    events: list[BusinessEvent] = Field(min_length=1, max_length=100)


class EventBatchResult(DTO):
    accepted_event_ids: list[Identifier]
    duplicate_event_ids: list[Identifier]
    last_sequence: Nonnegative


class EventPage(DTO):
    events: list[BusinessEvent] = Field(max_length=100)
    last_sequence: Nonnegative
    has_more: bool
    source_head_sequence: Nonnegative
