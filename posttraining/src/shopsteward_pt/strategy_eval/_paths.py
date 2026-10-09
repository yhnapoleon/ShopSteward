"""Repo-local research tooling: make the agent runtime and the pure solver importable."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for extra in ("agent/src", "backend"):
    path = str(ROOT / extra)
    if path not in sys.path:
        sys.path.append(path)
