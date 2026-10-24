"""Synchronous worker parser. Never run inline in an API event loop.

Only the supplied bytes are opened; storage_key is descriptive metadata and is
never dereferenced. Optional format libraries load on demand, without models.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import version

from .models import OriginalRefLike, ParseResult, stable_hash

__all__ = ["ParseResult", "parse_original"]


def parse_original(ref: OriginalRefLike, content: bytes) -> ParseResult:
    if not isinstance(content, bytes):
        raise TypeError("content must be original bytes, not a file path")
    if type(ref.size_bytes) is not int or len(content) != ref.size_bytes:
        raise ValueError("original size mismatch")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("original exceeds 20 MiB parser limit")
    if hashlib.sha256(content).hexdigest() != ref.sha256:
        raise ValueError("original SHA256 mismatch")
    mime = ref.mime.split(";", 1)[0].strip().lower()
    engine = "stdlib"
    if mime == "application/pdf":
        from .pdf import parse_pdf

        engine = "pypdf"
        result = parse_pdf(content)
    elif mime in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }:
        from .office import parse_docx, parse_xlsx

        engine = "python-docx" if mime.endswith(".document") else "openpyxl"
        result = parse_docx(content) if engine == "python-docx" else parse_xlsx(content)
    elif mime in {"text/plain", "text/markdown", "text/csv", "application/csv"}:
        from .text import parse_text

        result = parse_text(
            content, markdown=mime == "text/markdown", csv_format=mime.endswith("csv")
        )
    else:
        return ParseResult(
            status="UNSUPPORTED",
            warnings=[f"UNSUPPORTED_MIME:{mime}"],
            coverage=dict(
                unit="originals",
                units_total=1,
                units_parsed=0,
                units_unparsed=1,
                items=[dict(status="UNPARSED", reason="UNSUPPORTED_MIME")],
            ),
        )
    profile = dict(
        id="shopsteward-parser-v1",
        format=mime,
        engine=engine,
        engine_version=version(engine) if engine != "stdlib" else "utf8-v1",
    )
    result.parser_profile = profile
    for ordinal, block in enumerate(result.blocks):
        block.update(
            version_id=ref.version_id,
            original_sha256=ref.sha256,
            parser_profile=dict(profile),
            ordinal=ordinal,
        )
        loc = block["locator"]
        # Heading sections group prose; table/sheet/page boundaries never mix.
        boundary = {k: loc[k] for k in ("kind", "page", "table", "sheet", "section_path")}
        block["parent_id"] = "p_" + stable_hash([ref.version_id, profile, boundary])
    return result
