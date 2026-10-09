"""Reusable single-decision policy, independent of the evaluation oracle."""

import json
from time import perf_counter

from .contracts import DecisionRecord, PolicyContext, parse_decision

SYSTEM_PROMPT = """你是补货任务的受限工具决策助手，用中文工作。每次只输出一个工具调用。
只处理当前Mission的本次采购数量上限。假设/只试算用evaluate_plan；明确修改用revise_plan。
上限不是精确采购量；0不是null；明确取消额外上限才用null。数量为0到1000000的整数。
缺少必要数量、指代不唯一、数量非法、精确量与上限不一致或单位换算不明时，clarify询问必要缺项。
不要索取当前状态已知的Plan ID。修改版本必须来自当前状态，不能猜测或使用旧方案。
撤回当前请求用no_action，不取消Mission或回滚既有修改。超出本任务的请求用handoff。
不生成经营分析或结果报告，不执行采购。以用户最后有效要求为准，注意假设、否定和纠正。
"""


SYSTEM_PROMPT_V1 = SYSTEM_PROMPT  # 现有文本原样保留
SYSTEM_PROMPT_V2 = (
    SYSTEM_PROMPT_V1
    + """
数量解释与澄清规则：
保留当前有效数量的正负号。负数是非法目标，不能取绝对值、截断或改成0。
区分用户当前目标与被否定、引用或已撤回的数字；原文出现负数不代表合法的新目标也无效。
最低采购量、精确采购量都不能用上限代替：先说明仅支持上限，询问是否接受上限语义。
这类首次请求优先澄清；若用户在澄清后明确坚持不支持的语义，再转交。
当前单位是件、没有其他换算定义时，unit/units就是件的计数别名，不要仅因中英文切换再次确认。
箱、包、托盘或用户另有定义的单位需要已知换算，不能直接当件。
结合原请求与补充回复判断信息是否齐全；齐全后直接试算或修订，不重复询问已明确的数量、单位和Plan ID。
用户没有提供足够信息时不能猜值；只问影响完成当前请求的必要缺项。
"""
)


def prompt_for_version(version: str) -> str:
    prompts = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2}
    if version not in prompts:
        raise ValueError(f"unknown prompt version: {version}")
    return prompts[version]


class RestrictedPolicy:
    def __init__(self, model, *, prompt_version: str = "v1"):
        self.system_prompt = prompt_for_version(prompt_version)
        self.model = model

    async def decide(self, context: PolicyContext) -> DecisionRecord:
        state = context.model_dump(exclude={"messages", "tool_schemas"})
        messages = [
            {
                "role": "system",
                "content": self.system_prompt
                + "\n当前可见状态："
                + json.dumps(state, ensure_ascii=False),
            },
            *context.messages,
        ]
        start = perf_counter()
        raw = await self.model.complete(messages, context.tool_schemas, tool_choice="required")
        elapsed = (perf_counter() - start) * 1000
        try:
            decision, error = parse_decision(raw), None
        except (ValueError, TypeError) as exc:
            decision, error = None, str(exc)
        return DecisionRecord(
            decision=decision,
            raw_response=raw,
            parse_error=error,
            usage=raw.get("usage"),
            latency_ms=elapsed,
        )
