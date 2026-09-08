# Knowledge local startup and portable restore

For GitHub/PR handoff to the server owner, start with the
[server handoff guide](knowledge-server-handoff.md). This file remains a local
rehearsal/restore procedure, not a verified public-cloud deployment configuration.

This is the C2 operator procedure for the independent
`shopsteward-knowledge-precloud` project. Run commands from the repository root.
The existing business backend/Agent remain local; this Compose file contains only
Knowledge API, its worker, PostgreSQL, and OpenSearch. Existing ports 8000/8001,
`infra/.env`, and `infra/compose.yaml` are outside this procedure.

## Current verification boundary

On 2026-09-08 the user started Docker Desktop; elevated Docker access confirmed
daemon 29.6.2. The independent helper's `check`, `build`, `migrate`, and `start`
have now passed. API `/health/live` and `/health/ready` both returned HTTP 200 at
`http://127.0.0.1:8020`. API, PostgreSQL, and OpenSearch are healthy; the worker
is running (it has no Compose healthcheck). Keep all four services running for
the main task's further integration tests; do not run the optional stop command
below during that handoff.

The dedicated `shopsteward_knowledge_test` database is at `knowledge_0002`, on
PostgreSQL 17.11 at loopback 55434. OpenSearch reports 3.8.0 and green cluster
health at loopback 19201. The API runs as UID 10001, its data volume is writable,
parser dependencies import successfully, and its sole enabled profile is
`lexical-v1`; no reranker is configured. This infra continuation made no model
calls. Service credentials are in `var/knowledge-precloud/private.env`; consumers
must read them privately rather than print or copy them into reports.

The built `shopsteward-knowledge:precloud` image content ID is
`sha256:4c4130e2f71ccc89ec36ebc20fc7456678835d19ba6b7f492dad8e10e5093ae2`.
The helper's `var/knowledge-precloud/shopsteward-knowledge-precloud.json` holds
the four resolved dependency digests and lock hash. Sanitized live evidence is
in `var/knowledge-precloud/infra-ready.json`, with execution notes in
`var/knowledge-precloud/infra-execution.md`. This is a local image content ID,
not a pushed registry digest.

Two real infra failures were reproduced and fixed: BuildKit could not read the
Windows-protected `knowledge/.pytest_cache` directory (cache directories are now
explicitly excluded), and the helper decoded Compose's UTF-8 output as GBK
(subprocess decoding is now explicitly UTF-8). Real rebuilding passed after the
context fix; a real child-process regression reproduced the decoding failure
before the helper fix and passed afterward. Image pulls succeeded at the planned
versions; no registry fallback or version downgrade was needed.

PostgreSQL dump/restore, live index reconstruction, full corpus retrieval, and
HTTP relocation acceptance are not established by these infra checks. Subsequent
main-task checks verified 200 published documents, 5169 matching PG/index chunks,
and four real Agent scenarios; see the [integration report](../reports/agent-document-langgraph-integration.md).
Independent scoped infra source review is complete; live restore/lifecycle is
still outstanding. PostgreSQL and OpenSearch boundary doubles in unit tests are
**not integration evidence**.

Scoped verification commands:

```powershell
./.venv/Scripts/python.exe -m pytest -c knowledge/pyproject.toml knowledge/tests/test_bundle.py knowledge/tests/test_readiness.py -q
./.venv/Scripts/python.exe -m pytest -c knowledge/pyproject.toml knowledge/tests/test_infra_local.py knowledge/tests/test_bundle.py -q
./.venv/Scripts/python.exe -m ruff check infra/knowledge_local.py knowledge/tests/test_infra_local.py
./.venv/Scripts/python.exe -m ruff check knowledge/src/shopsteward_knowledge/bundle.py knowledge/src/shopsteward_knowledge/readiness.py knowledge/tests/test_bundle.py knowledge/tests/test_readiness.py knowledge/tools/restore_bundle.py backend/tools/export_knowledge_bundle.py infra/knowledge_local.py
```

The latest infra/bundle run passed 48 tests with one Windows symlink skip; the
scoped helper/test Ruff check passed. The earlier bundle/readiness scoped run
passed 90 tests; one symlink test skipped because this Windows host
does not permit creating the test symlink. The broader non-integration knowledge
run at handoff had 226 passes and one failure in the separately owned
`test_pg_traversal_starts_at_frontier_not_first_scope_wide_edges`; that result is
not a C2 integration pass. An offline `uv lock --check` could not validate the
workspace lock because the temporary cache lacked `langchain-openai` metadata
for an alternate-platform resolution. Root dependency files were not changed by C2.

OpenSearch initially uses `opensearchproject/opensearch:3.8.0`, following the
controller's official release check (August 4, 2026). See the
[official downloads](https://opensearch.org/downloads/). Do not substitute the old
K0 2.17.1 image. Python 3.12 and uv 0.12.10 are the initial build tags; the build
uses the [documented uv workspace Docker pattern](https://docs.astral.sh/uv/guides/integration/docker/).
OpenSearch 3.8.0 startup and API dependency readiness are now verified; corpus
retrieval compatibility and performance need the main integration run. Dependency
digests in the build receipt came from real pulls, not guessed values.

## Configure, check, build, migrate, start

1. Manually start Docker Desktop when ready. The helper never launches it, kills
   port owners, or starts another business backend. It uses hidden Windows CLI
   processes and records container IDs plus daemon-side PIDs in
   `var/knowledge-precloud/<project>.json`. PIDs are Docker VM PIDs, not Windows
   application PIDs. `stop` uses only recorded container IDs and retains volumes.
2. Copy `knowledge/.env.example` to `var/knowledge-precloud/private.env` using a
   private file/secret manager. Set random `KNOWLEDGE_SERVICE_KEY` and
   `KNOWLEDGE_POSTGRES_PASSWORD`; the latter must be URL-safe (`A-Z a-z 0-9 _ -`).
   Do not put keys in a committed file. The helper rejects template credentials,
   duplicate keys, variable expansion, and non-test database names.
3. Use these explicit commands:

   ```powershell
   ./.venv/Scripts/python.exe infra/knowledge_local.py check
   ./.venv/Scripts/python.exe infra/knowledge_local.py build
   ./.venv/Scripts/python.exe infra/knowledge_local.py migrate
   ./.venv/Scripts/python.exe infra/knowledge_local.py start
   ./.venv/Scripts/python.exe infra/knowledge_local.py status
   ```

`check` validates Compose and checks ports 8020, 55434, and 19201 by binding to
127.0.0.1. Run it before startup; an already running project's ports are expected
to be occupied. `start` permits existing containers only when they are in this
helper's ownership record, checks ports for services it is about to start, and
waits for API readiness. Do not remove the ownership record while containers
exist. An unknown container under the project name causes a refusal, not adoption.

`build` pulls the initial base/dependency tags, resolves their registry digests,
builds against those digests, and records the image content ID, resolved references,
and SHA256 of `uv.lock`. Subsequent helper commands load the pinned references
from that receipt. Distribute the receipt with the corresponding image; a local
built image's content ID is not a pushed registry RepoDigest. For another machine,
use `docker image save`/`load` for that exact image, or push it to an authorized
registry and record the resulting registry digest. No push is performed here.
Copy the receipt's pinned references into the receiving private configuration.

Build context is the repository root. The root `.dockerignore` allowlists workspace
metadata, knowledge source, and migrations; it excludes environment files, `var`,
`.venv`, IH, evaluations/gold, and unrelated originals. `uv sync --locked --package
shopsteward-knowledge --no-dev --no-editable --extra service --extra parsers --extra
opensearch` installs only the knowledge runtime from the workspace lock. The
runtime runs as UID/GID 10001 with a data volume and read-only root filesystem.

`migrate` is an explicit maintenance step: it starts only the dedicated PostgreSQL
service and executes `python -m alembic -c /app/knowledge/alembic.ini upgrade head`.
It does not run the business database migrations. API and worker never migrate
automatically. The confirmed API command is `python -m uvicorn
shopsteward_knowledge.api:create_app --factory`; worker is `python -m
shopsteward_knowledge.worker`. API health is `/health/live` and `/health/ready`.
Readiness includes database schema and OpenSearch, and fails without a service key.

After startup, use the C1 corpus importer against the designated test backend,
through its real upload/index-job/publish APIs. Check its CLI `--help` for the current
manifest/mapping parameters. Do not seed the service tables directly as an import
shortcut. Complete the C3 real HTTP and fixed-query checks before marking import
or retrieval acceptance passed. Finally:

```powershell
./.venv/Scripts/python.exe infra/knowledge_local.py stop
```

## Credentials, storage, profiles, and network scope

| Setting | Local meaning | Future cloud change |
| --- | --- | --- |
| `KNOWLEDGE_DATABASE_URL` | Host process URL; Compose constructs its private `postgres:5432` URL | Dedicated service PG URL with TLS and scoped credentials |
| `KNOWLEDGE_STORAGE_ROOT` | Host storage root; Compose uses `/data/knowledge` on its own volume | Persistent volume/object-store adapter with identical storage keys |
| `KNOWLEDGE_OPENSEARCH_URL` | Host `http://127.0.0.1:19201`; Compose uses private `opensearch:9200` | Authenticated private/TLS index endpoint |
| `KNOWLEDGE_SERVICE_KEY` | Internal service authentication, delivered via private environment | Secret manager; also update the authorized backend client |
| `KNOWLEDGE_INDEX_PREFIX` | Project-specific index namespace | New isolated namespace per deployment/restore |
| `KNOWLEDGE_*_IMAGE` | Initial tags replaced with receipt digests | Same tested image digests |

Compose publishes only API 8020, PG 55434, and OpenSearch 19201, on 127.0.0.1.
OpenSearch security is disabled **only for this local isolated rehearsal**. This
file is not a cloud security configuration; do not expose these ports publicly.
The helper and bundle CLIs reject arbitrary remote targets in this first version.

`lexical-v1` is selected in API requests and needs no model key. Current service
`Settings` consumes the example's embedding URL, API key, model, dimensions, and
separate query/document instructions. Complete embedding configuration enables
`hybrid-v1`; complete rerank URL/key/model configuration enables the reranker.
Blank optional fields remain absent, leaving both providers disabled in this
rehearsal. Filling those fields may enable provider calls and requires the
corresponding authorization. No embedding or paid provider call occurs in the
bundle/rebuild tools. The example does not implement a separate cost-meter or
billable-run switch.

## Consistent export from dedicated test sources

Prerequisites: local PostgreSQL client programs `pg_dump` and `pg_restore` on PATH
with a major version compatible with both servers, the same application checkout
and migrations as the source, and separate authority/derived **test** databases.
These client programs were not found on PATH during implementation. Install or
provide the matching client tools before the live rehearsal; `--verify-only`
does not require them, asyncpg, Docker, or a database connection.

Pause this task's upload/publisher/ingestion producers and drain their work first.
Wait for all `knowledge_delivery_outbox` and `knowledge_jobs` rows to be terminal
(`SUCCEEDED` or `FAILED`); pending/running/retry rows cause export to refuse. Stop
only the dedicated test processes through their owning launcher. Do not pause
the existing business services or hold a request-path transaction open. A paused
task must remain paused until export returns. If that cannot be arranged, do not
use the flag below: a cross-service consistency watermark implementation would
be required instead.

Set `KNOWLEDGE_BUNDLE_AUTHORITY_DATABASE_URL` and
`KNOWLEDGE_BUNDLE_DERIVED_DATABASE_URL` in the current process environment from
private configuration. Both must be explicit PostgreSQL URLs to local databases
named `shopsteward..._test...`; names must differ. Database URL query overrides
are rejected. No CLI argument contains a database URL or password, and no `.env`
is loaded by the export/restore CLIs.

```powershell
./.venv/Scripts/python.exe backend/tools/export_knowledge_bundle.py `
  --target-test --writers-paused `
  --authority-storage <absolute-test-backend-originals-root> `
  --derived-storage <absolute-test-knowledge-storage-root> `
  --output <new-empty-task-bundle-directory>
```

`--writers-paused` is an operator attestation, not a command that stops arbitrary
processes. In addition, export discovers **all public tables**, obtains SHARE
locks across both source databases, checks work is drained, and keeps both lock
sets until custom-format `pg_dump --snapshot` archives, JSON snapshots, originals,
and parsed storage are copied. Lock acquisition fails after 5 seconds rather than
waiting indefinitely. The explicit offline maintenance transaction spans backup
I/O to provide a coherent image; normal API/worker transactions must not do so.
No DDL, storage mutation, or external sequence allocation may run during this
maintenance window. Non-public application schemas are rejected rather than
silently left outside the lock set.

The bundle includes:

- `authority/database.dump`, all-table `snapshot.json`, migration scripts/revision,
  and immutable `originals/<raw_key>` paths (including the existing `.raw` suffix).
  This full test database archive includes the authority's other tables; it is
  not suitable for arbitrary production database extraction.
- `derived/database.dump`, all-table snapshot, migration scripts/revision, and
  `storage/` with all original/parsed artifacts. Parsed chunks, parse coverage,
  parent context, and generation manifests also remain in the derived PG archive.
- `profiles.json`, listing retrieval profiles and generation parse manifests.
  Publication pointers and relation snapshots are in the all-table snapshots.
- `bundle-manifest.json`, listing every payload's portable relative path, size,
  and SHA256, plus both source database names and revisions. Connection credentials
  are excluded. Keep the matching application image and build receipt separately.

Export validates source references using the current tables: `stores`, store-scoped
`products.sku_id`, and `supplier_offers.supplier_id`. New tables are discovered and
included; they are not silently omitted by a fixed export table list. It verifies
original hashes, publication-generation correspondence, relation evidence, and
READY generation manifests. It emits only counts on success. Failures retain an
incomplete task output for inspection; rerun into a new empty directory.

## Offline verification

```powershell
./.venv/Scripts/python.exe knowledge/tools/restore_bundle.py `
  --bundle <bundle-directory> --target-test --verify-only
```

This reads files only. It rejects missing files, changed size/hash, unlisted files,
duplicate/case-alias paths, Windows-unsafe/absolute/traversing paths, links/junctions,
environment files, unknown data revisions, missing migration revisions, broken
entity/original/publication/relation references, and changed generation manifests.
It does not execute migration Python or SQL. A checksum manifest proves internal
integrity, not sender authenticity: actual restore executes SQL from trusted
operator-created PostgreSQL archives. Transfer the manifest hash by a trusted
channel and retain the matching build receipt.

## Restore into a separate empty rehearsal project

Never restore into the source project or reuse its volumes. Choose a new project
such as `shopsteward-knowledge-precloud-restore-r1`, fresh private configuration,
three unused ports (for example 8022/55435/19202),
`KNOWLEDGE_POSTGRES_DB=shopsteward_knowledge_test_r1`, and
`KNOWLEDGE_INDEX_PREFIX=shopsteward-restore-test-r1`. Use the recorded pinned image
references and exact application build. Do **not** run migrations before restore:
`pg_restore` restores schema and data into the empty database.

For this restore procedure, operate Compose explicitly under its new project
name. Do not mix manually created containers with the helper's ownership record.
Every command below uses the new file/project, not `infra/.env` or the existing
Compose project:

```powershell
$restoreCompose = @('--project-name', 'shopsteward-knowledge-precloud-restore-r1',
  '--env-file', '<absolute-private-restore.env>', '--file', 'infra/compose.knowledge.yaml')
docker compose @restoreCompose up -d --wait postgres opensearch
docker compose @restoreCompose exec -T postgres createdb -U knowledge shopsteward_authority_test_r1
```

The dedicated PG service creates the empty derived database named in its private
configuration. The `createdb` command creates a second empty authority test DB;
it fails if that name exists. Before starting, check that the chosen project has
no containers or volumes and its ports are free. Do not remove pre-existing
volumes to force that check to pass. `docker compose config --quiet` can validate
the new configuration without printing credentials.

Set these process environment variables privately:

- `KNOWLEDGE_RESTORE_AUTHORITY_DATABASE_URL`: the new authority test DB.
- `KNOWLEDGE_RESTORE_DERIVED_DATABASE_URL`: the new derived test DB.
- `KNOWLEDGE_RESTORE_OPENSEARCH_URL`: the new loopback OpenSearch endpoint.

```powershell
./.venv/Scripts/python.exe knowledge/tools/restore_bundle.py `
  --bundle <bundle-directory> --target-test `
  --storage-target <new-empty-restored-storage-directory> `
  --index-prefix shopsteward-restore-test-r1
```

The tool verifies the entire bundle before any target connection. It rejects
source database names even through a different host alias, nonempty DBs/storage,
other database clients, incompatible migrations/profiles, and existing index
prefixes. Each target DB has a cooperative session advisory lock to prevent two
restore invocations racing. Keep all target services/writers stopped and restrict
target access throughout restore; this is an exclusive maintenance operation.

It preflights the empty search namespace without writing, restores each PG archive
in its own transaction without `--clean` or `--create`, compares all restored table
rows with the snapshot, restores files with exclusive creation, and compares hashes.
Then it rebuilds compatible lexical generation indexes from the persisted parsed
chunks (including original-version references), verifies index counts, and reads
back all candidate payloads. No vector snapshot is assumed portable and no model
calls are made. Parser-only parent context remains in PG and is not sent as an
unknown Candidate field to OpenSearch.

Only `lexical-v1` is supported by this automatic rebuild. An incompatible profile
causes a refusal before restore writes. A new embedding/parser profile requires
normal reingestion from the restored immutable originals into **new generation
IDs**, validation, and explicit publication; do not reinterpret or overwrite an
old vector space. This first C2 tool does not automate that profile conversion.

The returned storage directory contains `authority/` and `derived/`. Point the
isolated backend at `authority/`. To populate the **new empty** Compose knowledge
data volume from `derived/`, while its API/worker are stopped:

```powershell
docker compose @restoreCompose run --rm --no-deps `
  --volume '<absolute-restored-storage-directory>/derived:/restore-source:ro' `
  --entrypoint python api -c "import pathlib,shutil; dst=pathlib.Path('/data/knowledge'); assert not any(dst.iterdir()), 'volume must be empty'; shutil.copytree('/restore-source',dst,dirs_exist_ok=True)"
docker compose @restoreCompose up -d --no-build --wait api worker
```

The copy runs as the image's unprivileged UID and checks the destination is empty.
Configure a separate test backend process against the restored authority DB and
API URL for C3 checks. Confirm identical publication pointers, relations, original
hashes, and fixed scoped query results through real HTTP. The restore result
explicitly says `fixed_queries: not_run`; successful rebuilding alone cannot mark
query or Agent acceptance passed. Stop only this restore project's services with
`docker compose @restoreCompose stop`; retain volumes and failed targets for review.
The two databases and filesystem/index cannot share one atomic transaction: any
partial failure is reported as failure, retains partial targets, and requires new
empty targets for another attempt. No automatic destructive cleanup is provided.

## Readiness and the next cloud step

### Bind the authored synthetic relations

After the normal corpus importer has uploaded, indexed and published the test
documents, use its saved receipts and the same explicit entity mapping:

```powershell
./.venv/Scripts/python.exe backend/tools/import_knowledge_relations.py `
  --manifest docs/evaluation/knowledge-expanded/manifests/pilot.json `
  --mapping var/precloud/fixture-mapping.json `
  --receipts var/precloud/import-receipts.json `
  --output var/precloud/relation-import.json --target-test
```

The tool reads `KNOWLEDGE_IMPORT_TOKEN` and `KNOWLEDGE_SERVICE_KEY` from the
environment and permits only isolated loopback endpoints. Run with `--dry-run`
to check quotes offline without receipts, service calls or relation writes.
Offline chunk identities use fixture version IDs and are not server evidence.

The actual import reparses the verified original with the uploaded version ID
and the worker's chunk profile, requires a unique complete quote, checks the
current backend publication and evidence revision, and compares service evidence
text/hash/locator/original identity before submitting a confirmed synthetic edge.
Conditions remain the explicitly authored scalar atoms, including `store_fixture`
and `scenario_id`; callers must supply all of them in `relation_context`.
`SUPPLIES` and the explicitly declared `HAS_APPLICABLE_DOCUMENT` lookup are
retrieval directions, not procurement or substitution authority. Missing proofs
or endpoint mappings fail closed. Public-source claims require a separate reviewed
intake workflow; this importer accepts only the authored synthetic assertion schema.

The service gives identical edges deterministic IDs, so a retry after a lost
response does not add a duplicate. Old import receipts without `index_profile_id`
must be refreshed through the normal corpus importer before relation import.
Metadata changes or replacement publications require current receipts and source
verification again; do not mark a failed relation as confirmed manually.

`ready_for_cloud_pilot(checks)` requires exactly these six evidence keys to all
have the string value `passed`: `corpus_200`, `real_http`, `restore`, `versioning`,
`agent_tools`, `build`. Missing, skipped, failed, boolean, or not-run values fail
the gate. Extra fields do not substitute for a required check.

`cloud_model_quality`, `cloud_latency`, and `cloud_cost` remain separately reported
and may be `not_run` for a local pilot. Local readiness is not MVP readiness: A3
and real cloud quality acceptance still apply. Before moving configuration to
cloud, validate credentials, TLS/private networking, provider profiles, budget,
and actual query/document performance against the same frozen corpus. Current
loopback results, when available, must not be presented as cloud latency or SLA.
