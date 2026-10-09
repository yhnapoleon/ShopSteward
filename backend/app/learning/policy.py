"""Pure policies. Sample counts are proposal triggers, never proof of quality."""

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo


def trigger_candidates(episodes, consumed):
    unique = {e["id"]: e for e in episodes if e.get("eligible")}
    results = []
    if len(unique) >= 10 and "first_ten" not in consumed:
        results.append(
            {"kind": "first_ten", "family": "unclassified", "episode_ids": sorted(unique)}
        )
    groups = defaultdict(list)
    for episode in unique.values():
        groups[episode["task_family"]].append(episode)
    for family, rows in sorted(groups.items()):
        dates = {
            datetime.fromisoformat(r["occurred_at"]).astimezone(ZoneInfo("Asia/Shanghai")).date()
            for r in rows
        }
        if family != "unclassified" and len(rows) >= 3 and len(dates) >= 2:
            results.append(
                {"kind": "category", "family": family, "episode_ids": sorted(r["id"] for r in rows)}
            )
    return results


def business_outcome(status, *, received=0, ordered=0):
    if status == "UNKNOWN":
        return "unknown"
    if status == "SUCCEEDED" and ordered > 0 and received >= ordered:
        return "matured"
    return "pending"


def assess_drift(applications):
    mature = [
        r
        for r in applications
        if r.get("stage") == "executed" and r.get("status") in {"pass", "fail"}
    ][-10:]
    return len(mature) == 10 and sum(r["status"] == "fail" for r in mature) >= 3
