import asyncio
import hashlib
import shutil

import pytest


def run(awaitable):
    return asyncio.run(awaitable)


def test_blob_survives_root_move_and_identical_replay(tmp_path):
    from shopsteward_knowledge.storage.local import LocalBlobStore

    original = tmp_path / "old"
    store = LocalBlobStore(original)
    data = "原件".encode()
    digest = hashlib.sha256(data).hexdigest()
    run(store.put("versions/v1/original.txt", data, digest))
    run(store.put("versions/v1/original.txt", data, digest))
    shutil.move(str(original), str(tmp_path / "new"))
    assert run(LocalBlobStore(tmp_path / "new").get("versions/v1/original.txt")) == data


def test_blob_rejects_bad_hash_and_different_overwrite(tmp_path):
    from shopsteward_knowledge.storage.local import LocalBlobStore

    store = LocalBlobStore(tmp_path)
    with pytest.raises(ValueError, match="SHA256"):
        run(store.put("bad", b"x", "0" * 64))
    assert not (tmp_path / "bad").exists()
    run(store.put("v1", b"x", hashlib.sha256(b"x").hexdigest()))
    with pytest.raises(FileExistsError):
        run(store.put("v1", b"y", hashlib.sha256(b"y").hexdigest()))
    assert run(store.get("v1")) == b"x"


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../secret",
        "/absolute",
        "C:/secret",
        "a/../b",
        "a\\b",
        "//host/share",
        "a//b",
        "a/./b",
        "a:stream",
        "NUL",
        "a/CON.txt",
        "a. ",
        "a\x00b",
    ],
)
def test_blob_rejects_unsafe_keys_for_reads_and_writes(tmp_path, key):
    from shopsteward_knowledge.storage.local import LocalBlobStore

    store = LocalBlobStore(tmp_path)
    with pytest.raises(ValueError):
        run(store.get(key))
    with pytest.raises(ValueError):
        run(store.put(key, b"x", hashlib.sha256(b"x").hexdigest()))


def test_blob_rejects_symlink_escape(tmp_path):
    from shopsteward_knowledge.storage.local import LocalBlobStore

    root = tmp_path / "blobs"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        # Windows directory junctions require no symlink privilege.
        import subprocess

        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(root / "link"), str(outside)],
            check=True,
            capture_output=True,
        )
    store = LocalBlobStore(root)
    with pytest.raises(ValueError):
        run(store.put("link/file", b"x", hashlib.sha256(b"x").hexdigest()))
    with pytest.raises(ValueError):
        run(store.get("link/file"))
    assert not (outside / "file").exists()


def test_concurrent_different_puts_publish_one_whole_original(tmp_path):
    from shopsteward_knowledge.storage.local import LocalBlobStore

    store = LocalBlobStore(tmp_path)

    async def race():
        payloads = [b"a" * 100000, b"b" * 100000]
        outcomes = await asyncio.gather(
            *(store.put("same", d, hashlib.sha256(d).hexdigest()) for d in payloads),
            return_exceptions=True,
        )
        assert sum(isinstance(o, FileExistsError) for o in outcomes) == 1
        assert await store.get("same") in payloads

    run(race())
