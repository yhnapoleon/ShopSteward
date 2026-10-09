"""Offer cards: what one supplier's documents support, as typed fields.

A reviewer reports facts and where it read them. It never picks a quantity or
a supplier: code turns the cards into solver offers and the solver compares
them. A wrong field is therefore traceable to one supplier and one document
instead of surfacing only as a wrong recommendation.
"""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REASONS = ("SKU_NOT_COVERED", "STORE_NOT_SERVED", "SUPPLY_WITHDRAWN")
OFFER_FIELDS = (
    "unit_price_minor",
    "minimum_order_quantity",
    "pack_size",
    "lead_time_days",
    "valid_from",
    "valid_until",
    "offer_version",
)
# Everything the solver reads. An expired quote is still an offer: the dates are
# reported as written and the solver, not the reviewer, rejects it.
DECISIVE = OFFER_FIELDS[:-1]
CITED = ("unit_price_minor", "minimum_order_quantity", "lead_time_days", "valid_until")
# Part of the output format, so it is not an evolvable text component.
CONTRACT = (
    "A card is one JSON object {supplier_id, status, reason, offer, history, citations}. "
    "status is offer or no_offer. Use no_offer only with reason SKU_NOT_COVERED (the requested "
    "item is not in the price list), STORE_NOT_SERVED (the store's district is outside the "
    "delivery area) or SUPPLY_WITHDRAWN (a notice in force suspends this item); then offer is "
    "null. Otherwise reason is null and offer is {unit_price_minor, minimum_order_quantity, "
    "pack_size, lead_time_days, valid_from, valid_until, offer_version}: the price of ONE unit "
    "in fen (1 yuan = 100 fen), the minimum order in units, units per case, calendar days from "
    "order to delivery (0 = same day), the quote's first and last valid dates as YYYY-MM-DD "
    "exactly as written, and the quote number. Report an expired quote as an offer with its "
    "written dates; do not judge budget, quantity or timing. history is {deliveries, late}, two "
    "integers: how many rows the delivery record has, and how many of those rows were "
    "delivered after the promised date. citations is a "
    "list of {field, doc_id, quote} with an exact excerpt for unit_price_minor, "
    "minimum_order_quantity, lead_time_days and valid_until, or for status when no_offer."
)


class _Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_price_minor: int = Field(gt=0)
    minimum_order_quantity: int = Field(gt=0)
    pack_size: int = Field(gt=0)
    lead_time_days: int = Field(ge=0)
    valid_from: date
    valid_until: date
    offer_version: str = Field(min_length=1)


class _History(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deliveries: int = Field(ge=0)
    late: int = Field(ge=0)


class _Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    doc_id: str
    quote: str = Field(min_length=1)


class Card(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: str
    status: Literal["offer", "no_offer"]
    reason: Literal[REASONS] | None = None
    offer: _Offer | None = None
    history: _History
    citations: list[_Citation] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        offered = self.status == "offer"
        if offered != (self.offer is not None) or offered == (self.reason is not None):
            raise ValueError("status, reason and offer disagree")
        return self


def parse(raw):
    """A validated card as plain JSON values, or None."""
    try:
        return Card.model_validate(raw).model_dump(mode="json")
    except ValueError:
        return None


def squash(text):
    return "".join(text.split())


def unsupported(card, documents):
    """Fields this card should cite but does not back with an exact excerpt.

    Needs no answer key, so it can gate a card at run time.
    """
    texts = {doc["doc_id"]: squash(doc["text"]) for doc in documents}
    backed = {
        item["field"]
        for item in card["citations"]
        if squash(item["quote"]) in texts.get(item["doc_id"], "")
    }
    needed = CITED if card["status"] == "offer" else ("status",)
    return [name for name in needed if name not in backed]


def to_offer(card, sku_id):
    """The written last valid day is inclusive; the solver's interval is half-open."""
    offer = card["offer"]
    until = date.fromisoformat(offer["valid_until"]) + timedelta(days=1)
    return {
        "supplier_id": card["supplier_id"],
        "sku_id": sku_id,
        "unit_price_minor": offer["unit_price_minor"],
        "minimum_order_quantity": offer["minimum_order_quantity"],
        "pack_size": offer["pack_size"],
        "offer_version": offer["offer_version"],
        "currency": "CNY",
        "lead_time_seconds": offer["lead_time_days"] * 86400,
        "valid_from": f"{offer['valid_from']}T00:00:00+00:00",
        "valid_until": f"{until.isoformat()}T00:00:00+00:00",
    }
