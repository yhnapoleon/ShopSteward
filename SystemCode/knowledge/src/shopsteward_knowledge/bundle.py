"""Portable, fail-closed test-database backup and restore primitives.

Verification uses only the standard library. Dumps are trusted operator artifacts,
not a safe format for executing archives received from untrusted third parties.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.parse import unquote, urlsplit

GROUPS = ("authority", "derived")
MANIFEST = "bundle-manifest.json"


def safe_path(root: Path, key: str) -> Path:
    if not isinstance(key, str) or not key:
        raise ValueError("invalid relative path")
    parts = key.split("/")
    for part in parts:
        if (
            not part
            or part in {".", ".."}
            or part.endswith((".", " "))
            or any(ord(c) < 32 or c in '\\:<>"|?*' for c in part)
            or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
        ):
            raise ValueError("invalid relative path")
    path = Path(root).absolute()
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise ValueError("path crosses a link")
    for part in parts:
        path /= part
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise ValueError("path crosses a link")
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("path escapes root")
    return path


def file_info(path: Path) -> dict:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": digest, "size": path.stat().st_size}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("missing or malformed bundle JSON") from exc


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def migration_revisions(root: Path) -> set[str]:
    revisions = set()
    for path in root.glob("versions/*.py"):
        # Parse constants; never import or execute a bundled migration to verify it.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "revision" for t in node.targets
            ):
                revisions.add(ast.literal_eval(node.value))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "revision":
                    revisions.add(ast.literal_eval(node.value))
    return revisions


def _validate_references(root, listed):
    authority = read_json(root / "authority/snapshot.json")
    derived = read_json(root / "derived/snapshot.json")
    required = {"knowledge_documents", "knowledge_versions", "knowledge_publications"}
    if (
        not required <= authority.keys()
        or not {
            "knowledge_originals",
            "knowledge_index_generations",
            "knowledge_chunks",
            "knowledge_relations",
            "knowledge_jobs",
            "knowledge_projections",
        }
        <= derived.keys()
    ):
        raise ValueError("missing required snapshot tables")
    documents = {r["id"]: r for r in authority["knowledge_documents"]}
    versions = {r["id"]: r for r in authority["knowledge_versions"]}
    generations = {r["id"]: r for r in derived["knowledge_index_generations"]}
    stores = {r["id"] for r in authority.get("stores", [])}
    skus = {(r["store_id"], r["sku_id"]) for r in authority.get("products", [])}
    suppliers = {(r["store_id"], r["supplier_id"]) for r in authority.get("supplier_offers", [])}
    for doc in documents.values():
        if (
            doc["store_id"] not in stores
            or any((doc["store_id"], sku) not in skus for sku in doc.get("sku_ids", []))
            or any(
                (doc["store_id"], supplier) not in suppliers
                for supplier in doc.get("supplier_ids", [])
            )
        ):
            raise ValueError("missing entity mapping")
    for version in versions.values():
        if version["document_id"] not in documents:
            raise ValueError("missing document mapping")
    for group, rows, key, hash_key in (
        ("authority/originals", versions.values(), "raw_key", "content_sha256"),
        ("derived/storage", derived["knowledge_originals"], "storage_key", "sha256"),
    ):
        for row in rows:
            name = group + "/" + row[key]
            safe_path(root, name)
            if name not in listed or listed[name] != {
                "sha256": row[hash_key],
                "size": row["size_bytes"],
            }:
                raise ValueError("missing or mismatched original reference")
            if group.startswith("derived"):
                version = versions.get(row["version_id"])
                if not version or version["content_sha256"] != row[hash_key]:
                    raise ValueError("derived original has no matching authority version")
    for publication in authority["knowledge_publications"]:
        generation = generations.get(publication["generation_id"])
        if (
            not generation
            or generation["version_id"] != publication["version_id"]
            or generation["manifest_hash"] != publication["manifest_hash"]
        ):
            raise ValueError("publication generation mapping mismatch")
    for row in derived["knowledge_chunks"] + derived["knowledge_relations"]:
        if row["generation_id"] not in generations or row["version_id"] not in versions:
            raise ValueError("missing derived entity mapping")
    chunk_scope = {
        (r["generation_id"], r["version_id"], r["chunk_id"]) for r in derived["knowledge_chunks"]
    }
    for relation in derived["knowledge_relations"]:
        if not relation.get("evidence_chunk_ids") or any(
            (relation["generation_id"], relation["version_id"], chunk_id) not in chunk_scope
            for chunk_id in relation["evidence_chunk_ids"]
        ):
            raise ValueError("missing relation evidence in generation")
    validate_generations(derived)
    profiles = read_json(root / "profiles.json")
    if not {r["profile_id"] for r in generations.values()} <= set(profiles["retrieval"]):
        raise ValueError("missing profile mapping")


def validate_generations(snapshot):
    for generation in snapshot["knowledge_index_generations"]:
        if generation["state"] != "READY":
            continue
        chunks = [
            r["payload"]
            for r in snapshot["knowledge_chunks"]
            if r["generation_id"] == generation["id"]
        ]
        ids = [c["chunk_id"] for c in chunks]
        serialized = json.dumps(
            {"chunks": sorted(chunks, key=lambda c: c["chunk_id"])},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        if (
            not chunks
            or len(chunks) != generation["chunk_count"]
            or len(set(ids)) != len(ids)
            or hashlib.sha256(serialized.encode()).hexdigest() != generation["manifest_hash"]
        ):
            raise ValueError("generation manifest mismatch")


def verify_bundle(root: Path) -> dict:
    """Verify every byte and portable reference without connecting to a database."""
    root = Path(root)
    manifest = read_json(safe_path(root, MANIFEST))
    try:
        entries = manifest["files"]
        if not isinstance(entries, list) or not entries:
            raise ValueError("missing bundle files")
        listed, aliases = {}, set()
        for entry in entries:
            name = entry["path"]
            path = safe_path(root, name)
            if name == MANIFEST or name.casefold() in aliases:
                raise ValueError("duplicate bundle path")
            aliases.add(name.casefold())
            if any(part == ".env" or part.startswith(".env.") for part in path.parts):
                raise ValueError("environment files cannot enter bundle")
            if not path.is_file():
                raise ValueError("missing bundle file")
            if type(entry["size"]) is not int or entry["size"] < 0:
                raise ValueError("invalid file size")
            actual = file_info(path)
            if actual["size"] != entry["size"]:
                raise ValueError("bundle file size mismatch")
            if actual["sha256"] != entry["sha256"]:
                raise ValueError("bundle checksum mismatch")
            listed[name] = actual
        for path in root.rglob("*"):
            name = path.relative_to(root).as_posix()
            safe_path(root, name)
            if path.is_file() and name != MANIFEST and name not in listed:
                raise ValueError("unlisted bundle file")
        if manifest.get("format_version") != 1 or manifest.get("data_revision") != 1:
            raise ValueError("incompatible bundle format/data revision")
        for group in GROUPS:
            for name in ("database.dump", "snapshot.json"):
                if f"{group}/{name}" not in listed:
                    raise ValueError("missing database artifact")
            revisions = manifest["databases"][group]["revisions"]
            if not revisions or not set(revisions) <= migration_revisions(
                root / group / "migrations"
            ):
                raise ValueError("incompatible database revision")
        if "profiles.json" not in listed:
            raise ValueError("missing profiles")
        _validate_references(root, listed)
    except (KeyError, TypeError, AttributeError, SyntaxError) as exc:
        raise ValueError("malformed bundle manifest or snapshot") from exc
    return {
        "files_verified": len(listed),
        "bytes_verified": sum(item["size"] for item in listed.values()),
    }


def database_spec(url: str) -> dict:
    """Public identity only. Restrict this first rehearsal to explicit local test DBs."""
    try:
        parsed = urlsplit(url)
        name = unquote(parsed.path.removeprefix("/"))
        if (
            parsed.scheme not in {"postgresql", "postgresql+asyncpg"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1", "postgres"}
            or not re.fullmatch(r"shopsteward(?:_[a-z0-9]+)*_test(?:_[a-z0-9]+)*", name)
            or parsed.query
            or parsed.fragment
            or not parsed.username
        ):
            raise ValueError()
        return {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "name": name,
            "user": unquote(parsed.username),
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("requires an explicit local shopsteward test database URL") from exc


async def connect_database(url):
    import asyncpg

    spec = database_spec(url)
    try:
        return await asyncpg.connect(
            host=spec["host"],
            port=spec["port"],
            user=spec["user"],
            password=unquote(urlsplit(url).password or ""),
            database=spec["name"],
            timeout=10,
            command_timeout=60,
        )
    except Exception:
        raise ValueError("cannot connect to designated test database") from None


def pg_command(program, url, arguments):
    spec = database_spec(url)
    executable = shutil.which(program)
    if not executable:
        raise ValueError(f"{program} is required on PATH")
    # Never put passwords in argv or inherit a libpq options/service override.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update(
        PGHOST=spec["host"],
        PGPORT=str(spec["port"]),
        PGUSER=spec["user"],
        PGDATABASE=spec["name"],
        PGPASSWORD=unquote(urlsplit(url).password or ""),
        PGCONNECT_TIMEOUT="10",
    )
    result = subprocess.run(
        [executable, "--no-password", *arguments], env=env, capture_output=True, timeout=600
    )
    if result.returncode:
        raise ValueError(f"{program} failed for designated test database; output suppressed")


def require_empty_directory(path: Path):
    path = Path(path).absolute()
    safe_path(path.parent, path.name)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("target must be a new empty directory")


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


async def table_names(connection):
    extra = await connection.fetchval("""SELECT count(*) FROM pg_namespace
        WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN ('public', 'information_schema')""")
    if extra:
        raise ValueError("test database must use only the public application schema")
    return [
        r["tablename"]
        for r in await connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
    ]


async def snapshot_tables(connection, tables):
    result = {}
    for table in tables:
        rows = await connection.fetch(
            f"SELECT row_to_json(t)::text AS row FROM public.{quote_identifier(table)} t"
        )
        result[table] = [json.loads(row["row"]) for row in rows]
    return result


def copy_tree_files(source: Path, destination: Path):
    if not source.is_dir():
        raise ValueError("missing source storage or migrations directory")
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source).as_posix()
        safe_path(source, relative)
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_file():
            if any(p == ".env" or p.startswith(".env.") for p in path.parts):
                raise ValueError("environment files cannot enter bundle")
            target = safe_path(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with path.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)


async def export_bundle(
    *,
    output,
    authority_url,
    derived_url,
    authority_storage,
    derived_storage,
    repo,
    writers_paused=False,
):
    """Hold SHARE locks across both test DBs until dumps AND immutable blobs are copied.

    Unlike request-path transactions, this explicit maintenance transaction must span
    backup I/O. Operators drain/pause only their dedicated test writers beforehand.
    """
    if not writers_paused:
        raise ValueError("pause dedicated test writers and drain jobs before export")
    output, repo = Path(output), Path(repo)
    require_empty_directory(output)
    specs = [database_spec(url) for url in (authority_url, derived_url)]
    if specs[0]["name"] == specs[1]["name"]:
        raise ValueError("authority and derived databases must be distinct")
    for source in (authority_storage, derived_storage):
        source_root = await asyncio.to_thread(Path(source).resolve)
        if output.resolve().is_relative_to(source_root):
            raise ValueError("output cannot be inside source storage")
    if not shutil.which("pg_dump"):
        raise ValueError("pg_dump is required on PATH")
    async with AsyncExitStack() as stack:
        connections = []
        for url in (authority_url, derived_url):
            connection = await connect_database(url)
            stack.push_async_callback(connection.close)
            connections.append(connection)
        tables_by_group = {}
        for group, connection in zip(GROUPS, connections, strict=True):
            await stack.enter_async_context(connection.transaction())
            await connection.execute("SET LOCAL lock_timeout='5s'")
            tables = await table_names(connection)
            if "alembic_version" not in tables:
                raise ValueError("missing database migration revision")
            await connection.execute(
                "LOCK TABLE "
                + ", ".join("public." + quote_identifier(t) for t in tables)
                + " IN SHARE MODE"
            )
            tables_by_group[group] = tables
        # Both databases are now frozen against table writes. Pending/retry jobs
        # count as undrained; do not silently export a half-published generation.
        snapshots = {
            group: await snapshot_tables(conn, tables_by_group[group])
            for group, conn in zip(GROUPS, connections, strict=True)
        }
        for snapshot in snapshots.values():
            for table in ("knowledge_jobs", "knowledge_delivery_outbox"):
                if any(r["state"] not in {"SUCCEEDED", "FAILED"} for r in snapshot.get(table, [])):
                    raise ValueError("in-flight or undrained jobs; drain before export")
        output.mkdir(parents=True, exist_ok=True)
        manifest = {
            "format_version": 1,
            "data_revision": 1,
            "databases": {},
            "index": {"mode": "rebuild-lexical", "profile_id": "lexical-v1"},
        }
        for group, conn, url, spec in zip(
            GROUPS, connections, (authority_url, derived_url), specs, strict=True
        ):
            directory = output / group
            directory.mkdir()
            snapshot_id = await conn.fetchval("SELECT pg_export_snapshot()")
            await asyncio.to_thread(
                pg_command,
                "pg_dump",
                url,
                [
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--snapshot=" + snapshot_id,
                    "--file=" + str(directory / "database.dump"),
                ],
            )
            data = snapshots[group]
            write_json(directory / "snapshot.json", data)
            revisions = sorted(r["version_num"] for r in data["alembic_version"])
            manifest["databases"][group] = {"name": spec["name"], "revisions": revisions}
            source = repo / ("backend" if group == "authority" else "knowledge")
            copy_tree_files(source / "migrations", directory / "migrations")
        for version in snapshots["authority"]["knowledge_versions"]:
            source = safe_path(Path(authority_storage), version["raw_key"])
            target = safe_path(output / "authority/originals", version["raw_key"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
        copy_tree_files(Path(derived_storage), output / "derived/storage")
        generations = snapshots["derived"]["knowledge_index_generations"]
        write_json(
            output / "profiles.json",
            {
                "retrieval": sorted({"lexical-v1", *(r["profile_id"] for r in generations)}),
                "embedding": [],
                "generation_manifests": {r["id"]: r["manifest"] for r in generations},
            },
        )
        manifest["files"] = [
            {"path": p.relative_to(output).as_posix(), **file_info(p)}
            for p in sorted(output.rglob("*"))
            if p.is_file()
        ]
        write_json(output / MANIFEST, manifest)
        return verify_bundle(output)


async def require_empty_database(connection):
    tables = await table_names(connection)
    objects = await connection.fetchval("""SELECT count(*) FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'""")
    routines = await connection.fetchval("""SELECT count(*) FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'""")
    others = await connection.fetchval("""SELECT count(*) FROM pg_stat_activity
        WHERE datname=current_database() AND pid<>pg_backend_pid()""")
    if tables or objects or routines or others:
        raise ValueError("restore requires an empty test database with no other clients")


async def rebuild_lexical(snapshot, url, prefix, *, check_only=False):
    """Rehydrate compatible lexical indexes from checksummed persisted chunk payloads."""
    import httpx

    from .contracts import Candidate
    from .retrieval.opensearch import OpenSearchIndex

    if any(g["profile_id"] != "lexical-v1" for g in snapshot["knowledge_index_generations"]):
        raise ValueError("incompatible profile; reingest into a new generation")
    validate_generations(snapshot)

    if not re.fullmatch(r"shopsteward-restore-test-[a-z0-9-]{1,25}", prefix):
        raise ValueError("use a fresh shopsteward-restore-test-* index prefix")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "opensearch"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("restore index must be a local test endpoint")
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.get(
            url.rstrip("/") + "/_cat/indices/" + prefix + "-*", params={"format": "json"}
        )
        if response.status_code != 404:
            response.raise_for_status()
            if response.json():
                raise ValueError("restore index prefix already exists")
        if check_only:
            return 0
        index = OpenSearchIndex(client, url, prefix)
        count = 0
        for generation in snapshot["knowledge_index_generations"]:
            if generation["state"] != "READY":
                continue
            if generation["profile_id"] != "lexical-v1":
                raise ValueError("incompatible profile; reingest into a new generation")
            chunks = [
                {k: v for k, v in r["payload"].items() if k in Candidate.model_fields}
                for r in snapshot["knowledge_chunks"]
                if r["generation_id"] == generation["id"]
            ]
            if len(chunks) != generation["chunk_count"]:
                raise ValueError("generation chunk count mismatch")
            await index.upsert(generation["id"], chunks)
            if await index.count(generation["id"]) != len(chunks):
                raise ValueError("rebuilt index count mismatch")
            if not await index.verify_generation(generation["id"], chunks):
                raise ValueError("rebuilt index candidate mismatch")
            count += len(chunks)
        return count


async def restore_bundle(
    *, root, storage_target, authority_url, derived_url, repo, opensearch_url, index_prefix
):
    verified = verify_bundle(Path(root))  # Must precede even target connections.
    root, storage_target, repo = Path(root), Path(storage_target), Path(repo)
    require_empty_directory(storage_target)
    if storage_target.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(
        storage_target.resolve()
    ):
        raise ValueError("restore storage must be separate from bundle")
    manifest = read_json(root / MANIFEST)
    specs = [database_spec(url) for url in (authority_url, derived_url)]
    source_names = {manifest["databases"][g]["name"] for g in GROUPS}
    if specs[0]["name"] == specs[1]["name"] or any(s["name"] in source_names for s in specs):
        raise ValueError("restore targets must be new databases distinct from source")
    for group in GROUPS:
        local = repo / ("backend" if group == "authority" else "knowledge") / "migrations"
        if not set(manifest["databases"][group]["revisions"]) <= migration_revisions(local):
            raise ValueError("target code has incompatible migration revision")
    profiles = read_json(root / "profiles.json")
    if set(profiles["retrieval"]) != {"lexical-v1"} or profiles.get("embedding"):
        raise ValueError("incompatible profile; reingest into a new generation")
    if not shutil.which("pg_restore"):
        raise ValueError("pg_restore is required on PATH")
    async with AsyncExitStack() as stack:
        connections = []
        for url in (authority_url, derived_url):
            conn = await connect_database(url)
            stack.push_async_callback(conn.close)
            # Keep a session lock so two copies of this tool cannot race.
            if not await conn.fetchval("SELECT pg_try_advisory_lock(724193810)"):
                raise ValueError("restore target is already reserved")
            await require_empty_database(conn)
            connections.append(conn)
        snapshot = read_json(root / "derived/snapshot.json")
        # Validate a fresh index namespace before any DB/storage mutation.
        await rebuild_lexical(snapshot, opensearch_url, index_prefix, check_only=True)
        storage_target.mkdir(parents=True, exist_ok=True)
        for group, url, conn in zip(GROUPS, (authority_url, derived_url), connections, strict=True):
            await require_empty_database(conn)
            await asyncio.to_thread(
                pg_command,
                "pg_restore",
                url,
                [
                    "--single-transaction",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--dbname=" + database_spec(url)["name"],
                    str(root / group / "database.dump"),
                ],
            )
            actual = await snapshot_tables(conn, await table_names(conn))
            expected = read_json(root / group / "snapshot.json")

            def canonical(rows):
                return sorted(json.dumps(r, sort_keys=True) for r in rows)

            if actual.keys() != expected.keys() or any(
                canonical(actual[t]) != canonical(expected[t]) for t in expected
            ):
                raise ValueError("restored database snapshot mismatch")
        for source, destination in (
            (root / "authority/originals", storage_target / "authority"),
            (root / "derived/storage", storage_target / "derived"),
        ):
            destination.mkdir(parents=True)
            if source.exists():
                copy_tree_files(source, destination)
                for path in source.rglob("*"):
                    if path.is_file() and file_info(path) != file_info(
                        destination / path.relative_to(source)
                    ):
                        raise ValueError("restored original checksum mismatch")
        chunks = await rebuild_lexical(snapshot, opensearch_url, index_prefix)
        return {
            **verified,
            "databases_restored": 2,
            "chunks_rebuilt": chunks,
            "fixed_queries": "not_run",
        }
