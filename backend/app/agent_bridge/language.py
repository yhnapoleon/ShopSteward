"""The owner's interface language, so model-written text matches what they read.

The frontend sends X-UI-Language on every request. A user request that changes
something remembers it per principal, in the existing receipt store; model work
that runs later (follow-up insights, memory written in a run, work-item answers)
reads it back and tells the model which language to write.
"""

from sqlalchemy.dialects.postgresql import insert

from app.agent_bridge.models import Receipt
from app.core.hashing import digest

OWNER = "ui-language"
LANGUAGES = {"en": "en", "zh": "zh", "zh-cn": "zh"}
# How text the owner reads is written, in either language; appended after the directive.
OWNER_TEXT = (
    "写给店主的文字：金额取money_display的yuan数值，英文写“CNY 9.50”，中文写“¥9.50”，"
    "同一回答只用一种写法。数量、库存、现金只用工具结果里的数，用界面上的叫法："
    "中文“件、在库、采购在途、可用现金、现金底线、待结算、剩余需求”，英文“units, on hand, "
    "in transit, available cash, cash floor, receivables, remaining demand”。商品和供应商称名称。"
    "不写版本号（方案、状态、模型、快照）、系统内部ID或哈希（方案、预测、店铺、SKU、证据）、"
    "字段名（如available_cash_minor）、原始时间戳或实现细节（如v6、snapshot version、"
    "前端绑定序列）；日期英文写DD/MM，中文写“10月21日”。依据由系统附带的引用链接展示，"
    "正文不抄写引用标识。用店主读得懂的短句，不写日志体。\n"
)


def requested(request):
    return LANGUAGES.get(request.headers.get("x-ui-language", "").strip().lower())


async def remember(session, principal_id, language):
    value = {"language": language}
    statement = insert(Receipt).values(
        owner=OWNER, key=principal_id, args_hash=digest(value), result=value
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Receipt.owner, Receipt.key],
            set_={"args_hash": statement.excluded.args_hash, "result": statement.excluded.result},
            where=Receipt.args_hash != statement.excluded.args_hash,
        )
    )


async def recall(session, principal_id):
    row = await session.get(Receipt, (OWNER, principal_id))
    return row.result["language"] if row is not None else None


def directive(language):
    """One instruction line, placed before the prompt's own language rules."""
    if language == "en":
        return (
            "The user's interface is in English: write everything the user reads "
            "(answers, questions, saved memory and notes) in English, even when these "
            "instructions, tool data or earlier messages are in Chinese. Only an explicit "
            "request from the user for another language overrides this.\n"
        )
    if language == "zh":
        return (
            "用户界面是中文：用户读到的一切（回答、提问、保存的记忆和备注）都用中文书写，"
            "即使说明、工具数据或历史消息是英文；只有用户明确要求其他语言时例外。\n"
        )
    return ""
