"""Deterministic character budgets, explicitly not measured token budgets."""

import hashlib
from copy import deepcopy

from .models import stable_hash


def _table_fragments(block: dict, size: int, overlap: int):
    table = block["table"]
    header = "\t".join(table["headers"]) + "\n"
    rows = table["rows"]
    if block["text"] != header + "\n".join("\t".join(row) for row in rows):
        raise ValueError("table text must match source cells")
    offset = len(header)
    for row_number, row in enumerate(rows, 1):
        row_text = "\t".join(row)
        if len(header) + len(row_text) <= size:
            yield header + row_text, [offset, offset + len(row_text)], {}
        else:
            # Preserve the first-column row identity and every other column.
            # Choose a data cell to split, never slice across column boundaries.
            column = max(range(1 if len(row) > 1 else 0, len(row)), key=lambda i: len(row[i]))
            before = "\t".join(row[:column]) + ("\t" if column else "")
            after = ("\t" if column + 1 < len(row) else "") + "\t".join(row[column + 1 :])
            available = size - len(header) - len(before) - len(after)
            if available <= overlap:
                raise ValueError("table row context cannot fit within this chunk budget")
            cell = row[column]
            for start in range(0, len(cell), available - overlap):
                end = min(start + available, len(cell))
                value = header + before + cell[start:end] + after
                source_range = [offset + len(before) + start, offset + len(before) + end]
                metadata = dict(
                    truncated=True,
                    table_fragment=dict(
                        row=row_number, column=column + 1, cell_char_range=[start, end]
                    ),
                )
                yield value, source_range, metadata
                if end == len(cell):
                    break
        offset += len(row_text) + 1


def _fragments(block: dict, size: int, overlap: int):
    text = block["text"]
    table = block.get("table")
    if table and table.get("headers") and table.get("rows"):
        yield from _table_fragments(block, size, overlap)
        return
    for start in range(0, len(text), size - overlap):
        end = min(start + size, len(text))
        yield text[start:end], [start, end], {}
        if end == len(text):
            break


def chunk_blocks(blocks: list[dict], profile: dict) -> list[dict]:
    profile = {"id": "characters-v1", "max_chars": 1200, "overlap_chars": 0, **profile}
    size, overlap = profile["max_chars"], profile["overlap_chars"]
    if type(size) is not int or size < 1 or type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError("require max_chars > overlap_chars >= 0 integers")
    chunks = []
    for block in blocks:
        text = block["text"]
        if not text.strip():
            continue
        for value, source_range, metadata in _fragments(block, size, overlap):
            if value.strip():
                digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
                identity = [
                    block["version_id"],
                    block["parser_profile"],
                    profile,
                    block["locator"],
                    block["ordinal"],
                    source_range,
                    digest,
                ]
                identifier = "c_" + stable_hash(identity)
                chunk = deepcopy(block)
                chunk.update(
                    id=identifier,
                    chunk_id=identifier,
                    text=value,
                    content_sha256=digest,
                    chunker_profile=deepcopy(profile),
                    source_ordinal=block["ordinal"],
                    ordinal=len(chunks),
                    char_range=source_range,
                    **metadata,
                )
                chunks.append(chunk)
    return chunks
