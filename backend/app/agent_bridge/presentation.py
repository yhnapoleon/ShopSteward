"""Deterministic display values and a narrow numeric grounding check."""

import re
from decimal import Decimal


def money_facts(value, path=""):
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            field = f"{path}.{key}" if path else key
            if key.endswith("_minor") and isinstance(item, int) and not isinstance(item, bool):
                result.append({"field": field, "minor": item, "yuan": f"{Decimal(item) / 100:.2f}"})
            elif key != "money_display":
                result.extend(money_facts(item, field))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(money_facts(item, f"{path}[{index}]"))
    return result


def unsupported_amounts(content, allowed_minor):
    invalid = []
    for match in re.finditer(
        r"(?<![0-9A-Za-z_.,])(-?\d[\d,]*(?:\.\d+)?)\s*(万|千)?(元|分)(?!钟)", content
    ):
        multiplier = {None: 1, "万": 10000, "千": 1000}[match[2]]
        amount = Decimal(match[1].replace(",", "")) * multiplier * (100 if match[3] == "元" else 1)
        if amount not in allowed_minor:
            invalid.append(match[0])
    return invalid


def memory_success_claim(content):
    return bool(
        re.search(
            r"已.{0,8}(?:保存|记住|记录|纠正|删除|更新)|成功(?:保存|记住|删除)",
            content,
        )
    )


def memory_write_denied(content):
    return bool(
        re.search(
            r"(?:不要|不必|无需|不用|别|不想|不需要).{0,6}"
            r"(?:记住|记下|保存|删除|修改|纠正|更正|更新|清除|忘记)|"
            r"(?:don't|do not|never).{0,8}(?:remember|save|delete|remove|update|correct|forget)",
            content,
            re.I,
        )
    )


def explicit_memory_intent(content):
    """Recognize explicit commands, never infer a write from a mention of saved data."""
    content = content.strip()
    if memory_write_denied(content):
        return False
    stable = re.search(
        r"记住|记下|长期|以后|每次|偏好|流程|skill|memory|remember|preference", content, re.I
    )
    if not stable:
        return False
    return bool(
        re.match(
            r"(?:请帮我|请|帮我|麻烦|我希望你|我需要你)?\s*(?:长期|永久)?\s*"
            r"(?:记住|记下|保存|删除|忘记|纠正|更正|清除|更新|修改)|"
            r"(?:请)?把.{0,40}(?:偏好|流程|记忆|skill).{0,40}(?:改成|删除|更新)|"
            r"(?:以后|每次).{0,50}(?:先|按|优先)|"
            r"(?:please\s+)?(?:remember|save|forget|delete|update|correct)\b",
            content,
            re.I,
        )
    )
