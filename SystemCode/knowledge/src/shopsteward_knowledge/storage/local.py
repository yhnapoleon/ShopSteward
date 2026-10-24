"""Async BlobPort for a service-owned volume; keys never contain host paths.

The volume and its directories must not be writable by untrusted processes.
Containment checks reject existing symlinks/junctions; OS-level isolation is
still required to exclude hostile concurrent directory replacement.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
from pathlib import Path


def validate_key(key: str) -> tuple[str, ...]:
    if not isinstance(key, str) or not key or len(key) > 1024:
        raise ValueError("storage key must be a controlled relative path")
    parts = key.split("/")
    for part in parts:
        if (
            not part
            or part in {".", ".."}
            or part.endswith((".", " "))
            or any(ord(c) < 32 or c in '\\:<>"|?*' for c in part)
            or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", part)
        ):
            raise ValueError("storage key must be a controlled relative path")
    return tuple(parts)


class LocalBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        parts = validate_key(key)
        path = self.root
        for part in parts:
            path = path / part
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("storage key crosses a link")
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("storage key escapes blob root")
        return path

    async def put(self, key: str, data: bytes, sha256: str) -> None:
        await asyncio.to_thread(self._put, key, data, sha256)

    def _put(self, key: str, data: bytes, sha256: str) -> None:
        path = self._path(key)
        if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError("original SHA256 mismatch")
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        # Publish a flushed complete file via atomic no-replace hard link. An
        # exclusive open at the final key would expose partially written bytes.
        descriptor, name = tempfile.mkstemp(prefix=".blob-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if self._path(key).read_bytes() != data:
                    raise FileExistsError(
                        "blob key already contains a different original"
                    ) from None
        finally:
            temporary.unlink(missing_ok=True)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(lambda: self._path(key).read_bytes())
