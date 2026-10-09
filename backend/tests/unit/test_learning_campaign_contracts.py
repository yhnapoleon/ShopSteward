import pytest


def test_reviewer_disagreement_or_invented_evidence_blocks_release():
    from app.learning.campaign import adjudicate

    def review(person, score=3):
        return {
            "reviewer": person,
            "dimensions": {
                f"S{i}": {"score": score, "reason": "Evidence read", "evidence_refs": ["artifact"]}
                for i in range(1, 7)
            },
        }

    scores, dimensions = adjudicate([review("a"), review("b")], {"artifact"})
    assert scores["S1"] == 3
    scores, _ = adjudicate([review("a"), review("b", 2)], {"artifact"})
    assert scores["S1"] is None
    with pytest.raises(ValueError):
        adjudicate([review("a"), review("a")], {"artifact"})
    with pytest.raises(ValueError):
        adjudicate([review("a"), review("b")], set())
