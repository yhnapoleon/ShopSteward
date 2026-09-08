"""Local cloud-pilot evidence gate, distinct from cloud quality and MVP acceptance."""

REQUIRED_CHECKS = frozenset(
    {
        "corpus_200",
        "real_http",
        "restore",
        "versioning",
        "agent_tools",
        "build",
    }
)


def ready_for_cloud_pilot(checks: dict[str, str]) -> bool:
    return all(checks.get(key) == "passed" for key in REQUIRED_CHECKS)
