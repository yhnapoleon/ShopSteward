"""Strict UTF-8 paragraphs and logical CSV records."""

import csv
import io
import re

from .models import ParseResult, coverage, locator, table_text


def column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def parse_text(content: bytes, *, markdown: bool = False, csv_format: bool = False) -> ParseResult:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("original is not valid UTF-8") from exc
    if csv_format:
        return _csv(text)
    blocks, sections = [], []
    # Paragraphs are nonempty runs separated by blank lines; Markdown headings
    # form their own paragraph even when no blank line follows them.
    paragraphs, pending = [], []
    for line in text.splitlines():
        heading = markdown and re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not line.strip() or heading:
            if pending:
                paragraphs.append("\n".join(pending))
                pending = []
            if heading:
                paragraphs.append(line)
        else:
            pending.append(line)
    if pending:
        paragraphs.append("\n".join(pending))
    for number, paragraph in enumerate(paragraphs, 1):
        heading = markdown and re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", paragraph)
        if heading:
            level, title = len(heading[1]), heading[2]
            sections = [(depth, name) for depth, name in sections if depth < level]
            sections.append((level, title))
        blocks.append(
            dict(
                text=paragraph,
                locator=locator(
                    "paragraph",
                    paragraph_range=[number, number],
                    section_path=[name for _, name in sections],
                ),
            )
        )
    items = [dict(locator=b["locator"], status="PARSED") for b in blocks]
    return ParseResult(status="COMPLETE", blocks=blocks, coverage=coverage("paragraphs", items))


def _csv(text: str) -> ParseResult:
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise ValueError("invalid CSV") from exc
    if not records:
        return ParseResult(status="COMPLETE", coverage=coverage("records", []))
    headers = records[0]
    blocks, items, warnings = [], [], []
    for number, row in enumerate(records[1:], 2):
        loc = locator(
            "cells",
            sheet="CSV",
            cell_range=f"A{number}:{column_name(max(len(headers), len(row), 1))}{number}",
        )
        items.append(dict(locator=loc, status="PARSED"))
        if len(row) != len(headers):
            warnings.append(f"CSV_RAGGED_ROW:{number}")
        value = table_text(headers, [row])
        if value.strip():
            blocks.append(dict(text=value, locator=loc, table=dict(headers=headers, rows=[row])))
    if len(records) == 1 and any(headers):
        loc = locator("cells", sheet="CSV", cell_range=f"A1:{column_name(len(headers))}1")
        blocks.append(
            dict(text=table_text(headers, []), locator=loc, table=dict(headers=headers, rows=[]))
        )
        items.append(dict(locator=loc, status="PARSED"))
    return ParseResult(
        status="PARTIAL" if warnings else "COMPLETE",
        blocks=blocks,
        warnings=warnings,
        coverage=coverage("records", items),
    )
