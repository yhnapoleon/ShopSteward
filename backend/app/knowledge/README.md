# Knowledge K1 backend

Scope follows `docs/superpowers/plans/2026-09-07-k0-k1-execution.md`.
K1 stores originals and metadata only. No index job, parsing, extraction, search,
reindex or index activation is registered. Those belong to K2.

## HTTP contract

All routes use the existing user bearer identity, errors and role/store authorization.
Service identities are rejected. Reads require an authorized store (admin retains
existing all-store discovery). Writes require operator or admin.

| Method | Path under `/api/v1` | Body / result |
|---|---|---|
| POST | `/stores/{store_id}/documents` | multipart `file` + JSON text `metadata`; 201 Document |
| GET | `/stores/{store_id}/documents` | category, sku_id, supplier_id, status, q, cursor, limit; DocumentList |
| GET | `/documents/{document_id}` | Document metadata |
| PATCH | `/documents/{document_id}` | expected_metadata_version + metadata changes; Document |
| POST | `/documents/{document_id}/versions` | multipart `file` + JSON text `metadata`; 201 Document |
| GET | `/documents/{document_id}/versions` | descending version_no, cursor, limit; VersionList |
| GET | `/documents/{document_id}/versions/{version_id}` | Version metadata, with original-read authorization |
| GET | `/documents/{document_id}/versions/{version_id}/content` | original attachment; representation=original only |
| POST | `/documents/{document_id}/control` | archive/restore + expected_metadata_version; Document |

POST and PATCH require `Idempotency-Key` (1–128 characters). Same principal,
operation and key replay the original response; changed request returns 409.
Authorization is checked again before replay or fingerprint comparison. Replaying
an earlier accepted operation can return its historical metadata_version; GET the
document to fetch its current state. PATCH, append and control use CAS and a
PostgreSQL document row lock; concurrent different writes at the same expected
metadata version have exactly one winner. All idempotent writes lock the receipt
before the document to keep lock ordering consistent.

Create metadata (unknown fields, including owner/store overrides, are rejected):

```json
{
  "title": "Delivery notes",
  "category": "general",
  "visibility": "store",
  "sku_ids": ["sku_001"],
  "supplier_ids": ["supplier_001"],
  "valid_from": "2026-09-01T00:00:00Z",
  "valid_until": null
}
```

Only title is required for create. Default category is general, visibility is store,
entity arrays are empty, validity bounds are null. Title <=300 characters, category
<=64, each entity array <=100; IDs are deduplicated and sorted. Store must exist in
`stores`, SKU in the store's `products`, and supplier in its `supplier_offers`.
No names or alternate IDs are resolved heuristically. Entity filters undergo the
same existence validation. The store ID in the path selects the scope and never
grants permission by itself.

Append metadata has required `expected_metadata_version` and optional valid_from /
valid_until only. Dates require timezone offsets; valid_until must follow valid_from.
PATCH accepts title/category/visibility/sku_ids/supplier_ids, requires at least one
non-null change and expected_metadata_version. Owner and store cannot be changed.
Control is `{"operation":"archive","expected_metadata_version":1}` or restore.

Document includes id, store_id, owner_principal_id, metadata, metadata_version,
status (active/archived), latest_version_id, ingestion_status=UPLOADED,
indexing_status=NOT_INDEXED, created_at and updated_at. Latest upload is NOT a
published/current business or searchable version. There are no active index pointers
or job_run_id in K1 responses. Version includes id, document_id, version_no,
original_name, mime_type, content_sha256, size_bytes, created_by, created_at and
validity; storage keys and local paths are never returned by the API.

Document lists default to active and sort by immutable created_at/id descending;
`q` is a literal, case-insensitive title substring, not full-text search. Cursor
scope binds identity, grants and filters. Version lists sort by version_no descending.
Both use limit 1–100 (default 20), items + next_cursor. Pagination is keyset-based,
not a cross-request snapshot; changes to filters/visibility can change membership.

Private documents are readable/manageable only by owner. Admin may discover their
metadata via list/detail, but cannot list versions, download, append, change their
visibility or control another owner's private document. Archive removes documents
from default lists and denies version/original reads to every identity until restore;
authorized metadata discovery and restore remain available. Store grants are always
required for non-admin owners. Authorization is evaluated for each request; already
sent response bytes cannot be revoked retrospectively.

## Storage and validation

Only `settings.knowledge_storage_root` chooses the directory, default `var/knowledge`.
Relative paths resolve against the API process **working directory**, e.g. starting
from backend resolves to backend/var/knowledge; set an absolute persistent path when
running under a service manager. No second storage-path environment variable exists.
The application creates the directory on upload; it does not expose a static mount.

Each multipart stream writes to an exclusively created random UUID `.raw` key;
user filenames only become safe display basenames. File bytes are counted while
receiving, regardless of Content-Length. Limit: 20 MiB inclusive; metadata <=64 KiB;
headers <=64 KiB and the total body <=20 MiB +128 KiB. Exactly one file and one metadata
field are allowed. Upload and validation run outside DB transactions/Store locks;
blocking file/XML/ZIP work runs in the thread pool. SHA-256 covers exact original bytes.

PDF/DOCX/XLSX/CSV/MD/TXT only. Text formats require strict UTF-8 and reject binary
control characters. PDFs are read with **pypdf PdfReader(strict=True)**. Validation
uses actual is_encrypted state, requires a catalog, resolvable page tree with matching
nonzero page count, page boxes and valid content-stream references. A literal /Encrypt
in a comment or normal content is not an encryption flag. Broken reader structure and
actual encrypted PDFs return 422. This is structural validation, not rendering,
OCR, full object-graph/content-operator validation or proof that all pages contain text.
Conservative strict reading can reject repairable PDFs. K2 owns text coverage and
extraction quality assessment; no PDF text extraction runs during upload.

Office validation checks ZIP magic, CRC/decompression, standard OPC namespaces,
Content_Types declarations and a unique internal _rels/.rels officeDocument relationship
that resolves to the actual, correctly typed main part. It requires DOCX's namespaced
document/body, or XLSX's namespaced workbook/sheets, unique sheet identities, corresponding
internal sheet relationships and correctly typed worksheet/chartsheet/dialogsheet parts.
Only a worksheet requires sheetData; a standalone chart is retained as original content.
Both transitional and strict main-document namespaces are supported. Main parts are
resolved from package relationships, not assumed from hardcoded filenames. The current
XLSX path validates these sheet types structurally; charts and dialogs are not interpreted.

Limits remain: 2048 members, 100 MiB aggregate expanded data, 20 MiB per member. Duplicate,
traversal, encrypted and VBA members and XML DTD/entity declarations are rejected.
XML validation retains only the structural metadata needed for these checks, not text.
This is not full OOXML schema compliance, formula evaluation, content extraction or
malware scanning. Invalid format is 422; file/body size excess is 413.

Downloads resolve only server-owned key patterns within the configured root, reject
symlinks, check document/version association and force attachment, nosniff and
`Cache-Control: private, no-store`. Files are never overwritten by the application.
The directory is assumed to be protected from untrusted local writers by deployment.

PostgreSQL and filesystem do not share a transaction. A failed validation removes
only that request's exclusively created partial file. A successfully stored original
whose metadata validation/transaction fails, or whose request replays an existing
receipt, can remain an unreferenced orphan. No automated garbage collector is included;
cleanup must compare keys to committed `knowledge_versions.raw_key` with an age/race
safety policy. Never delete files just because an idempotency key or content hash
matches: another request can already reference its own distinct file. Backup both
PostgreSQL and the original directory.

## Schema and verification evidence (2026-09-07)

Migration `0010_knowledge` follows `0009_agent_scopes`. Two new tables in public:
knowledge_documents and knowledge_versions. Receipts reuse existing command_receipts.
GIN entity indexes and store/status/created_at/id paging index support metadata filters.
Version number and document/version identity are unique; a deferred composite FK
ensures latest_version_id belongs to that same document. A PostgreSQL trigger rejects
UPDATE/DELETE of versions. Database.ready now expects 0010 and checks both new tables.
Migration and application import the knowledge model metadata.

Tests use existing integration `db` fixture and real ASGI clients, not SQLite. The
runner reads backend/.env without printing credentials and changes only the URL's
database name to shopsteward_test, asserts that exact target, and passes it to subprocesses.
It never writes .env and does not monkeypatch readiness or start a business worker.
Tests are serial; do not run alongside another agent's clean_queue suite.

Commands from repository root (Windows Python path shown):

```powershell
.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py migrate
.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py schema-check
.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py heads
.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py tests/integration/test_knowledge_documents.py tests/unit/test_knowledge_storage.py tests/unit/test_knowledge_contract.py -q --tb=short
```

Observed TDD evidence, before corresponding fixes:

- Initial PG + ASGI suite: 12 failed (missing routes returned 404 instead of 201/422/413).
  Command: runner tests/integration/test_knowledge_documents.py -q --tb=line.
- PATCH replay test: 1 failed, 12 deselected; replay incorrectly returned 409 instead
  of original 200. Command: same file with -k patch_idempotency -q --tb=short.
- Corrupt compressed Office payload: 1 failed, 17 passed in unit storage tests;
  zlib.error escaped instead of 422. Fixed by explicit decompression-error mapping.
- With the temporary runner override removed, db fixture readiness failed against
  migrated head. Fixed in production session.py; runner contains no override.
- Out-of-range version cursor: 1 failed, 20 deselected; returned 503 rather than 422.
  Fixed by bounding the decoded cursor to PostgreSQL bigint range.

Intermediate GREEN: initial 12 PG tests passed; PATCH/readiness + storage run 31 passed;
expanded PG behavior run 20 passed. Final K1 command above: **40 passed in 13.62s**
(21 real PG/ASGI tests, 18 storage unit tests, 1 runtime OpenAPI test).
Targeted existing compatibility run:
`runner tests/integration/test_missions.py tests/integration/test_agent_knowledge.py -q --tb=short`
returned **5 passed in 3.14s**. Ruff over all owned Python files passed;
`uv lock --check --offline --cache-dir .uv-cache` passed (87 packages).
The test database was handed back to the coordinating agent after these runs.
Alembic check: `No new upgrade operations detected.` Current: `0010_knowledge (head)`.
Production dependencies added for K1 are python-multipart (locked to 0.0.32) and,
after independent review, pypdf (locked to 6.17.0), using this repository's .uv-cache. Full contract export, independent HTTP acceptance and
repository-wide regressions belong to the coordinating agent; this directory does
not alter docs contract exports or research artifacts.



### Independent P2 review fixes

The earlier 40-test and HTTP acceptance results predate the stronger validation.
Review reproduced both a false rejection of valid PDF comments/text containing
/Encrypt, and acceptance of a fake PDF/structurally incomplete Office package.

- RED, before storage changes: **16 failed, 18 passed in 2.56s**. Command:
  `.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/unit/test_knowledge_storage.py -q --tb=short`.
  Failures include the comment/text cases, fake PDF without objects/trailer, missing
  Office namespaces, main content type, package relationships, DOCX body, XLSX sheets,
  worksheet links/parts/sheetData, wrong relation target/type and external main target.
- GREEN with repaired minimal OPC fixtures: **34 passed in 2.64s**.
- Extended GREEN: **54 passed in 3.25s**, including actual encrypted PDF, independent
  readable-text PDF fixture check and **18 read-only K0 corpus PDF/DOCX/XLSX originals**.
  The corpus files were neither rebuilt nor modified. Positive Office fixtures now
  have real namespaces, content types, relationships and required main/sheet structures.
- K1 real PostgreSQL/ASGI regression:
  `.venv/Scripts/python.exe backend/tests/integration/test_knowledge_runner.py tests/integration/test_knowledge_documents.py -q --tb=short`
  returned **21 passed in 11.39s**. The test database was handed back immediately after
  this run. Migration/schema/API behavior was unchanged; head remains 0010_knowledge.
- The coordinating agent owns rerunning HTTP acceptance and the cross-service test.
  No foundation API test, runner, exported contract, research or corpus file was edited
  for this review fix. There was no development/IH database operation or commit.

Final pure-unit check including test_knowledge_contract.py: **55 passed in 6.94s**.
Ruff on storage and its unit tests, uv lock --check --offline --cache-dir .uv-cache
(88 packages), and git diff --check passed after formatting cleanup.
