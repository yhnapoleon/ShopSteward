"""Focused regressions for the isolated knowledge Docker launcher."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("kind", ["QUERY", "DOCUMENT"])
def test_private_env_decodes_instruction_newlines_without_changing_secrets(tmp_path, kind):
    path = Path(__file__).resolve().parents[2] / "infra/knowledge_local.py"
    spec = importlib.util.spec_from_file_location("knowledge_local_instructions", path)
    local = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local)
    config = tmp_path / "private.env"
    config.write_text(
        'KNOWLEDGE_SERVICE_KEY="literal\\ncredential"\n'
        'KNOWLEDGE_POSTGRES_PASSWORD=test_password\n'
        f'KNOWLEDGE_EMBEDDING_{kind}_INSTRUCTION='
        '"Instruct: Retrieve retail documents.\\nQuery: "\n',
        encoding="utf-8",
    )

    values = local.read_private_env(config)

    assert values[f"KNOWLEDGE_EMBEDDING_{kind}_INSTRUCTION"] == (
        "Instruct: Retrieve retail documents.\nQuery: "
    )
    assert values["KNOWLEDGE_SERVICE_KEY"] == r"literal\ncredential"


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
