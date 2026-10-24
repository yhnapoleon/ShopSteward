"""Bounded, directional evidence paths; reachability is never business permission."""

from datetime import datetime


def _date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value


def bounded_paths(edges, seeds, predicates, *, as_of, context=None, max_depth=3, max_paths=100):
    if not 1 <= max_depth <= 3 or not 1 <= max_paths <= 100:
        raise ValueError("relation traversal budget exceeded")
    context = context or {}
    eligible = []
    for edge in sorted(edges, key=lambda e: e["id"]):
        if not edge.get("confirmed") or not edge.get("evidence_chunk_ids"):
            continue
        if edge["predicate"] not in predicates or edge["predicate"] == "MENTIONS":
            continue
        start, end = _date(edge.get("valid_from")), _date(edge.get("valid_until"))
        if (start and as_of < start) or (end and end <= as_of):
            continue
        if any(
            key not in context or type(context[key]) is not type(value) or context[key] != value
            for key, value in edge.get("conditions", {}).items()
        ):
            continue
        eligible.append(edge)
    frontier = [(seed, [seed], []) for seed in sorted(set(seeds))]
    result = []
    for _depth in range(max_depth):
        following = []
        for node, visited, path in frontier:
            for edge in eligible:
                if edge["subject"] != node or edge["object"] in visited:
                    continue
                # Compatibility/substitution is not automatically transitive.
                if path and edge["predicate"] in {"SUBSTITUTES", "COMPATIBLE_WITH"}:
                    continue
                next_path = path + [edge]
                result.append(
                    {
                        "edge_ids": [item["id"] for item in next_path],
                        "nodes": visited + [edge["object"]],
                        "edges": next_path,
                        "evidence_chunk_ids": list(
                            dict.fromkeys(
                                c for item in next_path for c in item["evidence_chunk_ids"]
                            )
                        ),
                        "coverage": "known_paths_only",
                    }
                )
                if len(result) >= max_paths:
                    for found in result:
                        found["truncated"] = True
                    return result
                following.append((edge["object"], visited + [edge["object"]], next_path))
        frontier = following
    return result


class PathList(list):
    """Retain traversal truncation even when no eligible path was found."""

    def __init__(self, values=(), *, truncated=False):
        super().__init__(values)
        self.truncated = truncated


class PGRelationRetriever:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def relation_paths(self, seeds, predicates, scope, *, max_depth=3, context=None):
        from sqlalchemy import and_, or_, select

        from ..models import Relation

        if not 1 <= max_depth <= 3:
            raise ValueError("relation traversal budget exceeded")
        if not seeds or not scope.allowed_versions:
            return PathList()
        clauses = [
            and_(
                Relation.version_id == v.version_id,
                Relation.generation_id == v.generation_id,
                Relation.metadata_revision == v.metadata_revision,
            )
            for v in scope.allowed_versions
        ]
        edges, seen = [], set()
        frontier = sorted(set(seeds))
        overflow = False
        async with self.session_factory() as session:
            for _ in range(max_depth):
                if not frontier:
                    break
                rows = (
                    await session.scalars(
                        select(Relation)
                        .where(
                            Relation.store_id == scope.store_id,
                            Relation.confirmed.is_(True),
                            Relation.predicate.in_(predicates),
                            Relation.subject.in_(frontier),
                            or_(Relation.valid_from.is_(None), Relation.valid_from <= scope.as_of),
                            or_(Relation.valid_until.is_(None), Relation.valid_until > scope.as_of),
                            or_(*clauses),
                        )
                        .order_by(Relation.id)
                        .limit(2001)
                    )
                ).all()
                overflow = overflow or len(rows) > 2000
                following = set()
                for row in rows[:2000]:
                    if row.id in seen:
                        continue
                    seen.add(row.id)
                    edge = {
                        key: getattr(row, key)
                        for key in (
                            "id",
                            "subject",
                            "predicate",
                            "object",
                            "confirmed",
                            "conditions",
                            "evidence_chunk_ids",
                            "version_id",
                            "generation_id",
                            "metadata_revision",
                            "valid_from",
                            "valid_until",
                        )
                    }
                    # Only expand nodes reached by satisfied, evidenced edges.
                    if bounded_paths(
                        [edge],
                        frontier,
                        predicates,
                        as_of=scope.as_of,
                        context=context,
                        max_depth=1,
                    ):
                        edges.append(edge)
                        following.add(row.object)
                frontier = sorted(following)
        paths = bounded_paths(
            edges, seeds, predicates, as_of=scope.as_of, max_depth=max_depth, context=context
        )
        if overflow:
            for path in paths:
                path["truncated"] = True
        return PathList(paths, truncated=overflow or any(p.get("truncated") for p in paths))
