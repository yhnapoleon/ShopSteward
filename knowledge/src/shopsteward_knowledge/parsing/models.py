"""Parser-owned results; importing contracts never loads parser dependencies.

Blocks and coverage are JSON-compatible dictionaries. Locators use only the
public EvidenceLocator fields. All source coordinates are one-based, inclusive.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class OriginalRefLike(Protocol):
    version_id: str
    sha256: str
    mime: str
    storage_key: str
    size_bytes: int


class ParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks: list[dict[str, Any]] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["COMPLETE", "PARTIAL", "OCR_REQUIRED", "UNSUPPORTED"]
    parser_profile: dict[str, Any] = Field(default_factory=dict)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def locator(kind: str, **coordinates: Any) -> dict:
    return (
        dict(
            kind=kind,
            page=None,
            paragraph_range=None,
            table=None,
            sheet=None,
            cell_range=None,
            section_path=[],
        )
        | coordinates
    )


def coverage(unit: str, items: list[dict]) -> dict:
    parsed = sum(i["status"] == "PARSED" for i in items)
    return dict(
        unit=unit,
        units_total=len(items),
        units_parsed=parsed,
        units_unparsed=len(items) - parsed,
        items=items,
    )


def table_text(headers: list[str], rows: list[list[str]]) -> str:
    """Repeat the source header with each row; no inferred business values."""
    return "\n".join("\t".join(row) for row in [headers, *rows] if row)
