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
