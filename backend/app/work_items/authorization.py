"""Conservative mutation and date guards, independent of model tool selection."""

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.errors import AppError

BUSINESS_ZONE = ZoneInfo("Asia/Shanghai")
# Mac and phone keyboards type ’ for an apostrophe; the guards read one form.
APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "＇": "'"})
NEGATED = r"不要|不用|不必|别|先不|不修改|不调整|不暂停|不恢复|do not|don't|do n't|never|no need"
HYPOTHETICAL = (
    r"如果|假设|先看|只看|仅比较|只比较|先比较|试算|what if|suppose|"
    r"only compare|just compare|preview"
)
REVISION = r"修改|改成|上限|最多|限制|调整|revise|change|limit|maximum"
# Declining to buy does not decline a revision: a revised proposal never places an order.
NO_PURCHASE = (
    r"(?:不要|不用|不必|别|先不)(?:下单|采购|购买)|"
    r"(?:do not|don't|do n't) (?:order|buy|purchase)"
)
# Ways an owner asks someone to keep watching a product, as opposed to a one-off question.
FOLLOW_UP = (
    r"跟进|委托|盯|看着(?!办)|关注|留意|照看|看管|管着|帮我管|替我管|"
    r"follow|monitor|keep track|watch|keep an eye|look after|take care of|"
    r"\b(?:manage|handle)\b.{0,30}\bfor me\b|in charge of|take over"
)
RUN_OUT = r"(?:run|runs|running|go|goes|going|sell|sells|selling)\s+(?:out|short|empty)"
STOCKED_OUT = r"断货|缺货|卖空|卖光|脱销|断档"
# Keeping a product from running out is itself a standing request.
NOT_RUNNING_OUT = (
    rf"(?:别|不要|不再)(?:让)?.{{0,8}}?(?:{STOCKED_OUT})|不断货|不缺货|"
    rf"(?:保持|保证|确保).{{0,10}}(?:有货|够卖|不断货|不缺货)|(?:防止|避免).{{0,8}}(?:{STOCKED_OUT})|"
    r"\bkeep\b.{0,40}?\b(?:in stock|stocked|on (?:the )?shel(?:f|ves)|topped up)\b|"
    rf"\b(?:avoid|prevent)\w*\s+(?:[\w']+\s+){{0,4}}?{RUN_OUT}|"
    rf"\b(?:make sure|ensure)\b.{{0,60}}?\b(?:never|not|doesn't|does not|don't|do not|won't|isn't|"
    rf"aren't)\b.{{0,20}}?{RUN_OUT}|"
    rf"\b(?:don't|do not|never)\s+let\b.{{0,40}}?{RUN_OUT}|"
    r"\b(?:make sure|ensure)\b.{0,60}?\b(?:in stock|stocked)\b"
)
# A standing Mission is proposed only when the quoted request is about continuing.
ONGOING = (
    FOLLOW_UP + r"|持续|一直|长期|以后|往后|今后|定期|自动|交给你|"
    r"ongoing|from now on|going forward|regularly|automatically|always|long[- ]term|"
    + NOT_RUNNING_OUT
)
# What the owner wants avoided ("so it doesn't run out", "别断货") is the goal, not a refusal.
STOCKOUT_GOAL = (
    rf"(?:do not|don't|do n't|doesn't|does not|never|won't|not)\s+(?:let\s+)?"
    rf"(?:[\w']+\s+){{0,4}}?{RUN_OUT}|"
    rf"(?:不要|不用|别|不能|不会|不再|不)(?:让)?.{{0,8}}?(?:{STOCKED_OUT})"
)
CLAUSE = r"[，,。；;！？!?\n]|\.(?=\s|$)"


def plain(text):
    return text.translate(APOSTROPHES)


def refused(content, verb):
    """A negation or "what if" refuses an action when it comes before it in its clause.

    "Keep an eye on milk, never below CNY 300" asks for the follow-up; "don't keep an eye
    on milk" and "以后不要盯着" refuse it. With no such action in the message, any negation
    left refuses. The goal itself ("so it doesn't run out") and declining to order are not
    refusals: a proposal or a paused follow-up never places an order.
    """
    content = re.sub(STOCKOUT_GOAL, " ", plain(content), flags=re.I)
    content = re.sub(NO_PURCHASE, " ", content, flags=re.I)
    marker = rf"(?:{NEGATED})|(?:{HYPOTHETICAL})"
    clauses = [c for c in re.split(CLAUSE, content) if re.search(verb, c, re.I)]
    if not clauses:
        return bool(re.search(marker, content, re.I))
    for clause in clauses:
        *_, last = re.finditer(verb, clause, re.I)
        if re.search(marker, clause[: last.start()], re.I):
            return True
    return False


def require_explicit_revision(content):
    content = plain(content)
    if re.search(HYPOTHETICAL, content, re.I):
        raise AppError(422, "HYPOTHETICAL_ONLY", "假设或比较只能试算，不修改正式方案。")
    declined = re.search(NEGATED, re.sub(NO_PURCHASE, "", content, flags=re.I), re.I)
    if declined or not re.search(REVISION, content, re.I):
        raise AppError(422, "EXPLICIT_REVISION_REQUIRED", "修改方案需要当前用户明确要求。")


def authorize_action(name, args, messages):
    current = plain(messages[-1].content if messages else "")
    if name == "revise_plan":
        require_explicit_revision(current)
    elif name in {"control_mission", "request_check", "stop_analysis", "propose_mission"}:
        if name == "propose_mission":
            verb = ONGOING
            allowed = re.search(ONGOING, plain(args.source_quote), re.I)
        elif name == "request_check":
            verb = r"重新检查|重新计算|重新算|刷新|重算|再检查|refresh|recheck|recalculate"
            allowed = re.search(verb, current, re.I)
        elif name == "stop_analysis":
            verb = r"停止|取消|结束|stop|cancel"
            allowed = re.search(verb, current, re.I) and re.search(
                r"分析|这次|本次|analysis|this request", current, re.I
            )
        else:
            verb = (
                r"暂停|停止|pause|stop"
                if args.operation == "pause"
                else r"恢复|继续|resume|restart"
            )
            allowed = re.search(verb, current, re.I) and re.search(
                FOLLOW_UP + r"|备货|补货|mission|replenish|restock", current, re.I
            )
        if refused(current, verb):
            raise AppError(422, "EXPLICIT_ACTION_REQUIRED", "本条要求没有授权实际改变跟进或方案。")
        if not allowed:
            raise AppError(
                422,
                "EXPLICIT_ACTION_REQUIRED",
                "请澄清是停止分析、暂停跟进还是其他操作；不能据含糊表述修改业务。",
            )


# 2026-10-22, the interface's own 22/10 or 22/10/2026 (day first), and 10月22日.
DATE = re.compile(
    r"\b(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b|"
    r"(?<![\d/.])(?P<d2>\d{1,2})/(?P<m2>\d{1,2})(?:/(?P<y2>\d{4}))?(?![\d/])|"
    r"(?P<m3>\d{1,2})\s*月\s*(?P<d3>\d{1,2})\s*[日号]?"
)


def local_day(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.astimezone(BUSINESS_ZONE).date()


def last_day(end):
    """The last business day an end instant covers: local midnight closes the day before."""
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    local = end.astimezone(BUSINESS_ZONE)
    return local.date() - timedelta(days=1) if local.time() == time(0) else local.date()


def mentioned_dates(content, today):
    found = []
    for match in DATE.finditer(content):
        year = match["y"] or match["y2"]
        try:
            day = date(
                int(year or today.year),
                int(match["m"] or match["m2"] or match["m3"]),
                int(match["d"] or match["d2"] or match["d3"]),
            )
        except ValueError:
            continue
        if not year and day < today - timedelta(days=180):
            day = day.replace(year=day.year + 1)
        found.append(day)
    return found


def grounded_period(args, messages):
    """Known natural-calendar references must retain the user's actual dates.

    This is a rejection guard, not an intent classifier. Unknown relative references
    are left to clarification rather than being converted to the simulation calendar.
    Days are compared in the business time zone; the end may be given as the last day
    or as the midnight after it.
    """
    for message in reversed(messages):
        content = message.content
        today = local_day(message.created_at)
        dates = mentioned_dates(content, today)
        if len(dates) >= 2:
            start, last = dates[0], dates[1]
        else:
            monday = today - timedelta(days=today.weekday())
            if re.search(r"下周末|next weekend", content, re.I):
                start = monday + timedelta(days=12)
                last = start + timedelta(days=1)
            elif re.search(r"下周|下星期|next week", content, re.I):
                start, last = monday + timedelta(days=7), monday + timedelta(days=13)
            elif re.search(r"本周|这周|this week", content, re.I):
                # What is left of this week, from today.
                start, last = today, monday + timedelta(days=6)
            elif re.search(r"明天|tomorrow", content, re.I):
                start = last = today + timedelta(days=1)
            elif re.search(r"未来[七7]天|接下来[七7]天|next (?:seven|7) days", content, re.I):
                start, last = today, today + timedelta(days=6)
            # "以后" asks for a standing follow-up ("from now on"), not a period.
            elif re.search(
                r"下月|下个月|几天后|过几天|next month|in a few days|a few days later",
                content,
                re.I,
            ):
                raise AppError(
                    422,
                    "PERIOD_CLARIFICATION_REQUIRED",
                    "请先确认明确的起止日期，不能将相对时间套到模拟数据上。",
                )
            else:
                continue
        if args.requested_start is None:
            raise AppError(
                422,
                "USER_PERIOD_REQUIRED",
                "用户说了期间：按原话填写requested_start和requested_end（业务时区）。",
            )
        actual_last = last_day(args.requested_end)
        if local_day(args.requested_start) != start or abs((actual_last - last).days) > 1:
            raise AppError(
                422,
                "USER_PERIOD_MISMATCH",
                "请求日期与用户原话不一致；请核对实际日历，不能改用模拟数据日期。",
            )
        return


def grounded_cash_floor(value, messages, *, required=False):
    from decimal import Decimal

    number = r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
    for message in reversed(messages):
        # The currency may lead, as the interface shows it ("CNY 300"), or follow the amount;
        # a bare number is no floor, nor is one cut short of its digits or 万/千 scale.
        matches = [
            match
            for match in re.findall(
                r"(?:现金(?:底线|至少|最少)?|至少(?:保留|留)|保留|留|"
                r"cash floor|minimum cash|keep(?: at least)?|"
                # "never let cash drop below CNY 300": a bound only where cash is named.
                r"\bcash\b[^.\d]{0,25}?\b(?:below|under|above|over|less than|at least))\D{0,8}?"
                rf"(?:(CNY|RMB|¥|￥)\s*)?{number}(?![.,]?\d|\s*[万千](?!元))"
                r"\s*(万元|千元|块钱|元|块|分|CNY|RMB|yuan)?",
                message.content,
                re.I,
            )
            if match[0] or match[2]
        ]
        if matches:
            _, amount, unit = matches[-1]
            amount = amount.replace(",", "")
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
