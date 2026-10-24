"""Explicit current-date demonstration subsets; never mutate historical evaluation data."""

from copy import deepcopy
from datetime import datetime


def current_agent_subset(manifest, cases, as_of):
    instant = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("current-agent snapshot requires an explicit timezone")
    documents = []
    for record in manifest["documents"]:
        if not record["synthetic"]:
            continue
        metadata = record["metadata"]
        start = datetime.fromisoformat(metadata["valid_from"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(metadata["valid_until"].replace("Z", "+00:00"))
        if start <= instant < end:
            documents.append(deepcopy(record))
    scenarios = {d["metadata"]["scenario_id"] for d in documents}
    versions = {d["version_fixture_id"] for d in documents}
    selected = []
    date = instant.date().isoformat()
    for original in cases:
        if original["scenario_id"] not in scenarios:
            continue
        # Never rebind historical gold to a different current version.
        if any(
            not any(e.rsplit(":E", 1)[0] in versions for e in choices)
            for choices in original["required_evidence"]
        ):
            continue
        case = deepcopy(original)
        case.update(
            source_case_id=original["case_id"],
            source_as_of=original["as_of"],
            case_id=f"LIVE-{date}-{original['case_id']}",
            as_of=date,
            query=original["query"].replace(original["as_of"], date, 1),
            quality_evaluation_member=False,
            demonstration_scope="current document evidence only; no historical Agent claim",
        )
        if case.get("query_constraints"):
            case["query_constraints"]["as_of"] = date
        selected.append(case)
    return {
        "snapshot_as_of": as_of,
        "documents": documents,
        "cases": selected,
        "quality_counts_excluded": True,
        "historical_agent_evaluation": False,
    }
