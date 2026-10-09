"""Trusted check of typed claims against the solver output.

Only two claim types are machine-checked: a candidate's status and the first
day a candidate still loses demand. Untyped prose is neither credited nor
penalized here; it needs human review.
"""

import re


def gap(candidate):
    day = next((i for i, d in enumerate(candidate["daily"], 1) if d["lost_qty"] > 0), None)
    return f"day-{day}" if day else "none"


def required_conditions(proposal):
    """What a useful explanation must state: the decision, its effect, and the cost of waiting."""
    candidates = {c["id"]: c for c in proposal["candidates"]}
    chosen = proposal["recommended_candidate_id"]
    required = [f"candidate:{chosen}=recommended", f"gap:{chosen}={gap(candidates[chosen])}"]
    if chosen != "wait":
        required.append(f"gap:wait={gap(candidates['wait'])}")
    return required


def check_claims(claims, proposal):
    candidates = {c["id"]: c for c in proposal["candidates"]}
    chosen = proposal["recommended_candidate_id"]
    required = required_conditions(proposal)
    stated, contradictions, unverifiable = set(), [], 0
    for claim in claims:
        subject = claim.get("subject") or {}
        result = (claim.get("applicability") or {}).get("result")
        kind, target = subject.get("type"), subject.get("id")
        if kind not in ("candidate", "gap") or not isinstance(result, str):
            continue
        candidate = candidates.get(target)
        if candidate is None:
            truth = None  # a claim about a candidate the solver never produced
        elif kind == "candidate":
            truth = {
                "recommended": target == chosen,
                "feasible": candidate["feasible"],
                "rejected": not candidate["feasible"],
            }.get(result, "unverifiable")
        else:
            truth = (
                result == gap(candidate)
                if re.fullmatch(r"none|day-[1-7]", result)
                else "unverifiable"
            )
        if truth == "unverifiable":
            unverifiable += 1
        elif truth:
            stated.add(f"{kind}:{target}={result}")
        else:
            contradictions.append(
                {
                    "claim": f"{kind}:{target}={result}",
                    "statement": claim.get("statement", ""),
                    "asserted_by": claim.get("asserted_by", []),
                }
            )
    covered = [item for item in required if item in stated]
    return {
        "required": required,
        "covered": covered,
        "coverage": len(covered) / len(required),
        "contradictions": contradictions,
        "unverifiable": unverifiable,
    }
