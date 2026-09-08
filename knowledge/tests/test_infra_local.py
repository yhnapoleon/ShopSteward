"""Focused regressions for the isolated knowledge Docker launcher."""

import importlib.util
import subprocess
import sys
from pathlib import Path


def test_docker_decodes_utf8_output_on_gbk_windows(monkeypatch):
    """Compose's Unicode command ellipsis must survive a GBK host locale."""
    path = Path(__file__).resolve().parents[2] / "infra/knowledge_local.py"
    spec = importlib.util.spec_from_file_location("knowledge_local_encoding", path)
    local = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local)
    run = subprocess.run

    def docker_cli_output(argv, **kwargs):
        # A real child emits Docker's UTF-8 bytes; emulate Windows' fallback
        # encoding only if the launcher has not selected one explicitly.
        kwargs.setdefault("encoding", "gbk")
        return run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'postgres \\xe2\\x80\\xa6')",
            ],
            **kwargs,
        )

    monkeypatch.setattr(local.subprocess, "run", docker_cli_output)
    assert local.docker(["compose", "ps", "--format", "json"]) == "postgres \u2026"
