import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def write_manifest(root, manifest):
    (root / "bundle-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    snapshots = {
        "authority": {
            "knowledge_documents": [
                {"id": "D1", "store_id": "S1", "sku_ids": ["SKU1"], "supplier_ids": ["SUP1"]}
            ],
            "knowledge_versions": [
                {
                    "id": "V1",
                    "document_id": "D1",
                    "raw_key": "abc.raw",
                    "content_sha256": hashlib.sha256(b"raw").hexdigest(),
                    "size_bytes": 3,
                }
            ],
            "stores": [{"id": "S1"}],
            "products": [{"store_id": "S1", "sku_id": "SKU1"}],
            "supplier_offers": [{"store_id": "S1", "sku_id": "SKU1", "supplier_id": "SUP1"}],
            "knowledge_publications": [],
        },
        "derived": {
            "knowledge_originals": [
                {
                    "version_id": "V1",
                    "storage_key": "originals/abc",
                    "sha256": hashlib.sha256(b"raw").hexdigest(),
                    "size_bytes": 3,
                }
            ],
            "knowledge_index_generations": [],
            "knowledge_chunks": [],
            "knowledge_relations": [],
            "knowledge_jobs": [],
            "knowledge_projections": [],
        },
    }
    contents = {
        "authority/database.dump": b"fixture archive",
        "derived/database.dump": b"fixture archive",
        "authority/originals/abc.raw": b"raw",
        "derived/storage/originals/abc": b"raw",
        "profiles.json": b'{"retrieval": ["lexical-v1"], "embedding": []}',
        "authority/snapshot.json": json.dumps(snapshots["authority"]).encode(),
        "derived/snapshot.json": json.dumps(snapshots["derived"]).encode(),
        "authority/migrations/versions/one.py": b"revision = 'a1'\ndown_revision = None\n",
        "derived/migrations/versions/one.py": b"revision = 'k1'\ndown_revision = None\n",
    }
    manifest = {
        "format_version": 1,
        "data_revision": 1,
        "files": [],
        "databases": {
            group: {"name": f"shopsteward_{group}_test", "revisions": [revision]}
            for group, revision in [("authority", "a1"), ("derived", "k1")]
        },
        "index": {"mode": "rebuild-lexical", "profile_id": "lexical-v1"},
    }
    for name, data in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest["files"].append(
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        )
    write_manifest(root, manifest)
    return root, manifest


def replace_file(root, manifest, name, value):
    data = json.dumps(value).encode()
    (root / name).write_bytes(data)
    item = next(item for item in manifest["files"] if item["path"] == name)
    item.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    write_manifest(root, manifest)


def test_verify_valid_bundle_counts_bytes(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    assert verify_bundle(root) == {
        "files_verified": 9,
        "bytes_verified": sum(i["size"] for i in manifest["files"]),
    }


def test_restore_rejects_missing_original(tmp_path):
    from shopsteward_knowledge.bundle import verify_bundle

    write_manifest(
        tmp_path, {"files": [{"path": "originals/missing.raw", "sha256": "0" * 64, "size": 1}]}
    )
    with pytest.raises(ValueError, match="missing"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize("mutation", ["hash", "size", "missing", "unlisted", "duplicate"])
def test_detects_corrupt_or_unaccounted_files(bundle, mutation):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    path = root / "authority/originals/abc.raw"
    if mutation == "hash":
        path.write_bytes(b"bad")
    elif mutation == "size":
        path.write_bytes(b"longer")
    elif mutation == "missing":
        path.unlink()
    elif mutation == "unlisted":
        (root / ".env").write_text("must not ship")
    else:
        manifest["files"].append(manifest["files"][0])
        write_manifest(root, manifest)
    with pytest.raises(ValueError):
        verify_bundle(root)


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "C:/secret",
        "a/../../b",
        "a\\b",
        "a//b",
        "a/./b",
        "a:stream",
        "NUL",
        "a.",
    ],
)
def test_rejects_nonportable_or_escaping_paths(bundle, name):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    manifest["files"][0]["path"] = name
    write_manifest(root, manifest)
    with pytest.raises(ValueError):
        verify_bundle(root)


def test_rejects_link_even_when_destination_is_in_bundle(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, _ = bundle
    path = root / "authority/originals/abc.raw"
    path.unlink()
    try:
        path.symlink_to(root / "derived/storage/originals/abc")
    except OSError:
        pytest.skip("host does not permit symlinks")
    with pytest.raises(ValueError, match="link"):
        verify_bundle(root)


def test_incompatible_data_revision(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    manifest["data_revision"] = 999
    write_manifest(root, manifest)
    with pytest.raises(ValueError, match="revision"):
        verify_bundle(root)


def test_database_revision_must_exist_in_bundled_migrations(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    manifest["databases"]["derived"]["revisions"] = ["unknown"]
    write_manifest(root, manifest)
    with pytest.raises(ValueError, match="revision"):
        verify_bundle(root)


def test_missing_entity_mapping(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    snapshot = json.loads((root / "authority/snapshot.json").read_text())
    snapshot["products"] = []
    replace_file(root, manifest, "authority/snapshot.json", snapshot)
    with pytest.raises(ValueError, match="entity mapping"):
        verify_bundle(root)


def test_original_reference_must_match_snapshot_hash(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    snapshot = json.loads((root / "derived/snapshot.json").read_text())
    snapshot["knowledge_originals"][0]["sha256"] = "0" * 64
    replace_file(root, manifest, "derived/snapshot.json", snapshot)
    with pytest.raises(ValueError, match="original"):
        verify_bundle(root)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:secret@localhost/shopsteward",
        "sqlite:///test.db",
        "postgresql://u:p@remote/db_test",
        "postgresql://u:p@localhost/shopsteward_test?options=x",
    ],
)
def test_database_guard_rejects_unsafe_targets(url):
    from shopsteward_knowledge.bundle import database_spec

    with pytest.raises(ValueError):
        database_spec(url)


def test_database_guard_keeps_credentials_out_of_public_identity():
    from shopsteward_knowledge.bundle import database_spec

    spec = database_spec("postgresql+asyncpg://u:secret@127.0.0.1:55434/shopsteward_test")
    assert spec["name"] == "shopsteward_test"
    assert "secret" not in repr(spec)


def test_restore_verify_only_requires_no_database_or_pg_programs(bundle):
    root, _ = bundle
    result = subprocess.run(
        [
            sys.executable,
            "-S",  # No site-packages: verification is standard-library-only.
            str(REPO / "knowledge/tools/restore_bundle.py"),
            "--bundle",
            str(root),
            "--target-test",
            "--verify-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["files_verified"] == 9


def test_restore_corruption_precedes_target_or_database_access(bundle, tmp_path):
    root, _ = bundle
    (root / "authority/database.dump").write_bytes(b"bad")
    target = tmp_path / "untouched"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "knowledge/tools/restore_bundle.py"),
            "--bundle",
            str(root),
            "--target-test",
            "--storage-target",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not target.exists()
    assert "checksum" in result.stderr or "size" in result.stderr


def test_mapping_from_another_store_is_not_valid(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    snapshot = json.loads((root / "authority/snapshot.json").read_text())
    snapshot["products"][0]["store_id"] = "OTHER"
    replace_file(root, manifest, "authority/snapshot.json", snapshot)
    with pytest.raises(ValueError, match="entity mapping"):
        verify_bundle(root)


def load_local():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "knowledge_local", REPO / "infra/knowledge_local.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_port_check_refuses_listener_without_killing_it():
    import socket

    local = load_local()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(ValueError, match="occupied"):
            local.check_ports([port])
        assert listener.getsockname()[1] == port


def test_local_docker_down_does_not_launch_desktop(monkeypatch, capsys):
    local = load_local()
    commands = []

    def run(argv, **kwargs):
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "daemon unavailable")

    monkeypatch.setattr(local.subprocess, "run", run)
    assert local.main(["check"]) == 2
    assert len(commands) == 1
    assert commands[0][1] == "info"
    assert "manually" in capsys.readouterr().err


def test_local_env_rejects_nonlocal_or_existing_project(tmp_path):
    local = load_local()
    env = tmp_path / "test.env"
    env.write_text("KNOWLEDGE_SERVICE_KEY=private\nKNOWLEDGE_POSTGRES_PASSWORD=private\n")
    with pytest.raises(ValueError, match="project"):
        local.Manager(env_file=env, project="shopsteward", state_dir=tmp_path)


def test_restore_refuses_source_database_before_connecting(bundle, tmp_path, monkeypatch):
    import asyncio

    from shopsteward_knowledge import bundle as module

    root, _ = bundle

    async def forbidden(_):
        pytest.fail("unsafe target attempted connection")

    monkeypatch.setattr(module, "connect_database", forbidden)
    with pytest.raises(ValueError, match="distinct from source"):
        asyncio.run(
            module.restore_bundle(
                root=root,
                storage_target=tmp_path / "new",
                repo=REPO,
                authority_url="postgresql://u:p@localhost/shopsteward_authority_test",
                derived_url="postgresql://u:p@localhost/shopsteward_derived_test_restore",
                opensearch_url="http://localhost:19201",
                index_prefix="shopsteward-restore-test-one",
            )
        )


def ready_snapshot():
    text = "cold storage"
    candidate = dict(
        document_id="D1",
        version_id="V1",
        generation_id="G1",
        chunk_id="C1",
        metadata_revision=1,
        text=text,
        title="Storage",
        store_id="S1",
        locator={"kind": "paragraph", "paragraph_range": [1, 1]},
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    # Persisted chunks also carry parser-only context; index Candidate forbids extras.
    payload = {**candidate, "parent_text": "context retained in PG"}
    canonical = json.dumps(
        {"chunks": [payload]}, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return {
        "knowledge_index_generations": [
            dict(
                id="G1",
                version_id="V1",
                state="READY",
                profile_id="lexical-v1",
                manifest_hash=digest,
                chunk_count=1,
            )
        ],
        "knowledge_chunks": [
            dict(generation_id="G1", version_id="V1", chunk_id="C1", payload=payload)
        ],
    }


async def test_rebuild_lexical_uses_persisted_payload_without_parser_extras(monkeypatch):
    import httpx

    from shopsteward_knowledge import bundle as module

    snapshot = ready_snapshot()
    second = json.loads(json.dumps(snapshot))
    second["knowledge_index_generations"][0].update(id="G2", version_id="V2")
    second_row = second["knowledge_chunks"][0]
    second_row.update(generation_id="G2", version_id="V2")
    second_row["payload"].update(generation_id="G2", version_id="V2")
    serialized = json.dumps(
        {"chunks": [second_row["payload"]]},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    second["knowledge_index_generations"][0]["manifest_hash"] = hashlib.sha256(
        serialized.encode()
    ).hexdigest()
    for key in snapshot:
        snapshot[key].extend(second[key])
    indexed = {}

    def handle(request):
        if "/_cat/indices/" in request.url.path:
            return httpx.Response(200, json=[])
        if request.method == "PUT":
            return httpx.Response(200, json={"acknowledged": True})
        if request.url.path == "/_bulk":
            lines = request.content.decode().splitlines()
            for offset in range(0, len(lines), 2):
                indexed[json.loads(lines[offset])["index"]["_id"]] = json.loads(lines[offset + 1])
            return httpx.Response(200, json={"errors": False})
        if request.url.path.endswith("/_count"):
            generation = json.loads(request.content)["query"]["term"]["generation_id"]
            return httpx.Response(
                200,
                json={"count": sum(row["generation_id"] == generation for row in indexed.values())},
            )
        if request.url.path.endswith("/_search"):
            requested = json.loads(request.content)["query"]["ids"]["values"]
            return httpx.Response(
                200,
                json={
                    "hits": {
                        "hits": [
                            {"_id": key, "_source": indexed[key]}
                            for key in requested
                            if key in indexed
                        ]
                    }
                },
            )
        raise AssertionError(f"unexpected index request {request.method} {request.url.path}")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw)
    )
    assert (
        await module.rebuild_lexical(
            snapshot, "http://localhost:19201", "shopsteward-restore-test-unit"
        )
        == 2
    )
    assert len(indexed) == 2
    assert {row["generation_id"] for row in indexed.values()} == {"G1", "G2"}
    assert all(row["candidate"]["text"] == "cold storage" for row in indexed.values())
    assert all("parent_text" not in row["candidate"] for row in indexed.values())


async def test_empty_index_preflight_rejects_profile_before_network(monkeypatch):
    from shopsteward_knowledge import bundle as module

    snapshot = ready_snapshot()
    snapshot["knowledge_index_generations"][0]["profile_id"] = "dense-incompatible"
    with pytest.raises(ValueError, match="profile"):
        await module.rebuild_lexical(
            snapshot, "http://localhost:1", "shopsteward-restore-test-unit"
        )


def test_bundle_rejects_generation_manifest_with_changed_chunk_payload(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    snapshot = json.loads((root / "derived/snapshot.json").read_text())
    snapshot.update(ready_snapshot())
    snapshot["knowledge_chunks"][0]["payload"]["parent_text"] = "tampered parser context"
    replace_file(root, manifest, "derived/snapshot.json", snapshot)
    with pytest.raises(ValueError, match="generation manifest"):
        verify_bundle(root)


async def test_export_requires_paused_writers_before_connection(tmp_path, monkeypatch):
    from shopsteward_knowledge import bundle as module

    async def forbidden(_):
        pytest.fail("export connected without writer pause attestation")

    monkeypatch.setattr(module, "connect_database", forbidden)
    with pytest.raises(ValueError, match="pause"):
        await module.export_bundle(
            output=tmp_path / "out",
            authority_url="",
            derived_url="",
            authority_storage=tmp_path,
            derived_storage=tmp_path,
            repo=REPO,
        )


async def test_restore_rejects_nonempty_directory_without_connecting(bundle, tmp_path, monkeypatch):
    from shopsteward_knowledge import bundle as module

    root, _ = bundle
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "keep").write_text("preserve")

    async def forbidden(_):
        pytest.fail("nonempty target attempted connection")

    monkeypatch.setattr(module, "connect_database", forbidden)
    with pytest.raises(ValueError, match="empty"):
        await module.restore_bundle(
            root=root,
            storage_target=target,
            authority_url="",
            derived_url="",
            repo=REPO,
            opensearch_url="",
            index_prefix="",
        )
    assert (target / "keep").read_text() == "preserve"


def test_build_cannot_adopt_unowned_project_containers(tmp_path, monkeypatch):
    local = load_local()
    env = tmp_path / "private.env"
    env.write_text("KNOWLEDGE_SERVICE_KEY=private\nKNOWLEDGE_POSTGRES_PASSWORD=private\n")
    manager = local.Manager(env_file=env, state_dir=tmp_path)
    monkeypatch.setattr(manager, "containers", lambda: [{"id": "foreign", "pid": 99}])
    monkeypatch.setattr(manager, "compose", lambda *a, **kw: pytest.fail("unowned build ran"))
    with pytest.raises(ValueError, match="not owned"):
        manager.build()


class PgSnapshotDouble:
    """Only the unavailable PostgreSQL boundary; files/serialization/guards stay real."""

    def __init__(self, rows, events, name):
        self.rows, self.events, self.name = rows, events, name

    def transaction(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def transaction():
            self.events.append((self.name, "transaction"))
            yield

        return transaction()

    async def close(self):
        self.events.append((self.name, "close"))

    async def execute(self, sql):
        if sql.startswith("LOCK TABLE"):
            self.events.append((self.name, "lock"))
        else:
            assert sql == "SET LOCAL lock_timeout='5s'"

    async def fetchval(self, sql):
        if "pg_namespace" in sql:
            return 0
        if "pg_export_snapshot" in sql:
            assert ("authority", "lock") in self.events and ("derived", "lock") in self.events
            return "00000001-00000001-1"
        raise AssertionError(sql)

    async def fetch(self, sql):
        if "FROM pg_tables" in sql:
            return [{"tablename": name} for name in sorted(self.rows)]
        table = sql.split('public."')[1].split('"')[0]
        return [{"row": json.dumps(row)} for row in self.rows[table]]


@pytest.mark.parametrize("undrained", [False, True])
async def test_export_real_files_and_dynamic_tables_under_both_locks(
    bundle, tmp_path, monkeypatch, undrained
):
    import shutil

    from shopsteward_knowledge import bundle as module

    root, _ = bundle
    repo = tmp_path / "repo"
    for group, package in [("authority", "backend"), ("derived", "knowledge")]:
        shutil.copytree(root / group / "migrations", repo / package / "migrations")
    delivery_migration = Path("versions/knowledge_index_delivery_0011.py")
    source_migration = REPO / "backend/migrations" / delivery_migration
    shutil.copyfile(source_migration, repo / "backend/migrations" / delivery_migration)
    events = []
    connections = {}
    for group, revision in [("authority", "0011_knowledge_delivery"), ("derived", "k1")]:
        rows = json.loads((root / group / "snapshot.json").read_text())
        rows["alembic_version"] = [{"version_num": revision}]
        rows["new_table_added_by_controller"] = [{"id": "future", "value": "must survive"}]
        if group == "authority":
            rows["knowledge_documents"][0].update(metadata_version=3, evidence_revision=1)
        if group == "derived" and undrained:
            rows["knowledge_jobs"] = [{"state": "RETRY_WAIT"}]
        connections[group] = PgSnapshotDouble(rows, events, group)

    async def connect(url):
        return connections["derived" if "derived" in url else "authority"]

    def dump(program, url, args):
        assert program == "pg_dump"
        assert "--snapshot=00000001-00000001-1" in args
        assert ("authority", "lock") in events and ("derived", "lock") in events
        assert not any(event == "close" for _, event in events)
        output = next(a.removeprefix("--file=") for a in args if a.startswith("--file="))
        Path(output).write_bytes(b"unit archive from pg boundary")

    monkeypatch.setattr(module, "connect_database", connect)
    monkeypatch.setattr(module, "pg_command", dump)
    monkeypatch.setattr(module.shutil, "which", lambda _: "pg_dump")
    out = tmp_path / "export"
    kwargs = dict(
        output=out,
        authority_url="postgresql://u:p@localhost/shopsteward_authority_test",
        derived_url="postgresql://u:p@localhost/shopsteward_derived_test",
        authority_storage=root / "authority/originals",
        derived_storage=root / "derived/storage",
        repo=repo,
        writers_paused=True,
    )
    if undrained:
        with pytest.raises(ValueError, match="undrained"):
            await module.export_bundle(**kwargs)
        assert not out.exists()
    else:
        result = await module.export_bundle(**kwargs)
        assert result["files_verified"] == 10
        assert (out / "authority/originals/abc.raw").read_bytes() == b"raw"
        authority = json.loads((out / "authority/snapshot.json").read_text())
        assert authority["knowledge_documents"][0]["metadata_version"] == 3
        assert authority["knowledge_documents"][0]["evidence_revision"] == 1
        assert authority["alembic_version"] == [{"version_num": "0011_knowledge_delivery"}]
        assert (out / "authority/migrations" / delivery_migration).read_bytes() == (
            source_migration.read_bytes()
        )
        snapshot = json.loads((out / "derived/snapshot.json").read_text())
        assert snapshot["new_table_added_by_controller"][0]["value"] == "must survive"


def test_pg_password_is_environment_only_and_errors_are_redacted(monkeypatch):
    from shopsteward_knowledge import bundle as module

    def failing(argv, **kwargs):
        assert "secret" not in repr(argv)
        assert kwargs["env"]["PGPASSWORD"] == "secret"
        assert "PGOPTIONS" not in kwargs["env"]
        return subprocess.CompletedProcess(argv, 1, b"", b"password=secret")

    monkeypatch.setenv("PGOPTIONS", "-c search_path=wrong")
    monkeypatch.setattr(module.shutil, "which", lambda _: "pg_dump")
    monkeypatch.setattr(module.subprocess, "run", failing)
    with pytest.raises(ValueError) as error:
        module.pg_command("pg_dump", "postgresql://u:secret@localhost/shopsteward_test", [])
    assert "secret" not in str(error.value)


def test_compose_configuration_is_loopback_only_and_does_not_include_backend(tmp_path):
    import shutil

    if not shutil.which("docker"):
        pytest.skip("Docker CLI absent; offline Compose config validation not available")
    local = load_local()
    env = tmp_path / "private.env"
    env.write_text("KNOWLEDGE_SERVICE_KEY=unit-private\nKNOWLEDGE_POSTGRES_PASSWORD=unit-private\n")
    manager = local.Manager(env_file=env, state_dir=tmp_path)
    config = json.loads(manager.compose("config", "--format", "json"))
    assert set(config["services"]) == {"postgres", "opensearch", "api", "worker"}
    ports = [p for service in config["services"].values() for p in service.get("ports", [])]
    assert {str(p["published"]) for p in ports} == {"8020", "55434", "19201"}
    assert all(p["host_ip"] == "127.0.0.1" for p in ports)
    assert config["services"]["opensearch"]["image"].endswith(":3.8.0")


async def test_target_database_objects_or_other_clients_block_restore():
    from shopsteward_knowledge.bundle import require_empty_database

    class EmptyTarget:
        def __init__(self, cause):
            self.cause = cause

        async def fetch(self, sql):
            return []

        async def fetchval(self, sql):
            return int(self.cause in sql)

    for cause in ["pg_class", "pg_proc", "pg_stat_activity"]:
        with pytest.raises(ValueError, match="empty test database"):
            await require_empty_database(EmptyTarget(cause))


def test_relation_requires_evidence_in_its_own_generation(bundle):
    from shopsteward_knowledge.bundle import verify_bundle

    root, manifest = bundle
    snapshot = json.loads((root / "derived/snapshot.json").read_text())
    snapshot.update(ready_snapshot())
    snapshot["knowledge_relations"] = [
        {"id": "R1", "generation_id": "G1", "version_id": "V1", "evidence_chunk_ids": ["MISSING"]}
    ]
    replace_file(root, manifest, "derived/snapshot.json", snapshot)
    with pytest.raises(ValueError, match="relation evidence"):
        verify_bundle(root)


async def test_index_check_only_does_not_write_candidate_data(monkeypatch):
    import httpx

    from shopsteward_knowledge.bundle import rebuild_lexical

    def handle(request):
        assert request.method == "GET" and "/_cat/indices/" in request.url.path
        return httpx.Response(200, json=[])

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw)
    )
    assert (
        await rebuild_lexical(
            ready_snapshot(),
            "http://localhost:19201",
            "shopsteward-restore-test-unit",
            check_only=True,
        )
        == 0
    )


async def test_restore_restores_files_and_compares_both_database_snapshots(
    bundle, tmp_path, monkeypatch
):
    import shutil

    import httpx

    from shopsteward_knowledge import bundle as module

    root, _ = bundle
    repo = tmp_path / "repo"
    connections = {}
    events = []

    class Target(PgSnapshotDouble):
        async def fetchval(self, sql):
            if "pg_try_advisory_lock" in sql:
                return True
            if "pg_class" in sql or "pg_proc" in sql or "pg_stat_activity" in sql:
                return len(self.rows)
            return await super().fetchval(sql)

    for group, package in [("authority", "backend"), ("derived", "knowledge")]:
        shutil.copytree(root / group / "migrations", repo / package / "migrations")
        connections[group] = Target({}, events, group)

    async def connect(url):
        return connections["derived" if "derived" in url else "authority"]

    def restore(program, url, args):
        assert program == "pg_restore"
        assert "--single-transaction" in args and "--exit-on-error" in args
        assert "--clean" not in args and "--create" not in args
        group = "derived" if "derived" in url else "authority"
        assert not connections[group].rows
        connections[group].rows = json.loads((root / group / "snapshot.json").read_text())

    def handle(request):
        assert request.method == "GET" and "/_cat/indices/" in request.url.path
        return httpx.Response(200, json=[])

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw)
    )
    monkeypatch.setattr(module, "connect_database", connect)
    monkeypatch.setattr(module, "pg_command", restore)
    monkeypatch.setattr(module.shutil, "which", lambda _: "pg_restore")
    target = tmp_path / "restored"
    result = await module.restore_bundle(
        root=root,
        storage_target=target,
        repo=repo,
        authority_url="postgresql://u:p@localhost/shopsteward_authority_test_restore",
        derived_url="postgresql://u:p@localhost/shopsteward_derived_test_restore",
        opensearch_url="http://localhost:19202",
        index_prefix="shopsteward-restore-test-unit",
    )
    assert result["databases_restored"] == 2 and result["fixed_queries"] == "not_run"
    assert (target / "authority/abc.raw").read_bytes() == b"raw"
    assert (target / "derived/originals/abc").read_bytes() == b"raw"
