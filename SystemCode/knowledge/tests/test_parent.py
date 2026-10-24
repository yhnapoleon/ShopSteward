import pytest


def manifest():
    return [
        dict(
            id=str(i),
            text=f"条款{i}",
            ordinal=i,
            version_id="V1",
            generation_id="G1",
            parent_id="P1",
        )
        for i in range(60)
    ]


def test_parent_keeps_hit_beyond_fiftieth_chunk():
    from shopsteward_knowledge.parsing.parent import expand_parent

    result = expand_parent(list(reversed(manifest())), "55", radius=2, max_chars=1000)
    assert result == {
        "text": "条款53\n条款54\n条款55\n条款56\n条款57",
        "chunk_ids": ["53", "54", "55", "56", "57"],
        "truncated": False,
    }


def test_budget_keeps_entire_hit_even_when_hit_exceeds_budget():
    from shopsteward_knowledge.parsing.parent import expand_parent

    result = expand_parent(manifest(), "55", radius=2, max_chars=2)
    assert result == {"text": "条款55", "chunk_ids": ["55"], "truncated": True}


def test_parent_never_includes_other_version_generation_or_parent():
    from shopsteward_knowledge.parsing.parent import expand_parent

    chunks = manifest()
    for index, field in [(54, "version_id"), (56, "generation_id"), (57, "parent_id")]:
        chunks[index][field] = "different"
    result = expand_parent(chunks, "55", radius=1, max_chars=100)
    assert result["chunk_ids"] == ["53", "55", "58"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "cross_version", "ordinal"])
def test_invalid_hit_manifest_is_rejected(mutation):
    from shopsteward_knowledge.parsing.parent import expand_parent

    chunks = manifest()
    if mutation == "missing":
        chunks.pop(55)
    elif mutation in ("duplicate", "cross_version"):
        chunks.append({**chunks[55], "version_id": "V2" if mutation == "cross_version" else "V1"})
    else:
        chunks[54]["ordinal"] = 55
    with pytest.raises(ValueError):
        expand_parent(chunks, "55", radius=2, max_chars=100)


@pytest.mark.parametrize("radius,budget", [(-1, 100), (1, 0), (True, 10)])
def test_invalid_parent_budget_is_rejected(radius, budget):
    from shopsteward_knowledge.parsing.parent import expand_parent

    with pytest.raises(ValueError):
        expand_parent(manifest(), "55", radius=radius, max_chars=budget)
