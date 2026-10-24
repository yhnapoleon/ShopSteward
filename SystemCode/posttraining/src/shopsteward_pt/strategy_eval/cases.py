"""Synthetic supply-recovery cases; the deterministic solver is the oracle.

The solver's own correctness is anchored by hand-computed tests in the backend.
These cases therefore measure whether an explanation is faithful to the solver
output, not whether the solver is right.
"""

import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..case_eval.models import CaseContract
from . import _paths  # noqa: F401
from .claims import required_conditions

DATASET = "ops-synthetic-v1"
START = datetime(2026, 10, 1, tzinfo=UTC)
# The optimizer may read evo-train (with feedback) and evo-val (scores only).
# It never sees gate, which decides whether an evolved text is released.
PARTITIONS = {"smoke": 12, "evo-train": 12, "evo-val": 12, "gate": 24}
SIMPLE = {"tight_budget", "no_action", "unverified_execution"}


def build(*, on_hand, demand, inbound, cash, budget, offers, floor=50000, **flags):
    return {
        "store_id": "store-eval",
        "sku_id": "sku-eval",
        "on_hand": on_hand,
        "available_cash_minor": cash,
        "cash_floor_minor": floor,
        "budget_minor": budget,
        "business_time": START,
        "evaluated_at": START,
        "demand_source": "simulation",
        "executable": True,
        "daily_demand": [
            {"settlement_at": START + timedelta(days=day, hours=23), "demand_qty": quantity}
            for day, quantity in enumerate(demand)
        ],
        "arrivals": [
            {
                "action_id": f"inbound-{number}",
                "sku_id": "sku-eval",
                "ordered_qty": ordered,
                "received_qty": received,
                "expected_arrival_at": START + timedelta(days=day),
            }
            for number, (ordered, received, day) in enumerate(inbound)
        ],
        "offers": [
            {
                "supplier_id": supplier,
                "sku_id": "sku-eval",
                "unit_price_minor": price,
                "minimum_order_quantity": minimum,
                "pack_size": pack,
                "offer_version": "v1",
                "currency": "CNY",
                "lead_time_seconds": lead * 86400,
                "valid_from": START - timedelta(days=1),
                "valid_until": START + timedelta(days=1),
            }
            for supplier, price, minimum, pack, lead in offers
        ],
        **flags,
    }


def _gap(rng):
    """Stock lasts k days, the paid inbound order lands on day a, so days k..a-1 are short."""
    demand = rng.choice((6, 8, 10, 12, 15))
    k = rng.choice((1, 2, 3))
    a = min(6, k + rng.choice((1, 2, 3)))
    pack = rng.choice((5, 10))
    need = -(-demand * (a - k) // pack) * pack
    base = {"on_hand": demand * k, "demand": [demand] * 7, "inbound": [(demand * (7 - k), 0, a)]}
    return base, k, a, pack, need


def temporal_gap(rng):
    base, k, a, pack, need = _gap(rng)
    price = rng.choice((900, 1000, 1200))
    budget = need * price + rng.choice((0, 1, 2)) * pack * price
    offers = [
        ("B", price, need, pack, rng.randint(1, k)),
        ("C", price + rng.choice((200, 300)), need, pack, rng.randint(1, k)),
    ]
    return {**base, "cash": 60000 + budget, "budget": budget, "offers": offers}


def late_cheap_offer(rng):
    base, k, a, pack, need = _gap(rng)
    fast = rng.choice((1200, 1500))
    budget = need * fast + pack * fast
    offers = [
        ("B", fast, need, pack, rng.randint(1, k)),
        ("C", fast - rng.choice((300, 400, 500)), need, pack, rng.randint(a, 6)),
    ]
    return {**base, "cash": 60000 + budget, "budget": budget, "offers": offers}


def tight_budget(rng):
    base, k, a, pack, need = _gap(rng)
    fast = rng.choice((1200, 1500))
    budget = need * fast - rng.choice((1000, 2000, 4000))
    offers = [
        ("B", fast, need, pack, rng.randint(1, k)),
        ("C", 800, pack, pack, rng.randint(a, 6)),
    ]
    return {**base, "cash": 60000 + budget, "budget": budget, "offers": offers}


def cash_floor(rng):
    base, k, a, pack, need = _gap(rng)
    room = need * 1300 + pack * 1300
    offers = [
        ("A", 900, need * 3, pack, rng.randint(1, k)),
        ("B", 1300, need, pack, rng.randint(1, k)),
    ]
    return {**base, "cash": 50000 + room, "budget": need * 3 * 900 + 10000, "offers": offers}


def moq_pack(rng):
    base, k, a, pack, need = _gap(rng)
    budget = need * 1200 + pack * 1200
    offers = [
        ("A", 800, need * 3, pack, rng.randint(1, k)),
        ("B", 1200, need, pack, rng.randint(1, k)),
    ]
    return {**base, "cash": 70000 + budget, "budget": budget, "offers": offers}


def partial_receipt(rng):
    base, k, a, pack, need = _gap(rng)
    ordered, _, day = base["inbound"][0]
    received = rng.choice((1, 2)) * base["demand"][0]
    budget = need * 1200 + pack * 1200
    return {
        **base,
        "inbound": [(ordered + received, received, day)],
        "cash": 60000 + budget,
        "budget": budget,
        "offers": [("B", 1200, need, pack, rng.randint(1, k))],
    }


def no_action(rng):
    demand, k, pack = rng.choice((6, 8, 10, 12)), rng.choice((2, 3)), rng.choice((5, 10))
    return {
        "on_hand": demand * k,
        "demand": [demand] * 7,
        "inbound": [(demand * (7 - k), 0, rng.randint(1, k))],
        "cash": 60000 + pack * 4 * 1200,
        "budget": pack * 4 * 1200,
        "offers": [("B", 1200, pack * 2, pack, 1)],
    }


def unverified_execution(rng):
    return {**temporal_gap(rng), "unresolved_action_id": "action-pending"}


def _chosen(result):
    return next(c for c in result.candidates if c.id == result.recommended_candidate_id)


def _wait(result):
    return next(c for c in result.candidates if c.id == "wait")


def _reasons(result, supplier):
    return {r for c in result.candidates if c.supplier_id == supplier for r in c.rejection_reasons}


def _closes_gap(result, supplier=None):
    chosen = _chosen(result)
    return (
        _wait(result).lost_qty > 0
        and chosen.lost_qty == 0
        and chosen.quantity > 0
        and supplier in (None, chosen.supplier_id)
    )


def _waits_with_gap(result):
    return result.recommended_candidate_id == "wait" and _wait(result).lost_qty > 0


# family -> (sampler, the outcome that makes a draw belong to the family)
FAMILIES = {
    "temporal_gap": (temporal_gap, _closes_gap),
    "late_cheap_offer": (
        late_cheap_offer,
        lambda r: (
            _closes_gap(r, "B")
            and any(
                c.supplier_id == "C" and c.feasible and c.lost_qty == _wait(r).lost_qty
                for c in r.candidates
            )
        ),
    ),
    "tight_budget": (tight_budget, _waits_with_gap),
    "cash_floor": (
        cash_floor,
        lambda r: _closes_gap(r, "B") and "CASH_FLOOR_VIOLATION" in _reasons(r, "A"),
    ),
    "moq_pack": (
        moq_pack,
        lambda r: _closes_gap(r, "B") and "BUDGET_EXCEEDED" in _reasons(r, "A"),
    ),
    "partial_receipt": (partial_receipt, _closes_gap),
    "no_action": (
        no_action,
        lambda r: r.recommended_candidate_id == "wait" and _wait(r).lost_qty == 0,
    ),
    "unverified_execution": (
        unverified_execution,
        lambda r: _waits_with_gap(r) and not any(c.feasible and c.quantity for c in r.candidates),
    ),
}


def _hash(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def contract(fixture, dataset=DATASET, simple=SIMPLE):
    case_id, family = fixture["case_id"], fixture["family"]
    checks = {
        "endpoint": ("analysis_delivered", True, "context", None),
        "claims_supported": ("claims_supported", True, "context", None),
        "no_contradiction": ("claims.contradictions", 0, "solver", "solver_contradiction"),
        "conditions_covered": ("claims.all_required_covered", True, "solver", None),
        "useful": ("claims.any_required_covered", True, "solver", None),
    }
    full = {
        "D2": ["claims_supported"],
        "D3": ["no_contradiction", "conditions_covered"],
        "D4": ["endpoint"],
    }
    return CaseContract.model_validate_json(
        json.dumps(
            {
                "schema_version": "case_contract_v1",
                "suite_id": "ops",
                "case_id": case_id,
                "dataset_version": dataset,
                "task_contract_version": "frozen-case-explanation-v1",
                "template_id": f"{fixture['partition']}/{family}",
                "fixture_id": case_id,
                "fixture_hash": _hash(fixture),
                "split": "smoke" if fixture["partition"] == "smoke" else "dev",
                "lock_status": "development",
                "artifact_kind": "recorded",
                "complexity": "simple" if family in simple else "complex",
                "scenario_family": family,
                "goal_endpoint": "analysis",
                "capabilities": ["read_frozen_evidence"],
                "allowed_actions": ["analyze"],
                "admission_revision": 1,
                "required_condition_ids": fixture["required"],
                "predicates": [
                    {
                        "check_id": check,
                        "observation_id": observation,
                        "expected": expected,
                        "source_kind": kind,
                        "critical_failure_code": critical,
                    }
                    for check, (observation, expected, kind, critical) in checks.items()
                ],
                "semantic_checks": [],
                "required_predicates": ["endpoint", "no_contradiction", "conditions_covered"],
                "required_semantic_checks": [],
                "dimensions": [
                    {
                        "dimension_id": key,
                        "applicable": key in full,
                        "full_checks": full.get(key, []),
                        "partial_checks": ["useful"] if key in ("D3", "D4") else [],
                        "reason": "Typed claims checked against the solver output"
                        if key in full
                        else "Not machine-checkable in this suite; needs human review",
                    }
                    for key in ("D1", "D2", "D3", "D4", "D5", "D6")
                ],
                "clarification_required": False,
                "followup_expected": False,
                "fixture_valid": True,
                "invalid_fixture_reason": None,
            }
        )
    )


def generate():
    """Deterministic: the same code always yields the same 60 fixtures."""
    from app.planning.recovery.schemas import RecoveryInput
    from app.planning.recovery.solver import solve

    fixtures, names = [], list(FAMILIES)
    for partition, count in PARTITIONS.items():
        for index in range(count):
            family = names[index % len(names)]
            sampler, belongs = FAMILIES[family]
            rng = random.Random(f"{DATASET}:{partition}:{family}:{index}")
            for _ in range(500):
                snapshot = RecoveryInput.model_validate(build(**sampler(rng)))
                result = solve(snapshot)
                if len(result.candidates) <= 12 and belongs(result):
                    break
            else:
                raise RuntimeError(f"no {family} draw satisfied its outcome")
            case_id = f"{partition}-{family}-{index:02d}"
            proposal = {"id": f"proposal:{case_id}", **result.model_dump(mode="json")}
            fixtures.append(
                {
                    "case_id": case_id,
                    "partition": partition,
                    "family": family,
                    "snapshot": {"recovery": snapshot.model_dump(mode="json")},
                    "proposal": proposal,
                    "required": required_conditions(proposal),
                }
            )
    bodies = [_hash({k: f[k] for k in ("snapshot", "required")}) for f in fixtures]
    if len(set(bodies)) != len(bodies):
        raise RuntimeError("two cases share one fixture; partitions would leak")
    return fixtures


def write_dataset(directory, fixtures=None, *, dataset=DATASET, simple=SIMPLE, inputs=(), **notes):
    """`inputs` are files already in the directory that the fixtures were built from."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = generate() if fixtures is None else fixtures
    files = {
        "fixtures.jsonl": [json.dumps(f, ensure_ascii=False, sort_keys=True) for f in fixtures],
        "cases.jsonl": [contract(f, dataset, simple).model_dump_json() for f in fixtures],
    }
    for name, lines in files.items():
        (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "dataset_version": dataset,
        "oracle": "recovery_solver_v1",
        "partitions": {
            name: sorted(f["case_id"] for f in fixtures if f["partition"] == name)
            for name in PARTITIONS
        },
        "sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in (*files, *inputs)
        },
        "research_status": "synthetic development cases; no locked test set",
        **notes,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def load_dataset(directory):
    """Return [(contract, fixture)] after checking the files against the manifest."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"{name} differs from the manifest")
    fixtures = [
        json.loads(line)
        for line in (directory / "fixtures.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    contracts = [
        CaseContract.model_validate_json(line)
        for line in (directory / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for case, fixture in zip(contracts, fixtures, strict=True):
        if case.case_id != fixture["case_id"] or case.fixture_hash != _hash(fixture):
            raise ValueError("fixture does not match its frozen contract")
    return list(zip(contracts, fixtures, strict=True))
