"""Trusted maintainer CLI; no model-generated verdict uploads are exposed over HTTP."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from app.core.config import Settings
from app.db.session import Database
from app.learning.campaign import complete, prepare
from app.learning.dispatch import current_owner
from app.learning.repository import policy
from app.learning.schemas import LearningScope


async def run(args):
    settings = Settings()
    if not settings.learning_enabled:
        raise ValueError("Enable learning explicitly before preparing an evaluation")
    data = json.loads(args.input.read_text("utf-8"))
    scope = LearningScope.model_validate(data["scope"])
    db = Database(settings.database_url.get_secret_value())
    try:
        async with db.session() as session, session.begin():
            pol = await policy(session, scope, lock=True)
            principal = current_owner(settings, pol)
            if principal is None or pol.mode == "off":
                raise ValueError("Current authorized learning owner required")
            if args.command == "prepare":
                result = await prepare(
                    session,
                    scope=scope,
                    asset_id=data["asset_id"],
                    revision=data["revision"],
                    cases=data["cases"],
                    target=data["target"],
                    settings=settings,
                    principal=principal,
                )
            else:
                artifacts = {}
                root = args.input.resolve().parent
                for item in data["artifacts"]:
                    path = (root / item["path"]).resolve()
                    if not path.is_relative_to(root) or not path.is_file():
                        raise ValueError("Artifacts must be files in the review package")
                    actual = hashlib.sha256(path.read_bytes()).hexdigest()
                    if actual != item["sha256"] or item["id"] in artifacts:
                        raise ValueError("Artifact checksum mismatch or duplicate ID")
                    artifacts[item["id"]] = actual
                result = await complete(
                    session,
                    scope=scope,
                    campaign_id=data["campaign_id"],
                    results=data["results"],
                    reviews=data["reviews"],
                    checks=data["checks"],
                    verified_artifacts=artifacts,
                    settings=settings,
                    principal=principal,
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "complete"])
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args))
