"""Read-only extension seams. Providers own authorization and source authenticity."""

from typing import Protocol


class EvidenceProvider(Protocol):
    async def search(self, query: str, scope: dict) -> list[dict]: ...


class SkillProvider(Protocol):
    async def load(self, task_type: str, scope: dict) -> list[dict]: ...


class EmptyEvidenceProvider:
    async def search(self, query: str, scope: dict) -> list[dict]:
        return []


class EmptySkillProvider:
    async def load(self, task_type: str, scope: dict) -> list[dict]:
        return []


async def collect_extensions(
    *,
    query: str,
    task_type: str,
    scope: dict,
    allowed_tools: set[str],
    evidence_provider: EvidenceProvider | None = None,
    skill_provider: SkillProvider | None = None,
) -> dict:
    """Keep provenance-bearing evidence and skills whose tool requirements are met.

    Merely listing a reference does not establish its authenticity; the injecting
    provider must validate sources. The result is context, not executable tools.
    """
    evidence = await (evidence_provider or EmptyEvidenceProvider()).search(query, scope)
    skills = await (skill_provider or EmptySkillProvider()).load(task_type, scope)
    return {
        "evidence": [
            item
            for item in evidence
            if isinstance(item, dict)
            and isinstance(item.get("references"), list)
            and item["references"]
            and all(isinstance(ref, dict) and ref for ref in item["references"])
        ],
        "skills": [
            item
            for item in skills
            if isinstance(item, dict)
            and isinstance(item.get("required_tools", []), list)
            and all(isinstance(name, str) for name in item.get("required_tools", []))
            and set(item.get("required_tools", [])) <= allowed_tools
        ],
    }
