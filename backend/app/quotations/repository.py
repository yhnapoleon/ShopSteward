"""Immutable artifacts inside the caller's store -> work transaction lock."""

import json
from uuid import uuid4

from sqlalchemy import func, or_, select

from app.agent_bridge import knowledge
from app.agent_bridge.models import KnowledgeRevision, KnowledgeScope
from app.agent_bridge.schemas import KnowledgeChange
from app.core.errors import AppError
from app.core.hashing import digest
from app.missions import repository as missions
from app.quotations.calculator import calculate, normalize_corrections, validate_file, validate_rule
from app.quotations.models import QuotationFile, QuotationResult
from app.quotations.schemas import (
    QuoteFile,
    QuoteFiles,
    QuoteProcessArgs,
    QuoteResult,
    QuoteResults,
    QuoteRule,
    QuoteRuleState,
)
from app.work_items import repository as works
from app.work_items.models import WorkItem


async def file_for_work(session, principal, work, file_id):
    file = await session.get(QuotationFile, file_id)
    if file is None:
        raise works.unavailable()
    origin = await works.visible(session, principal, file.work_id)
    if origin.id != work.id:
        raise works.unavailable()
    return file


async def result_for_work(session, principal, work, result_id):
    result = await session.get(QuotationResult, result_id)
    if result is None:
        raise works.unavailable()
    origin = await works.visible(session, principal, result.work_id)
    if origin.id != work.id:
        raise works.unavailable()
    return result


async def list_files(session, principal, work):
    await works.visible(session, principal, work.id)
    rows = await session.scalars(
        select(QuotationFile)
        .where(
            QuotationFile.work_id.in_(
                select(WorkItem.id).where(
                    or_(WorkItem.id == work.id, WorkItem.canonical_id == work.id)
                )
            )
        )
        .order_by(QuotationFile.created_at, QuotationFile.id)
    )
    return QuoteFiles(items=[QuoteFile.model_validate(f) for f in rows])


async def list_results(session, principal, work):
    await works.visible(session, principal, work.id)
    rows = await session.scalars(
        select(QuotationResult)
        .where(
            QuotationResult.work_id.in_(
                select(WorkItem.id).where(
                    or_(WorkItem.id == work.id, WorkItem.canonical_id == work.id)
                )
            )
        )
        .order_by(QuotationResult.created_at, QuotationResult.id)
    )
    return QuoteResults(items=[QuoteResult.model_validate(r.payload) for r in rows])


def rule_scope_id(principal, work):
    return digest([principal.principal_id, work.store_id, "SKILL", "quotation"])


async def rule_state(session, principal, work, version=None):
    scope_id = rule_scope_id(principal, work)
    scope = await session.get(KnowledgeScope, scope_id)
    if version == 0 or (version is None and scope is None):
        return QuoteRuleState(version=0, rule=None)
    selected = scope.version if version is None else version
    revision = await session.get(KnowledgeRevision, (scope_id, selected))
    if not revision:
        raise AppError(409, "QUOTATION_RULE_VERSION_MISSING", "报价规则版本不存在。")
    # Generic memory text is not executable quotation preferences. Only versions
    # produced by this validator can participate in a calculation.
    if revision.source.get("quotation_validated") is True and len(revision.entries) == 1:
        try:
            saved = json.loads(revision.entries[0]["content"])
            if saved.get("schema") == "quotation-sort-v1":
                return QuoteRuleState(
                    version=selected,
                    rule=QuoteRule(
                        scope_id=scope_id,
                        version=selected,
                        sort_by=saved["sort_by"],
                        source=revision.source,
                    ),
                )
        except (ValueError, KeyError, TypeError):
            pass
    return QuoteRuleState(version=selected, rule=None)


async def save_rule(session, principal, work, *, sort_by, expected_version, source, key):
    validate_rule(sort_by)
    scope = await session.get(KnowledgeScope, rule_scope_id(principal, work))
    if scope and len(scope.entries) > 1:
        raise AppError(409, "QUOTATION_RULE_CONFLICT", "报价规则有多个条目，请先整理规则。")
    entry = scope.entries[0] if scope and scope.entries else None
    body = KnowledgeChange(
        kind="SKILL",
        task_type="quotation",
        expected_version=expected_version,
        operation="replace" if entry else "add",
        entry_id=entry["id"] if entry else None,
        content=json.dumps(
            {"schema": "quotation-sort-v1", "sort_by": sort_by}, ensure_ascii=False, sort_keys=True
        ),
        required_tools=["process_quotation"],
    )
    await knowledge.change(
        session,
        principal.principal_id,
        work.store_id,
        body,
        key,
        source={
            **source,
            "work_id": work.id,
            "quotation_validated": True,
            "validation": "A=10;B=12;missing_pack=null;unit_price_unchanged",
        },
        allowed_tools=["process_quotation"],
    )
    await session.flush()
    return await rule_state(session, principal, work)


async def remove_rule(session, principal, work, expected_version, source, key):
    state = await rule_state(session, principal, work)
    if state.version != expected_version:
        raise AppError(409, "VERSION_CONFLICT", "报价规则已更新，请刷新后重试。")
    scope = await session.get(KnowledgeScope, rule_scope_id(principal, work))
    if scope and scope.entries:
        if len(scope.entries) != 1:
            raise AppError(409, "QUOTATION_RULE_CONFLICT", "报价规则有多个条目，请先整理规则。")
        await knowledge.change(
            session,
            principal.principal_id,
            work.store_id,
            KnowledgeChange(
                kind="SKILL",
                task_type="quotation",
                expected_version=expected_version,
                operation="remove",
                entry_id=scope.entries[0]["id"],
            ),
            key,
            source={**source, "work_id": work.id},
            allowed_tools=["process_quotation"],
        )
        await session.flush()
    return await rule_state(session, principal, work)


async def process(
    session, principal, work, body, *, rule=None, rule_loaded=False, correction_content=""
):
    """The caller holds the Work lock/lease fence; no Work or ledger writes here."""
    file = await file_for_work(session, principal, work, body.file_id)
    corrections = []
    if body.base_result_id:
        base = await result_for_work(session, principal, work, body.base_result_id)
        if base.file_id != file.id:
            raise AppError(422, "QUOTATION_BASE_MISMATCH", "基准结果不属于本报价原件。")
        corrections = normalize_corrections(base.payload["corrections"])
    overrides = normalize_corrections(body.corrections)
    replaced = {(c.record, c.field) for c in overrides}
    corrections = [c for c in corrections if (c.record, c.field) not in replaced] + overrides
    if not rule_loaded:
        rule = (await rule_state(session, principal, work, body.rule_version)).rule
    sort_by = body.sort_by or (rule.sort_by if rule else "source")
    rows, issues = calculate(file.content, corrections, sort_by)
    version = (
        await session.scalar(
            select(func.max(QuotationResult.version)).where(QuotationResult.file_id == file.id)
        )
        or 0
    ) + 1
    now = await session.scalar(select(func.clock_timestamp()))
    result = QuoteResult(
        id=str(uuid4()),
        work_id=work.id,
        file_id=file.id,
        filename=file.filename,
        version=version,
        input_sha256=file.sha256,
        sort_by=sort_by,
        rows=rows,
        issues=issues,
        rule=rule,
        corrections=corrections,
        correction_content=correction_content,
        created_at=now,
    )
    session.add(
        QuotationResult(
            id=result.id,
            work_id=work.id,
            file_id=file.id,
            version=version,
            payload=result.model_dump(mode="json"),
            created_at=now,
        )
    )
    await session.flush()
    return result


def references(result):
    refs = [
        {"type": "quotation_file", "id": result.file_id, "label": result.filename},
        {"type": "quotation_result", "id": result.id, "label": f"报价整理第{result.version}版"},
    ]
    if result.rule:
        refs.append(
            {
                "type": "quotation_rule",
                "id": f"{result.rule.scope_id}:{result.rule.version}",
                "label": f"报价排序规则第{result.rule.version}版",
            }
        )
    return refs


def work_result(result):
    return {
        "kind": "quotation",
        "title": f"{result.filename} · 整理结果 v{result.version}"[:200],
        "content": (
            f"已按原件重新计算{len(result.rows)}条报价。"
            + ("部分字段需补充，未确定金额不参与比较。" if result.issues else "计算完成。")
            + "字段纠正仅作用于本原件；未修改经营账本。"
        ),
        "columns": ["商品", "单件价(CNY)", "包装件数", "最低订购件数", "来源"],
        "rows": [
            [
                r.product,
                r.unit_price or "未确定",
                r.pack or "未确定",
                r.moq_pieces or "未确定",
                r.source or f"原件第{r.record}行",
            ]
            for r in result.rows
        ],
        "assumptions": [
            "仅支持CNY；单件价最多保留8位小数。",
            "缺失字段保留待补状态，不猜测包装数量。",
        ],
        "references": references(result),
    }


async def upload(session, principal, item_id, body, key):
    work = await works.visible(session, principal, item_id, lock=True)
    receipt, replay = await missions.command(
        session,
        principal.principal_id,
        "quotation_upload",
        key,
        {"item_id": item_id, **body.model_dump()},
    )
    if replay:
        return QuoteFile.model_validate(
            await file_for_work(session, principal, work, receipt.response["id"])
        )
    works.check_version(work, body.expected_work_version)
    size, sha = validate_file(body.filename, body.content)
    file = QuotationFile(
        id=str(uuid4()),
        work_id=work.id,
        filename=body.filename,
        content=body.content,
        size_bytes=size,
        sha256=sha,
    )
    session.add(file)
    await session.flush()
    await works.append(session, work, "system", "已保存一份报价CSV原件，可用于当前事项的处理。")
    works.release(work)
    work.status, work.question = "RECEIVED", None
    work.mission_request = None
    work.demonstration = False
    work.next_step = "报价原件已保存，可以整理或补充要求。"
    await works.changed(session, work)
    receipt.response = {"id": file.id}
    return QuoteFile.model_validate(file)


async def direct_process(session, principal, item_id, body, key):
    work = await works.visible(session, principal, item_id, lock=True)
    receipt, replay = await missions.command(
        session,
        principal.principal_id,
        "quotation_process",
        key,
        {"item_id": item_id, **body.model_dump()},
    )
    if replay:
        return QuoteResult.model_validate(
            (await result_for_work(session, principal, work, receipt.response["id"])).payload
        )
    works.check_version(work, body.expected_work_version)
    await file_for_work(session, principal, work, body.file_id)
    source_message = await works.append(
        session,
        work,
        "user",
        body.correction_content
        or (
            "整理此报价，按已保存规则重新计算。"
            if not body.corrections
            else "按本次字段纠正重新整理报价。"
        ),
    )
    state = await rule_state(session, principal, work)
    if body.persist_rule:
        source_message = await works.append(session, work, "user", "以后沿用此报价排序规则。")
        state = await save_rule(
            session,
            principal,
            work,
            sort_by=body.sort_by or (state.rule.sort_by if state.rule else "source"),
            expected_version=body.expected_rule_version,
            source={
                "source_message_id": source_message.id,
                "confirmation": "以后沿用此报价排序规则。",
                "correction_content": body.correction_content,
                "file_id": body.file_id,
            },
            key="rule:" + key,
        )
    result = await process(
        session,
        principal,
        work,
        QuoteProcessArgs.model_validate(
            body.model_dump(include=set(QuoteProcessArgs.model_fields))
        ),
        rule=state.rule,
        rule_loaded=True,
        correction_content=body.correction_content,
    )
    works.release(work)
    await works.changed(session, work)
    work.status = "WAITING_INPUT" if result.issues else "RESULT_READY"
    work.mission_request = None
    work.demonstration = False
    work.question = "请补充报价结果中标出的缺失字段。" if result.issues else None
    work.summary = "报价整理结果已保存，历史版本可下载。"
    work.next_step = "补充缺失字段后重新计算。" if result.issues else "可下载结果或上传下一份报价。"
    message = await works.append(
        session, work, "assistant", work.summary, result=work_result(result)
    )
    work.result = message.result
    receipt.response = {"id": result.id}
    return result


async def direct_remove_rule(session, principal, item_id, body, key):
    work = await works.visible(session, principal, item_id, lock=True)
    receipt, replay = await missions.command(
        session,
        principal.principal_id,
        "quotation_remove_rule",
        key,
        {"item_id": item_id, **body.model_dump()},
    )
    if replay:
        return QuoteRuleState.model_validate(receipt.response)
    works.check_version(work, body.expected_work_version)
    message = await works.append(session, work, "user", body.correction_content)
    result = await remove_rule(
        session,
        principal,
        work,
        body.expected_rule_version,
        {"source_message_id": message.id, "confirmation": body.correction_content},
        "rule:" + key,
    )
    works.release(work)
    await works.changed(session, work)
    pending_fields = False
    if work.result:
        for ref in work.result.get("references", []):
            if ref.get("type") == "quotation_result":
                artifact = await result_for_work(session, principal, work, ref["id"])
                pending_fields = bool(artifact.payload.get("issues"))
    work.status = (
        "WAITING_INPUT" if pending_fields else ("RESULT_READY" if work.result else "COMPLETED")
    )
    work.question = "请补充报价结果中标出的缺失字段。" if pending_fields else None
    work.next_step = (
        "补充缺失字段后重新计算。" if pending_fields else "以后整理报价将使用默认排序。"
    )
    await works.append(
        session, work, "assistant", "长期报价排序规则已取消；已生成结果保留原规则版本。"
    )
    receipt.response = result.model_dump(mode="json")
    return result


async def validate_reference(session, principal, work, ref):
    kind = ref.type if hasattr(ref, "type") else ref["type"]
    identifier = ref.id if hasattr(ref, "id") else ref["id"]
    if kind == "quotation_file":
        await file_for_work(session, principal, work, identifier)
    elif kind == "quotation_result":
        await result_for_work(session, principal, work, identifier)
    elif kind == "quotation_rule":
        try:
            scope_id, version = identifier.rsplit(":", 1)
            version = int(version)
        except (ValueError, TypeError):
            raise works.unavailable() from None
        if scope_id != rule_scope_id(principal, work):
            raise works.unavailable()
        revision = await session.get(KnowledgeRevision, (scope_id, version))
        if not revision or not revision.source.get("quotation_validated"):
            raise works.unavailable()
    else:
        raise works.unavailable()
    return True
