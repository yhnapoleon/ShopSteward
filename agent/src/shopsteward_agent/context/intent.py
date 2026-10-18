"""Shared source-backed mutation prohibitions, independent of the model stack.

This only narrows permissions. Existing tool-specific positive authorization,
version checks and the purchasing approval boundary still apply.
"""

import re

MUTATIONS = {"revise_plan", "memory_edit", "request_check", "analyze_recovery_case"}
PLAN_WRITES = {"revise_plan", "request_check"}


def classify_intent(messages):
    denied = {}
    effect_source = {}
    saw_write = False
    for message in messages:
        # A positive clause can replace an earlier message's restriction, but
        # cannot undo an explicit prohibition in its own source message.
        message_denied = set()
        for clause_match in re.finditer(r"[^，,。；;！？!?\n]+", message["content"]):
            clause = clause_match.group()
            broad = re.search(
                r"只(?:读|看|查询|试算|模拟|分析)|仅(?:试算|分析)|read.only|(?:only|just)\s+(?:simulate|evaluate|read|analy[sz]e)",
                clause,
                re.I,
            )
            negative = re.search(
                r"(?:不要|不必|无需|不用|别|不想|不需要|不).{0,6}?"
                r"(?:记住|记下|保存|删除|修改|改动|修订|纠正|更正|更新|清除|忘记)|"
                r"(?:do not|don't|never).{0,8}?"
                r"(?:save|change|write|revise|remember|delete|remove|update|correct|forget)",
                clause,
                re.I,
            )
            affected = set()
            match = broad or negative
            if broad:
                affected = MUTATIONS
            elif negative:
                tail = clause[negative.end() :]
                if re.match(
                    r"\s*(?:(?:到|当前|这个|我的|该|本次|the|this|my|current)\s*)*(?:偏好|记忆|习惯|preference|memory)",
                    tail,
                    re.I,
                ):
                    affected = {"memory_edit"}
                elif re.match(
                    r"\s*(?:(?:当前|这个|我的|该|本次|the|this|my|current)\s*)*(?:方案|计划|plan)",
                    tail,
                    re.I,
                ):
                    affected = PLAN_WRITES
                else:
                    affected = MUTATIONS
            if match:
                source = {
                    "effect_source_message_id": message["message_id"],
                    "effect_exact_quote": match.group(),
                    "effect_source_span": (
                        clause_match.start() + match.start(),
                        clause_match.start() + match.end(),
                    ),
                }
                effect_source = source
                message_denied.update(affected)
                for tool in affected:
                    denied[tool] = source
                continue
            # A prohibition against actually ordering purchases is not a ban on
            # preparing a pending Plan; no purchasing tool is exposed here.
            if re.search(
                r"(?:不要|别|不必)(?:下单|采购|执行)|(?:do not|don't)\s+(?:order|purchase|execute)",
                clause,
                re.I,
            ):
                continue
            allowed = set()
            positive = re.search(
                r"保存|记住|记下|删除|忘记|纠正|更正|清除|更新|修改|改成|改为|调整|修订|重新计算|刷新|生成|\b(?:save|remember|delete|forget|update|correct|revise|change|refresh|maximum|limit)\b",
                clause,
                re.I,
            )
            if positive:
                if re.search(r"偏好|记忆|习惯|preference|memory|remember", clause, re.I):
                    allowed = {"memory_edit"}
                elif re.search(r"刷新|重新计算|重新检查|refresh", clause, re.I):
                    allowed = {"request_check"}
                else:
                    allowed = PLAN_WRITES
                if allowed - message_denied:
                    saw_write = True
                    effect_source = {
                        "effect_source_message_id": message["message_id"],
                        "effect_exact_quote": positive.group(),
                        "effect_source_span": (
                            clause_match.start() + positive.start(),
                            clause_match.start() + positive.end(),
                        ),
                    }
            if re.search(r"重新分析|重算|analy[sz]e", clause, re.I):
                allowed.add("analyze_recovery_case")
            for tool in allowed - message_denied:
                denied.pop(tool, None)
    return {
        "requested_effect": "read_only"
        if set(denied) == MUTATIONS
        else "write"
        if saw_write
        else "unspecified",
        "denied_tools": sorted(denied),
        "denied_tool_sources": denied,
        **effect_source,
    }
