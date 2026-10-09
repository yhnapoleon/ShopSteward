import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.core.hashing import digest
from app.learning.lifecycle import binding
from app.learning.models import ApplicationRow, AssetRevisionRow, AssetRow, EvaluationRow
from app.learning.quality import decide
from app.learning.repository import policy


def applicable(spec, facts, tools):
    return (
        set(spec["required_tools"]) <= tools
        and all(facts.get(key) is True for key in spec["preconditions"])
        and all(facts.get(key) is False for key in spec["exclusions"])
    )


async def retrieve(session, *, scope, family, facts, settings, principal, run_id):
    if not settings.learning_enabled or principal.principal_id != scope.principal_id:
        return []
    from app.agent_bridge.tools import catalog
    from app.api.dependencies import authorize_store

    authorize_store(principal, scope.store_id)
    pol = await policy(session, scope, lock=True)
    from app.learning.run_binding import pin, selection, validated

    frozen = await selection(session, scope, run_id)
    if frozen:
        try:
            fixed = await validated(
                session, scope=scope, frozen=frozen, settings=settings, principal=principal
            )
        except AppError:
            return []  # Publication and tool boundaries separately fence the in-flight result.
        return [
            item
            for item in fixed
            if applicable(item["spec"], facts, set(catalog(principal, settings)))
            and item["spec"]["task_family"] == family
        ]
    if pol.mode == "off":
        await pin(session, scope, run_id, pol, [])
        return []
    assets = list(
        await session.scalars(
            select(AssetRow)
            .where(
                AssetRow.scope_id == pol.id,
                AssetRow.task_family == family,
                AssetRow.active_revision.is_not(None),
            )
            .order_by(AssetRow.id)
        )
    )
    selected = []
    for asset in assets:
        rev = await session.get(AssetRevisionRow, (asset.id, asset.active_revision))
        if (
            not rev
            or rev.status != "ACTIVE"
            or not applicable(rev.spec, facts, set(catalog(principal, settings)))
        ):
            continue
        evaluation = (
            await session.get(EvaluationRow, rev.evaluation_id) if rev.evaluation_id else None
        )
        try:
            expected = await binding(
                session,
                scope=scope,
                asset=asset,
                revision=rev,
                settings=settings,
                principal=principal,
            )
            valid = evaluation and decide(evaluation.report, expected)["status"] == "pass"
        except AppError:
            valid = False
        if not valid:
            rev.status = "SUSPENDED"
            asset.active_revision = None
            asset.version += 1
            continue
        item = {
            "asset_id": asset.id,
            "revision": rev.revision,
            "content_hash": rev.content_hash,
            "evaluation_id": rev.evaluation_id,
            "spec": rev.spec,
        }
        # UTF-8 bytes are a conservative token upper bound. Never truncate procedures.
        if len(json.dumps([*selected, item], ensure_ascii=False).encode("utf-8")) > 1800:
            continue
        selected.append(item)
        await session.execute(
            insert(ApplicationRow)
            .values(
                id=digest([run_id, asset.id, rev.revision]),
                scope_id=pol.id,
                asset_id=asset.id,
                revision=rev.revision,
                run_id=run_id,
                stage="selected",
                outcome={"status": "unknown", "attribution": "unresolved"},
            )
            .on_conflict_do_nothing()
        )
        if len(selected) == 3:
            break
    await pin(
        session,
        scope,
        run_id,
        pol,
        [{k: v for k, v in item.items() if k != "spec"} for item in selected],
    )
    return selected
