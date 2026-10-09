"""Grade offer cards against a world's answer key, and let the solver use them.

The card contract itself lives with the agent (`shopsteward_agent.offer_cards`),
because the running system has to enforce it too. Only what needs the answer
key or the solver is here.
"""

from . import _paths  # noqa: F401, I001
from shopsteward_agent.offer_cards import (
    CITED,
    CONTRACT,
    DECISIVE,
    OFFER_FIELDS,
    REASONS,
    Card,
    parse,
    squash,
    to_offer,
    unsupported,
)

__all__ = [
    "CITED",
    "CONTRACT",
    "DECISIVE",
    "OFFER_FIELDS",
    "REASONS",
    "Card",
    "check_card",
    "decide",
    "parse",
    "solve",
    "to_offer",
    "unsupported",
]


def _value(card, name):
    if name in ("status", "reason"):
        return card[name]
    if name in ("deliveries", "late"):
        return card["history"][name]
    return (card["offer"] or {}).get(name)


def check_card(raw, supplier):
    """Grade one reviewer output against the supplier's known card."""
    truth, card = supplier["card"], parse(raw)
    offered = truth["status"] == "offer"
    names = ("status", *(OFFER_FIELDS if offered else ("reason",)), "deliveries", "late")
    fields = {
        name: "invalid"
        if card is None
        else "correct"
        if _value(card, name) == _value(truth, name)
        else "wrong"
        for name in names
    }
    texts = {doc["doc_id"]: squash(doc["text"]) for doc in supplier["documents"]}
    citations = {}
    for name in CITED if offered else ("status",):
        found = [c for c in (card or {}).get("citations", []) if c["field"] == name]
        grounded = [c for c in found if squash(c["quote"]) in texts.get(c["doc_id"], "")]
        citations[name] = (
            "sourced"
            if any(c["doc_id"] in supplier["evidence"][name] for c in grounded)
            else "grounded"
            if grounded
            else "ungrounded"
            if found
            else "absent"
        )
    decisive = ("status", *(DECISIVE if offered else ()))
    return {
        "valid": card is not None,
        "fields": fields,
        "correct": sum(state == "correct" for state in fields.values()),
        "total": len(fields),
        "exact": all(state == "correct" for state in fields.values()),
        "decision_safe": all(fields[name] == "correct" for name in decisive),
        "citations": citations,
        "unsupported": unsupported(card, supplier["documents"]) if card else None,
    }


def solve(recovery):
    """The product's solver on one recovery input; None if the input is not valid."""
    from app.planning.recovery.schemas import RecoveryInput
    from app.planning.recovery.solver import solve as run

    try:
        return run(RecoveryInput.model_validate(recovery))
    except ValueError:
        return None


def decide(recovery, cards):
    """Solve with the offers these cards support; None if they are not a valid solver input."""
    offers = [to_offer(card, recovery["sku_id"]) for card in cards if card["status"] == "offer"]
    return solve({**recovery, "offers": offers})
