def rrf(lists: list[list[str]], *, c: int = 60) -> list[tuple[str, float]]:
    if c < 0:
        raise ValueError("RRF constant must be nonnegative")
    scores: dict[str, float] = {}
    for channel in lists:
        unique = list(dict.fromkeys(channel))
        for rank, identifier in enumerate(unique, 1):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (c + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
