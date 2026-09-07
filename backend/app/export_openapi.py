import argparse
import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app


def export(path: Path):
    app = create_app(Settings(_env_file=None, database_url=None, auth_tokens=[]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exported {len(app.openapi()['paths'])} implemented paths to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export actual registered routes without connecting DB"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("../docs/api/backend.runtime.openapi.json")
    )
    export(parser.parse_args().output)
