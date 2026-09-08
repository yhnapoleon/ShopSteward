# B2 integration

`from shopsteward_knowledge.parsing import parse_original, ParseResult`

`parse_original(ref, content: bytes)` is synchronous and belongs in the worker
process. `ref` is structurally typed through `OriginalRefLike` in `models.py`;
the public `contracts.OriginalRef` supplies `version_id`, `sha256`, `mime`,
`storage_key`, and `size_bytes`. Only the supplied bytes are parsed. A storage
key is never opened as a host filename. Bytes must match both size and SHA256.

`ParseResult` is a parser-local Pydantic model (`extra="forbid"`), with
`model_dump(mode="json")` available for persistence:

```python
{
    "status": "PARTIAL",  # COMPLETE / PARTIAL / OCR_REQUIRED / UNSUPPORTED
    "blocks": [...],
    "coverage": {
        "unit": "pages",  # format-specific: paragraphs/records/body_elements/workbook_parts
        "units_total": 2,
        "units_parsed": 1,
        "units_unparsed": 1,
        "items": [
            {"locator": {...}, "status": "PARSED"},
            {"locator": {...}, "status": "UNPARSED", "reason": "OCR_REQUIRED"},
        ],
    },
    "warnings": ["PDF_NO_TEXT_LAYER:2:OCR_REQUIRED"],  # string codes, not objects
    "parser_profile": {
        "id": "shopsteward-parser-v1",
        "format": "application/pdf",
        "engine": "pypdf",
        "engine_version": "6.17.0",
    },
}
```

`units_unparsed` counts units not fully
parsed, including worksheet units marked `PARTIAL` for missing formula caches.
Coverage is structural extraction coverage, not retrieval quality or a claim of
visual/layout fidelity. Encrypted PDFs with no accessible pages report
`UNSUPPORTED`; malformed input, invalid UTF-8, integrity mismatch, or exceeded
resource limits raise an exception for the worker to record as a parse failure.
Missing optional dependencies raise `ImportError`; there is no automatic install.

Every block is a JSON-compatible dictionary:

```python
{
    "text": "source text",
    "ordinal": 0,
    "version_id": "V1",
    "original_sha256": "<64 lowercase hex characters>",
    "parser_profile": {...},
    "parent_id": "p_<sha256>",
    "locator": {
        "kind": "paragraph",  # page / paragraph / table / cells
        "page": None,
        "paragraph_range": [1, 1],
        "table": None,
        "sheet": None,
        "cell_range": None,
        "section_path": [],
    },
}
```

Locators validate against `contracts.EvidenceLocator` without extra fields.
Ranges and PDF pages are one-based/inclusive. DOCX paragraph ordinals count
actual body XML paragraphs, including empty paragraphs and table-cell paragraphs;
table ordinals count body tables, including those inside supported body content
controls (`w:sdt/w:sdtContent`). These controls are traversed in document order;
text in other unsupported body wrappers is reported as unparsed. Nested cell paragraphs are included
under their containing table. No DOCX or spreadsheet page numbers are invented.
CSV uses `sheet="CSV"` and logical record row numbers, including quoted multiline
records. XLSX uses actual sheet names and cell coordinates; hidden sheet state
is retained. Sections are heading paths for Markdown and DOCX.

Table blocks also have `table={"headers": list[str], "rows": list[list[str]]}`.
The first source row is retained as header context, not inferred semantic labels.
Each data-row block repeats it in the text. XLSX blocks also have `sheet_state`
and `formulas`, where each formula entry has exactly:

```python
{"cell": "B2", "formula": "=2+3", "cached_value": 5, "cache_status": "present"}
# No cache: cached_value=None and cache_status="missing". Never substitute 0.
```

Caches are evidence metadata, not recalculated values; formula strings remain in
the text. Chartsheets (even empty/hidden ones), worksheet drawings, and DOCX
visual/nonbody text are explicitly reported as unparsed, making the result
`PARTIAL`. No OCR runs; textless PDF pages conservatively require OCR, including
blank pages which cannot be distinguished reliably by text extraction alone.
Image-bearing pages with a text layer also conservatively return `PARTIAL` with
`PDF_IMAGE_CONTENT:<page>:OCR_REQUIRED`; a footer does not prove the scanned body
was extracted. The image inventory includes nested forms and inline images. This
can conservatively flag decorative images too; it does not invent OCR output.

`chunk_blocks(blocks: list[dict], profile: dict) -> list[dict]` lives in
`parsing.chunking`. Defaults are `id="characters-v1"`, `max_chars=1200`,
`overlap_chars=0`. These are character budgets, not measured token budgets.
Every output copies block metadata and adds:

- `id` and `chunk_id`: identical `c_<sha256>` values;
- `content_sha256`: hash of this chunk's exact UTF-8 text;
- `chunker_profile`: the full profile with defaults expanded;
- `source_ordinal`: source block's zero-based ordinal;
- `ordinal`: chunk's zero-based document ordinal;
- `char_range`: zero-based/end-exclusive offsets into original block text.

Table chunks repeat the header. Long rows split one data cell at a time while
retaining the full first-column row key, other cells, and column separators.
`char_range` remains zero-based/end-exclusive into the original block; for a
continuation it identifies the varying cell slice, with the repeated row and
header text acting as additional context. Split rows add `truncated=True` and
`table_fragment={"row": 1, "column": 2, "cell_char_range": [0, 1181]}` (example):
row and column are one-based within the source block's table data, and cell
offsets are zero-based/end-exclusive. This metadata is additive; existing keys,
locators and generation handling are unchanged. `content_sha256` covers the
entire returned text, including repeated context. A budget too small to retain
the full row key/other cells plus overlap raises `ValueError`; no orphaned cell
fragment is returned. IDs bind
version, full parser/chunker profiles, locator, source ordinal, offsets, and text
hash. They do not bind storage path or generation. Worker must attach
`generation_id` and document/store/projection fields after chunking. Blocks are
not full `Candidate` objects and should not be passed wholesale to that model.

`expand_parent(chunks, hit_id, *, radius, max_chars)` lives in `parsing.parent`.
Caller supplies an authorized complete manifest with `id`, `text`, `ordinal`,
`parent_id`, `version_id`, and `generation_id`. It returns only
`{"text": str, "chunk_ids": list[str], "truncated": bool}`. It finds the unique
hit first, then takes ordinal neighbors in its same parent/version/generation.
Whole hit text is always retained, even if the hit alone exceeds the budget;
`truncated=True` discloses that case. Missing/ambiguous hits and duplicate sibling
ordinals are errors. This function does not replace caller authorization.

`LocalBlobStore(root)` in `storage.local` implements async `put(key, data,
sha256)` and `get(key)`. IO runs in a thread. Keys are controlled forward-slash
relative paths; traversal, Windows drive/UNC/ADS/reserved names, and existing
symlink/junction crossings are rejected. Writes publish a flushed complete file
via atomic no-replace hard link, allow byte-identical replay, and reject different
overwrites. The volume must support hard links and remain service-owned; these
checks do not replace filesystem isolation against hostile concurrent directory
replacement. Moving the root and constructing a new adapter preserves keys.
