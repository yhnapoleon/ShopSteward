"""Restore context from a complete manifest, never a first-N search window."""


def expand_parent(chunks: list[dict], hit_id: str, *, radius: int, max_chars: int) -> dict:
    """Return whole neighboring chunks; the hit alone may exceed max_chars.

    Input must already be authorized by the caller. Radius counts neighbors in
    ordinal order within the hit's parent/version/generation. A duplicate hit
    identity (including one from another version) is an error, not a guess.
    """
    if type(radius) is not int or radius < 0 or type(max_chars) is not int or max_chars < 1:
        raise ValueError("radius must be nonnegative and max_chars positive integers")
    hits = [c for c in chunks if c["id"] == hit_id]
    if len(hits) != 1:
        raise ValueError("hit is missing or ambiguous across manifests/versions")
    hit = hits[0]
    fields = ("parent_id", "version_id", "generation_id")
    if any(not hit.get(f) for f in fields):
        raise ValueError("hit requires parent_id, version_id and generation_id")
    siblings = [c for c in chunks if all(c.get(f) == hit[f] for f in fields)]
    if any(
        type(c.get("ordinal")) is not int
        or c["ordinal"] < 0
        or not isinstance(c.get("text"), str)
        or not c["text"]
        for c in siblings
    ):
        raise ValueError("manifest requires nonnegative ordinals and nonempty text")
    if len({c["ordinal"] for c in siblings}) != len(siblings) or len(
        {c["id"] for c in siblings}
    ) != len(siblings):
        raise ValueError("duplicate ordinal or identity in parent manifest")
    siblings.sort(key=lambda c: c["ordinal"])
    position = next(i for i, c in enumerate(siblings) if c["id"] == hit_id)
    window = range(max(0, position - radius), min(len(siblings), position + radius + 1))
    selected = {position}
    used = len(hit["text"])
    for index in sorted((i for i in window if i != position), key=lambda i: (abs(i - position), i)):
        cost = len(siblings[index]["text"]) + 1
        if used + cost <= max_chars:
            selected.add(index)
            used += cost
    ordered = [siblings[i] for i in sorted(selected)]
    return dict(
        text="\n".join(c["text"] for c in ordered),
        chunk_ids=[c["id"] for c in ordered],
        truncated=used > max_chars or len(selected) < len(window),
    )
