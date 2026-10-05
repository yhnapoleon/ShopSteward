"""Conservative mutation and date guards, independent of model tool selection."""

import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from app.core.errors import AppError

NEGATED = r"不要|不用|不必|别|先不|不修改|不调整|不暂停|不恢复|do not|don't|do n't|never|no need"
HYPOTHETICAL = (
    r"如果|假设|先看|只看|仅比较|只比较|先比较|试算|what if|suppose|"
    r"only compare|just compare|preview"
)
REVISION = r"修改|改成|上限|最多|限制|调整|revise|change|limit|maximum"


def require_explicit_revision(content):
    if re.search(HYPOTHETICAL, content, re.I):
        raise AppError(422, "HYPOTHETICAL_ONLY", "假设或比较只能试算，不修改正式方案。")
    if re.search(NEGATED, content, re.I) or not re.search(REVISION, content, re.I):
        raise AppError(422, "EXPLICIT_REVISION_REQUIRED", "修改方案需要当前用户明确要求。")


def authorize_action(name, args, messages):
    current = messages[-1].content if messages else ""
    if name == "revise_plan":
        require_explicit_revision(current)
    elif name in {"control_mission", "request_check", "stop_analysis", "propose_mission"}:
        if re.search(NEGATED, current, re.I) or re.search(HYPOTHETICAL, current, re.I):
            raise AppError(422, "EXPLICIT_ACTION_REQUIRED", "本条要求没有授权实际改变跟进或方案。")
        if name == "propose_mission":
            source = args.source_quote
            allowed = re.search(r"跟进|委托|持续|follow|monitor|keep track", source, re.I)
        elif name == "request_check":
            allowed = re.search(
                r"重新检查|重新计算|重新算|刷新|重算|再检查|refresh|recheck|recalculate",
                current,
                re.I,
            )
        elif name == "stop_analysis":
            allowed = re.search(r"停止|取消|结束|stop|cancel", current, re.I) and re.search(
                r"分析|这次|本次|analysis|this request", current, re.I
            )
        else:
            action = (
                r"暂停|停止|pause|stop"
                if args.operation == "pause"
                else r"恢复|继续|resume|restart"
            )
            allowed = re.search(action, current, re.I) and re.search(
                r"跟进|备货|委托|mission|follow|replenish", current, re.I
            )
        if not allowed:
            raise AppError(
                422,
                "EXPLICIT_ACTION_REQUIRED",
                "请澄清是停止分析、暂停跟进还是其他操作；不能据含糊表述修改业务。",
            )


def grounded_period(args, messages):
    """Known natural-calendar references must retain the user's actual dates.

    This is a rejection guard, not an intent classifier. Unknown relative references
    are left to clarification rather than being converted to the simulation calendar.
    """
    for message in reversed(messages):
        content = message.content
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", content)
        if len(dates) >= 2:
            expected = (dates[0], dates[1])
        else:
            today = message.created_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
            monday = today - timedelta(days=today.weekday())
            if re.search(r"下周末|next weekend", content, re.I):
                start = monday + timedelta(days=12)
                end = start + timedelta(days=2)
            elif re.search(r"下周|下星期|next week", content, re.I):
                start, end = monday + timedelta(days=7), monday + timedelta(days=14)
            elif re.search(r"本周|这周|this week", content, re.I):
                start, end = monday, monday + timedelta(days=7)
            elif re.search(r"明天|tomorrow", content, re.I):
                start, end = today + timedelta(days=1), today + timedelta(days=2)
            elif re.search(r"未来[七7]天|接下来[七7]天|next (?:seven|7) days", content, re.I):
                start, end = today, today + timedelta(days=7)
            elif re.search(r"下月|下个月|next month|几天后|以后|later", content, re.I):
                raise AppError(
                    422,
                    "PERIOD_CLARIFICATION_REQUIRED",
                    "请先确认明确的起止日期，不能将相对时间套到模拟数据上。",
                )
            else:
                continue
            expected = (start.isoformat(), end.isoformat())
        actual = (args.requested_start.date().isoformat(), args.requested_end.date().isoformat())
        if actual != expected:
            raise AppError(
                422,
                "USER_PERIOD_MISMATCH",
                "请求日期与用户原话不一致；请核对实际日历，不能改用模拟数据日期。",
            )
        return


def grounded_cash_floor(value, messages, *, required=False):
    from decimal import Decimal

    for message in reversed(messages):
        matches = re.findall(
            r"(?:现金(?:底线|至少|最少)?|至少(?:保留|留)|保留|留|"
            r"cash floor|keep(?: at least)?)\D{0,8}"
            r"(\d+(?:\.\d{1,2})?)\s*(万元|千元|块钱|元|块|分|CNY|yuan)",
            message.content,
            re.I,
        )
        if matches:
            amount, unit = matches[-1]
            multiplier = {"万元": 1000000, "千元": 100000, "分": 1}.get(unit, 100)
            expected = int(Decimal(amount) * multiplier)
            if value != expected:
                raise AppError(
                    422,
                    "CASH_FLOOR_SOURCE_MISMATCH",
                    "现金底线与用户原话不符，请核对元与分，不能降低已确认底线。",
                )
            return
    if required:
        raise AppError(
            422, "CASH_FLOOR_CLARIFICATION_REQUIRED", "请先确认明确的现金底线和金额单位。"
        )


def unsupported_success(content, completed_tools):
    """Model narration cannot replace an actual business receipt."""
    patterns = (
        r"(?:已|已经|成功)(?:经|完成|执行|帮你|为你|了|成功){0,2}"
        r"(?:采购|下单|购买|付款|审批|批准采购|撤单|撤回(?:已发)?订单|取消(?:采购)?订单|建立(?:了)?(?:备货)?委托)",
        r"(?:订单|采购|付款|审批|委托)(?:已经|已)(?:取消|撤回|完成|成功|建立|批准)",
        r"\b(?:placed|cancelled|canceled|approved|executed) (?:the |your |a )?(?:order|purchase)\b",
    )
    if any(re.search(pattern, content, re.I) for pattern in patterns):
        return True
    receipts = {
        "control_mission": r"(?:已|已经|成功)(?:将|把)?.{0,10}(?:暂停|恢复)|\b(?:paused|resumed)\b",
        "revise_plan": r"(?:已|已经|成功).{0,8}(?:修订|修改|调整)|新(?:的)?待确认方案已生成",
        "save_quotation_rule": (
            r"(?:已|已经|成功).{0,8}(?:保存|记住|沿用).{0,8}(?:规则|偏好)|"
            r"\b(?:saved|remembered).{0,20}(?:rule|preference)\b"
        ),
    }
    return any(
        name not in completed_tools and re.search(pattern, content, re.I)
        for name, pattern in receipts.items()
    )
