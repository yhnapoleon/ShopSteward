"""Baselines read visible context only; no example IDs or expected answers."""

import re
from time import perf_counter

from shopsteward_agent.task_policy.contracts import Decision, DecisionRecord


def _number(text):
    matches = list(re.finditer(r"(-?\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+)\s*件", text))
    if not matches:
        return None
    value = matches[-1].group(1)
    if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return float(value) if "." in value else int(value)
    digits = {c: n for n, c in enumerate("零一二三四五六七八九")}
    digits.update({"两": 2, "〇": 0})
    total, section, digit = 0, 0, 0
    for char in value:
        if char in digits:
            digit = digits[char]
        elif char == "万":
            total += (section + digit) * 10000
            section = digit = 0
        else:
            section += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            digit = 0
    return total + section + digit


class RulePolicy:
    async def decide(self, context):
        start = perf_counter()
        text = next(m["content"] for m in reversed(context.messages) if m["role"] == "user")
        qty = _number(text)
        if re.search(r"报告|季度|下单|批准|经营分析", text):
            name, args = "handoff", {"reason": "unsupported_request"}
        elif "箱" in text:
            name, args = "clarify", {"question": "每箱有多少件？请说明件数换算。"}
        elif re.search(r"刚好|必须.*买|不是最多", text):
            name, args = (
                "clarify",
                {"question": "当前工具只能设置采购数量上限，您是否接受最多采购的上限含义？"},
            )
        elif re.search(r"取消.*上限|无额外上限", text):
            name, args = (
                "revise_plan",
                {
                    "plan_id": context.plan_id,
                    "max_purchase_qty": None,
                    "expected_mission_version": context.mission_version,
                },
            )
        elif re.search(r"算了|不用改|不改.*了|请求.*撤回", text) and not re.search(
            r"试算|模拟|如果|假设", text
        ):
            name, args = "no_action", {"reason": "withdraw_current_request"}
        elif qty is None:
            name, args = (
                "clarify",
                {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"},
            )
        elif type(qty) is not int or not 0 <= qty <= 1000000:
            name, args = "clarify", {"question": "数量上限需要0到1000000的整数，请提供有效件数。"}
        else:
            name = (
                "evaluate_plan"
                if re.search(r"如果|假设|试算|模拟|只看|先别改|不要修改", text)
                else "revise_plan"
            )
            args = {"plan_id": context.plan_id, "max_purchase_qty": qty}
            if name == "revise_plan":
                args["expected_mission_version"] = context.mission_version
        decision = Decision(name=name, arguments=args)
        raw = {
            "content": "",
            "tool_calls": [{"type": "function", "function": {"name": name, "arguments": args}}],
        }
        return DecisionRecord(
            decision=decision,
            raw_response=raw,
            parse_error=None,
            usage={"input_tokens": 0, "output_tokens": 0},
            latency_ms=(perf_counter() - start) * 1000,
        )


def make_policy(policy_id, runtime):
    if policy_id == "B0":
        return RulePolicy()
    from pathlib import Path

    from langchain_openai import ChatOpenAI
    from shopsteward_agent.model import OpenAIModel
    from shopsteward_agent.task_policy.policy import RestrictedPolicy

    config = runtime["policies"][policy_id]
    from app.core.config import Settings

    settings = Settings(_env_file=runtime["app_env_file"])
    model = config.get("model") or settings.agent_model
    base_url = config.get("base_url") or settings.agent_base_url
    api_mode = config.get("api_mode") or settings.agent_api_mode
    key_file = config.get("key_file") or settings.agent_api_key_file
    if not key_file or not Path(key_file).is_file():
        raise ValueError("configured model key file unavailable")
    client = ChatOpenAI(
        base_url=base_url,
        model=model,
        api_key=Path(key_file).read_text(encoding="utf-8").strip(),
        timeout=config.get("timeout_seconds", 60),
        max_retries=0,
        temperature=0,
        max_completion_tokens=config.get("max_output_tokens", 1024),
        use_responses_api=api_mode == "responses",
    )
    return RestrictedPolicy(
        OpenAIModel(base_url=base_url, model=model, client=client, api_mode=api_mode),
        prompt_version=config.get("prompt_version", "v1"),
    )
