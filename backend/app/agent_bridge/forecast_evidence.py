"""Bind forecast conclusions to the same persisted evidence shown in the product."""

import re


def forecast_requested(content):
    for clause in re.split(r"[，,。；;！？!?\n]", content):
        if re.search(
            r"(?:不用|不要|无需|不必|不需要|别).{0,12}(?:预测|推演)|"
            r"\b(?:don't|do not|no need to)\b.{0,25}\bforecast",
            clause,
            re.I,
        ):
            continue
        if re.search(r"什么是|原理|定义|如何训练|how .{0,12}work|what is", clause, re.I):
            continue
        if re.search(
            r"预测|模型推演|预计.{0,8}(?:卖|销量|销售|需求)|"
            r"(?:下周|未来|明天).{0,12}(?:销量|卖多少|需求)|\bforecast\b",
            clause,
            re.I,
        ):
            return True
    return False


def replenishment_requested(content):
    for clause in re.split(r"[，,。；;！？!?\n]", content):
        if re.search(r"(?:不用|不要|无需|不必|不需要|别).{0,12}补货|什么是|原理|定义", clause):
            continue
        if re.search(r"补货|采购计划|replenishment", clause, re.I):
            return True
    return False


def forecast_answer_guard(result, *, required, current):
    if result.get("stopped_by_user") or result.get("status") == "WAITING_INPUT":
        return result
    references = result.get("references", [])
    forecasts = [r for r in references if r.get("type") == "forecast"]
    evidence = (current or {}).get("forecast") or {}
    stale = bool(forecasts) and (
        (current or {}).get("status") != "READY"
        or any(
            r.get("id") != evidence.get("forecast_id")
            or r.get("version") != evidence.get("model_version")
            or r.get("store_id") != current.get("store_id")
            or r.get("sku_id") != current.get("sku_id")
            or r.get("mode") != current.get("mode")
            for r in forecasts
        )
    )
    if stale or (required and not forecasts):
        return result | dict(
            content=(
                "预测依据已变化或失效，请刷新预测后再判断。"
                if stale
                else "尚未取得有效的 v6 预测依据，请在预测面板绑定序列并提供完整历史后刷新，"
                "暂不能据此判断销量或补货。"
            ),
            references=[r for r in references if r.get("type") != "forecast"],
            validation_warnings=[
                *result.get("validation_warnings", []),
                "FORECAST_EVIDENCE_CHANGED" if stale else "FORECAST_EVIDENCE_MISSING",
            ],
        )
    if forecasts and current.get("mode") == "historical_demo":
        return result | dict(content="模型推演，仅供参考。\n\n" + result.get("content", ""))
    return result
