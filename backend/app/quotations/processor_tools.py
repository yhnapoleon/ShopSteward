"""Tools run within the Work processor's lease/version/owner-fenced transaction."""

import re

from pydantic import Field
from sqlalchemy import select

from app.agent_bridge.models import KnowledgeRevision
from app.agent_bridge.presentation import memory_write_denied
from app.agent_bridge.schemas import DTO
from app.core.errors import AppError
from app.quotations import repository as repo
from app.quotations.schemas import QuoteProcessArgs, QuoteResult, SortBy
from app.work_items.models import WorkMessageRow


class ListFiles(DTO):
    pass


class SaveRule(DTO):
    result_id: str = Field(min_length=1, max_length=128)
    sort_by: SortBy
    expected_rule_version: int = Field(ge=0)
    confirmation: str = Field(min_length=1, max_length=8000)


def long_term_intent(content):
    if memory_write_denied(content) or re.search(
        r"(?:不要|不必|无需|不用|别).{0,12}(?:以后|长期|每次|沿用)|"
        r"仅本次|只限本次|只(?:在|用)?这次|只(?:在|用)?本次|本次即可|"
        r"only (?:this|for)|not (?:in |for )?(?:future|always)",
        content,
        re.I,
    ):
        return False
    return bool(
        re.search(
            r"(?:以后|每次|长期).{0,50}(?:按|排序|沿用|优先)|"
            r"(?:记住|保存|remember|save).{0,80}(?:排序|规则|sort|rule|preference)|"
            r"(?:always|from now|future).{0,50}(?:sort|use|order)",
            content,
            re.I,
        )
    )


DEFINITIONS = {
    "list_quotation_files": (
        ListFiles,
        "读取当前事项已保存的CSV原件元数据与当前用户店铺报价规则版本。",
    ),
    "process_quotation": (
        QuoteProcessArgs,
        "根据当前事项CSV原件确定性重新计算报价。缺包装不猜测；字段纠正仅此原件。"
        "可指定base_result_id沿用该原件旧纠正。规则仅改变排序，工具不改账本。",
    ),
    "save_quotation_rule": (
        SaveRule,
        "仅用户明确要求以后沿用时保存报价排序规则。confirmation必须是最新用户消息中的原话。"
        "expected_rule_version从list_quotation_files读取。先整理得到result_id；不保存逐行字段纠正。",
    ),
}


async def execute(session, settings, principal, work, name, args, invocation_id):
    args = DEFINITIONS[name][0].model_validate(args)
    if name == "list_quotation_files":
        files = await repo.list_files(session, principal, work)
        state = await repo.rule_state(session, principal, work)
        return {
            "ok": True,
            "data": {**files.model_dump(mode="json"), "rule_state": state.model_dump(mode="json")},
            "references": [],
        }
    if name == "process_quotation":
        result = await repo.process(session, principal, work, args)
        return {
            "ok": True,
            "data": result.model_dump(mode="json"),
            "references": repo.references(result),
            "work_result": repo.work_result(result),
        }
    row = await repo.result_for_work(session, principal, work, args.result_id)
    result = QuoteResult.model_validate(row.payload)
    latest = await session.scalar(
        select(WorkMessageRow)
        .where(WorkMessageRow.item_id == work.id, WorkMessageRow.role == "user")
        .order_by(WorkMessageRow.created_at.desc(), WorkMessageRow.id.desc())
        .limit(1)
    )
    if (
        latest is None
        or args.confirmation not in latest.content
        or not long_term_intent(latest.content)
        or not long_term_intent(args.confirmation)
    ):
        raise AppError(
            422,
            "QUOTATION_RULE_CONFIRMATION_REQUIRED",
            "保存长期规则需要当前用户明确要求以后沿用的原话。",
        )
    consumed = await session.scalar(
        select(KnowledgeRevision.version)
        .where(
            KnowledgeRevision.scope_id == repo.rule_scope_id(principal, work),
            KnowledgeRevision.source["source_message_id"].astext == latest.id,
        )
        .limit(1)
    )
    if consumed is not None:
        raise AppError(
            409,
            "QUOTATION_RULE_REQUEST_HANDLED",
            "这条长期规则要求已处理；上传新文件会沿用规则，修改规则需新的明确要求。",
        )
    state = await repo.save_rule(
        session,
        principal,
        work,
        sort_by=args.sort_by,
        expected_version=args.expected_rule_version,
        source={
            "source_message_id": latest.id,
            "confirmation": args.confirmation,
            "result_id": result.id,
            "file_id": result.file_id,
        },
        key=invocation_id,
    )
    refs = [
        {
            "type": "quotation_rule",
            "id": f"{state.rule.scope_id}:{state.rule.version}",
            "label": f"报价排序规则第{state.rule.version}版",
        }
    ]
    return {"ok": True, "data": state.model_dump(mode="json"), "references": refs}
