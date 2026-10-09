"""Diagnostic failure tags from the MAST taxonomy (arXiv 2503.13657).

Only modes that the run ledger can prove are tagged here. Tags explain a
result; they never decide task success.
"""

CODES = {
    "FM-1.1": ("invalid_subtask_result", "AGENT_MODEL_PROTOCOL", "AGENT_READ_ONLY_INTENT"),
    "FM-1.2": ("AGENT_TOOL_NOT_OFFERED", "AGENT_UNKNOWN_TOOL"),
    "FM-1.5": (
        "AGENT_MODEL_BUDGET",
        "AGENT_TOOL_BUDGET",
        "AGENT_RUN_DEADLINE",
        "AGENT_MODEL_DEADLINE",
    ),
    "FM-3.2": ("unsupported_claim",),
}


def mast_tags(analysis, checked):
    subtasks = analysis.get("subtasks", [])
    failures = {code for task in subtasks for code in task.get("missing", [])}
    tags = {tag for tag, codes in CODES.items() if failures & set(codes)}
    seen = set()
    for item in analysis.get("tool_log", []):
        key = (item["subtask_id"], item["name"], item["args_hash"])
        if key in seen:
            tags.add("FM-1.3")  # the same read repeated inside one subtask
        seen.add(key)
    if subtasks and all(task["status"] == "complete" for task in subtasks):
        if checked["coverage"] < 1:
            tags.add("FM-3.1")  # reported done without stating what the case requires
    conflicts = (analysis.get("merged") or {}).get("conflicts", [])
    if any("resolved_by" not in item for item in conflicts):
        tags.add("FM-3.2")
    if any(
        ":followup" in subtask
        for item in checked["contradictions"]
        for subtask in item["asserted_by"]
    ):
        tags.add("FM-3.3")  # the one verification step itself got the facts wrong
    return sorted(tags)
