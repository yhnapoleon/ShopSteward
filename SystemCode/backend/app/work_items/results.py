"""Server-stamped, immutable results and authorized rereads for exports."""

from sqlalchemy import select

from app.missions.models import PlanRow
from app.operations.models import SourceCursor, Store
from app.work_items.schemas import ResultProvenance, WorkResult


async def stamp(session, row, message_id, result, now, work_version, *, evidence=None):
    result = WorkResult.model_validate(result)
    store = await session.get(Store, row.store_id)
    cursor = await session.scalar(select(SourceCursor).where(SourceCursor.store_id == row.store_id))
    versions = {}
    calculation = result.calculation
    quotation = result.kind == "quotation"
    # Quotation validity depends on immutable files/results/rules, not store balances.
    evidence = {} if quotation else (evidence or {})
    for ref in result.references:
        if ref.type == "store" and (calculation or evidence):
            versions[ref.type + ":" + ref.id] = str(
                calculation.input.state.state_version if calculation else evidence["state_version"]
            )
        elif ref.type == "plan":
            plan = await session.get(PlanRow, ref.id)
            versions[ref.type + ":" + ref.id] = str(plan.plan_version)
        elif ref.type in {"quotation_file", "quotation_result"}:
            from app.quotations.models import QuotationFile, QuotationResult

            model = QuotationFile if ref.type == "quotation_file" else QuotationResult
            source = await session.get(model, ref.id)
            if source is not None:
                versions[ref.type + ":" + ref.id] = (
                    "sha256:" + source.sha256
                    if ref.type == "quotation_file"
                    else str(source.version)
                )
        elif ref.type == "quotation_rule":
            versions[ref.type + ":" + ref.id] = ref.id.rsplit(":", 1)[1]
    result.provenance = ResultProvenance(
        result_id=message_id,
        work_id=row.id,
        work_version=work_version,
        generated_at=now,
        # A publish-time observation does not prove which version an external
        # processor used. Only a server-created calculation pins that snapshot.
        data_as_of=calculation.input.state.data_as_of
        if calculation
        else evidence.get("data_as_of"),
        state_version=calculation.input.state.state_version
        if calculation
        else evidence.get("state_version"),
        source_type="quotation"
        if quotation
        else (evidence.get("source_type") or (cursor.source if cursor else None)),
        currency=None if quotation else store.currency,
        reference_versions=versions,
        limitations=["来源版本证明数据归属与时点；文本结论仍须由实际证据支持。"]
        + (
            ["报价依据原件、计算结果和规则版本；库存与现金变化不使其失效。"]
            if quotation
            else []
            if calculation or evidence
            else ["外部处理者未提供可核验的业务快照，未推测其数据时点或状态版本。"]
        ),
    )
    return result.model_dump(mode="json")


def legacy_result(message):
    result = WorkResult.model_validate(message.result)
    if result.provenance is None:
        result.provenance = ResultProvenance(
            result_id=message.id,
            work_id=message.item_id,
            work_version=None,
            generated_at=message.created_at,
            data_as_of=None,
            state_version=None,
            source_type=None,
            currency=None,
            limitations=["历史结果未记录业务截至时点、事项版本和来源版本；这些字段无法追溯。"],
        )
    return result
