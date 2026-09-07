import pytest


@pytest.mark.asyncio
async def test_extension_provenance_and_capability_filter():
    import shopsteward_agent

    assert hasattr(shopsteward_agent, "collect_extensions")

    class Evidence:
        async def search(self, query, scope):
            return [
                {"content": "verified", "references": [{"source": "plugin", "id": "1"}]},
                {"content": "unsupported"},
            ]

    class Skills:
        async def load(self, task_type, scope):
            return [
                {"name": "read", "required_tools": ["read"]},
                {"name": "execute", "required_tools": ["purchase"]},
                {"name": "bad", "required_tools": "read"},
            ]

    result = await shopsteward_agent.collect_extensions(
        query="q",
        task_type="summary",
        scope={"store": "A"},
        allowed_tools={"read"},
        evidence_provider=Evidence(),
        skill_provider=Skills(),
    )
    assert result == {
        "evidence": [{"content": "verified", "references": [{"source": "plugin", "id": "1"}]}],
        "skills": [{"name": "read", "required_tools": ["read"]}],
    }
    assert await shopsteward_agent.collect_extensions(
        query="q", task_type="summary", scope={}, allowed_tools=set()
    ) == {"evidence": [], "skills": []}
