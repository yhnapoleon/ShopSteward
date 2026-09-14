"""Short database reads and immutable evidence writes; no HTTP in this module."""

import math
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

from app.api.dependencies import authorize_store
from app.core.errors import AppError
from app.forecast_v6.models import ForecastV6Binding, ForecastV6Evidence, ForecastV6Input
from app.forecast_v6.schemas import ForecastV6Model, HistoryDay, validate_history
from app.operations.models import ProductRow, StockRow, Store


def aware(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timezone-aware forecast timestamps are required")
    return result


async def scope(session, principal, store_id, sku_id=None, *, lock=False):
    authorize_store(principal, store_id)
    store = await session.get(Store, store_id, with_for_update=lock)
    if store is None or (
        sku_id is not None
        and (
            await session.get(ProductRow, (store_id, sku_id)) is None
            or await session.get(StockRow, (store_id, sku_id)) is None
        )
    ):
        raise AppError(404, "RESOURCE_NOT_FOUND", "Store or SKU is not visible or does not exist")
    return store


def planning_compatible(document, simulation_time):
    """MVP deliberately supports only the first forecast day at UTC midnight."""
    try:
        start = aware(document["horizon_start"])
        cutoff = date.fromisoformat(document["observation_end_date"])
        return (
            simulation_time is not None
            and simulation_time == start
            and start == datetime.combine(cutoff + timedelta(days=1), time(), UTC)
        )
    except (KeyError, ValueError, TypeError):
        return False


async def read_current(session, store_id, sku_id, settings, now=None):
    result = dict(
        status="UNAVAILABLE",
        reason=None,
        store_id=store_id,
        sku_id=sku_id,
        mode=None,
        usable_for_planning=False,
        activate_for_planning=False,
        forecast=None,
        history=[],
        model=None,
    )
    if not settings.forecast_v6_enabled:
        result["reason"] = "FORECAST_V6_DISABLED"
        return result
    now = now or datetime.now(UTC)
    binding = await session.get(ForecastV6Binding, (store_id, sku_id))
    if binding is None:
        result["reason"] = "FORECAST_INPUT_NOT_IMPORTED"
        return result
    result["activate_for_planning"] = binding.activate_for_planning
    source = await session.get(ForecastV6Input, binding.input_id)
    evidence = await session.get(ForecastV6Evidence, binding.evidence_id)
    store = await session.get(Store, store_id)
    if (
        source is None
        or evidence is None
        or store is None
        or (source.store_id, source.sku_id) != (store_id, sku_id)
        or evidence.input_id != source.id
    ):
        result["reason"] = "FORECAST_BINDING_INVALID"
        return result
    document = evidence.document
    result.update(
        mode=source.mode,
        forecast=document,
        history=source.document["history"],
        model=evidence.model,
    )
    if (document.get("store_id"), document.get("sku_id"), document.get("series_id")) != (
        store_id,
        sku_id,
        source.series_id,
    ):
        result.update(reason="FORECAST_SCOPE_MISMATCH", forecast=None)
        return result
    try:
        if not aware(document["generated_at"]) <= now < aware(document["valid_until"]):
            result.update(status="STALE", reason="FORECAST_EXPIRED")
            return result
    except (KeyError, ValueError, TypeError):
        result.update(reason="FORECAST_EVIDENCE_INVALID", forecast=None)
        return result
    if evidence.state_version != store.state_version:
        result.update(status="STALE", reason="STORE_STATE_CHANGED")
        return result
    if source.mode == "observed":
        try:
            start, end = aware(document["horizon_start"]), aware(document["horizon_end"])
            if store.simulation_time is None:
                result.update(status="STALE", reason="STORE_SIMULATION_TIME_UNAVAILABLE")
                return result
            if store.simulation_time < start:
                result.update(status="STALE", reason="FORECAST_HORIZON_FUTURE")
                return result
            if store.simulation_time >= end:
                result.update(status="STALE", reason="FORECAST_HORIZON_ELAPSED")
                return result
        except (KeyError, ValueError, TypeError):
            result.update(reason="FORECAST_EVIDENCE_INVALID", forecast=None)
            return result
    result.update(
        status="READY",
        usable_for_planning=(
            binding.activate_for_planning
            and source.mode == "observed"
            and planning_compatible(document, store.simulation_time)
        ),
    )
    if source.mode == "historical_demo":
        result["reason"] = (
            "HISTORICAL_DEMO_ONLY: original historical dates; not current store demand"
        )
    elif binding.activate_for_planning and not result["usable_for_planning"]:
        result["reason"] = "PLANNING_REQUIRES_FIRST_FORECAST_DAY_UTC_MIDNIGHT"
    return result


async def capture(session, principal, store_id, body):
    store = await scope(session, principal, store_id, body.sku_id)
    binding = await session.get(ForecastV6Binding, (store_id, body.sku_id))
    source = await session.get(ForecastV6Input, binding.input_id) if binding else None
    series_id = body.series_id or (source.series_id if source else None)
    mode = body.mode or (source.mode if source else None)
    if not series_id or not mode:
        raise AppError(422, "FORECAST_INPUT_REQUIRED", "First refresh requires series_id and mode")
    if mode == "historical_demo" and (
        body.activate_for_planning
        or body.history is not None
        or body.observation_end_date is not None
    ):
        raise AppError(
            422,
            "INVALID_DEMO_INPUT",
            "Historical demo uses packaged history and cannot activate planning",
        )
    same_source = source and source.series_id == series_id and source.mode == mode
    history = (
        [row.model_dump(mode="json") for row in body.history]
        if body.history is not None
        else source.document["history"]
        if same_source
        else None
    )
    cutoff = (
        body.observation_end_date.isoformat()
        if body.observation_end_date
        else source.document["observation_end_date"]
        if same_source
        else None
    )
    if mode == "observed":
        if history is None or cutoff is None:
            raise AppError(
                422,
                "FORECAST_INPUT_REQUIRED",
                "Observed mode requires an explicit complete history import",
            )
        try:
            validate_history(
                [HistoryDay.model_validate(row) for row in history], date.fromisoformat(cutoff)
            )
        except ValueError as exc:
            raise AppError(422, "INVALID_FORECAST_HISTORY", str(exc)) from exc
    return dict(
        store_id=store_id,
        sku_id=body.sku_id,
        series_id=series_id,
        mode=mode,
        history=history,
        observation_end_date=cutoff,
        state_version=store.state_version,
        scenario_run_id=store.scenario_run_id,
        binding_revision=binding.revision if binding else 0,
        activate_for_planning=body.activate_for_planning,
    )


def validate_response(document, model, captured, now):
    model = ForecastV6Model.model_validate(model).model_dump(mode="json")
    for key in ("store_id", "sku_id", "series_id", "observation_end_date"):
        if document.get(key) != captured[key]:
            raise ValueError("Model response scope or observation cutoff mismatch")
    if document.get("input_state_version") != captured["state_version"]:
        raise ValueError("Model response state version mismatch")
    if (
        document.get("model_version") != model["model_version"]
        or document.get("feature_profile") != model["feature_profile"]
    ):
        raise ValueError("Model descriptor and prediction versions differ")
    start = datetime.combine(
        date.fromisoformat(captured["observation_end_date"]) + timedelta(days=1), time(), UTC
    )
    if aware(document["horizon_start"]) != start or aware(
        document["horizon_end"]
    ) != start + timedelta(days=7):
        raise ValueError("Model horizon does not follow imported observations")
    rows = document["daily_predictions"]
    if len(rows) != 7 or any(
        row["date"] != (start + timedelta(days=i)).date().isoformat() for i, row in enumerate(rows)
    ):
        raise ValueError("Model response must contain seven ordered forecast dates")
    quantities = [row["quantity"] for row in rows]
    if any(
        isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(q) or q < 0
        for q in quantities
    ):
        raise ValueError("Invalid daily forecast quantity")
    total = sum(quantities)
    if not math.isclose(
        total, document["total_quantity_raw"], rel_tol=1e-6, abs_tol=1e-6
    ) or document["predicted_quantity"] != math.ceil(total):
        raise ValueError("Model total must ceil the weekly sum exactly once")
    if (
        not isinstance(document.get("forecast_id"), str)
        or not 1 <= len(document["forecast_id"]) <= 128
    ):
        raise ValueError("Model forecast ID is missing")
    if (
        document.get("unit") != "piece"
        or document.get("source") != "model"
        or document.get("model_name") != "ShopSteward v6"
    ):
        raise ValueError("Unexpected model source or unit")
    if not aware(document["generated_at"]) <= now < aware(document["valid_until"]):
        raise ValueError("Model evidence is not currently valid")
    if not isinstance(document.get("assumptions"), list) or not isinstance(
        document.get("evaluation"), dict
    ):
        raise ValueError("Model evidence must include assumptions and evaluation")
    return model


async def persist(session, principal, captured, document, model, now=None):
    now = now or datetime.now(UTC)
    store = await scope(session, principal, captured["store_id"], captured["sku_id"], lock=True)
    binding = await session.get(ForecastV6Binding, (store.id, captured["sku_id"]))
    if (
        store.state_version != captured["state_version"]
        or store.scenario_run_id != captured["scenario_run_id"]
        or (binding.revision if binding else 0) != captured["binding_revision"]
    ):
        raise AppError(
            409,
            "FORECAST_INPUT_CHANGED",
            "Store state or forecast binding changed during inference; refresh again",
        )
    try:
        model = validate_response(document, model, captured, now)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise AppError(
            503,
            "FORECAST_INVALID_EVIDENCE",
            "Model response failed scope, freshness or quantity validation",
        ) from exc
    input_id, evidence_id = "v6-input-" + uuid4().hex, "v6-evidence-" + uuid4().hex
    # This revision invalidates existing plans and concurrent inference. The response retains
    # the original input_state_version; evidence binds the post-publication store revision.
    store.state_version += 1
    session.add(
        ForecastV6Input(
            id=input_id,
            store_id=store.id,
            sku_id=captured["sku_id"],
            series_id=captured["series_id"],
            mode=captured["mode"],
            document={
                "history": captured["history"],
                "observation_end_date": captured["observation_end_date"],
            },
            created_at=now,
        )
    )
    await session.flush()
    session.add(
        ForecastV6Evidence(
            id=evidence_id,
            input_id=input_id,
            state_version=store.state_version,
            document=document,
            model=model,
            created_at=now,
        )
    )
    await session.flush()
    if binding is None:
        binding = ForecastV6Binding(store_id=store.id, sku_id=captured["sku_id"], revision=0)
        session.add(binding)
    binding.revision += 1
    binding.input_id, binding.evidence_id = input_id, evidence_id
    binding.activate_for_planning = captured["activate_for_planning"]
    await session.flush()
    return binding
