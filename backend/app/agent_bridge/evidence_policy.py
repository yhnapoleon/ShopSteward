"""Narrow, observable evidence obligations for explicit requests, not an intent classifier."""

import re

from app.agent_bridge.forecast_evidence import forecast_requested, replenishment_requested
from app.agent_bridge.presentation import explicit_memory_intent


def current_state_requested(content):
    """Only explicit current/quantity wording creates a mandatory business read."""
    state = r"(?:库存|现金|在途|现货)(?!盘点|管理|SOP|操作规程)"
    english_state = r"\b(?:inventory|stock|cash)\b(?!\s+(?:SOP|policy|procedure|management)\b)"
    for clause in re.split(r"[，,。；;！？!?\n]", content):
        if re.search(
            r"(?:不用|不要|无需|不必|不需要|别).{0,12}(?:库存|现金|在途|现货)|"
            r"\b(?:don't|do not|no need to|never)\b.{0,30}\b(?:inventory|stock|cash)\b",
            clause,
            re.I,
        ):
            continue
        if re.search(
            rf"(?:当前|现在|现有|实时|目前).{{0,8}}{state}|"
            rf"{state}.{{0,8}}(?:多少|还剩|还有|余额|剩余)|"
            rf"\b(?:current|live|available|remaining)\s+{english_state}|"
            rf"\bhow much\s+{english_state}|"
            rf"{english_state}\s+(?:balance|remaining|on hand)\b",
            clause,
            re.I,
        ):
            return True
    return False


def evidence_policy(content, *, documents_enabled, forecasts_enabled=False):
    """Unknown wording remains model-directed; this only strengthens explicit cases."""
    required, reasons = [], []
    unavailable = False
    if explicit_memory_intent(content):
        required, reasons = ["memory_edit"], ["explicit_memory_command"]
        # A preference mentioning documents is not itself a retrieval request.
        # Retain separately stated requests after sentence/additional-request boundaries.
        clauses = re.split(r"[。！？!?；;\n]+|[，,]\s*(?=另外|此外|同时|并且|也请|然后)", content)
        content = "。".join(clause for clause in clauses if not explicit_memory_intent(clause))
    forecast = forecast_requested(content) or (
        forecasts_enabled and replenishment_requested(content)
    )
    if current_state_requested(content) or forecast:
        required.append("get_dashboard")
        reasons.append("current_business_state")
    if forecast:
        required.append("get_forecast")
        reasons.append("forecast_evidence")
    if re.search(r"方案|补货计划|采购计划|current plan|replenishment plan", content, re.I):
        required.append("get_plan")
        reasons.append("current_plan")
    no_docs = re.search(
        r"(?:不用|不要|无需|不必|不需要).{0,3}(?:查|检索|搜索|读取)?(?:文档|资料|合同|条款)",
        content,
    )
    expand = re.search(
        r"(?:展开|核对原文|读原文).{0,12}(?:引用|证据|片段)|(?:引用|片段).{0,12}(?:展开|上下文)",
        content,
    )
    document = re.search(
        r"条款|合同|供应商.{0,10}(?:退货|凭证|起订|规定)|操作规程|SOP|商品说明|文档|资料|policy|contract|document",
        content,
        re.I,
    )
    if (document or expand) and not no_docs:
        unavailable = not documents_enabled
        reasons.append("explicit_evidence_expansion" if expand else "explicit_document_question")
        if documents_enabled:
            required.append("read_document_evidence" if expand else "search_documents")
    return dict(
        version="explicit-evidence-v1",
        required_tools=required,
        reasons=reasons,
        document_evidence_unavailable=unavailable,
        coverage="explicit_request_patterns_only_model_handles_other_wording",
    )


def document_answer_guard(result, *, required, authority, relations_changed: bool = False):
    """Do not publish a document conclusion after evidence disappears or changes."""
    if result.get("stopped_by_user"):
        return result
    references = result.get("references", [])
    documents = [r for r in references if r.get("type") == "document"]
    stale = relations_changed or any(
        not (current := authority.get(r.get("version_id")))
        or current["document_id"] != r.get("id")
        or current["generation_id"] != r.get("generation_id")
        or current["metadata_revision"] != r.get("metadata_revision")
        for r in documents
    )
    if result.get("status") == "WAITING_INPUT":
        return result
    if not stale and (documents or not required):
        return inline_document_identifier_guard(result) if documents else result
    warning = "DOCUMENT_EVIDENCE_CHANGED" if stale else "DOCUMENT_EVIDENCE_MISSING"
    message = (
        "引用资料在生成回答期间已更新或失去访问权限，请重新检索后再判断。"
        if stale
        else "没有取得支持本次条款判断的有效文档证据，暂不能据此确认是否满足要求。"
    )
    return result | dict(
        content=message,
        references=[r for r in references if r.get("type") != "document"],
        validation_warnings=[*result.get("validation_warnings", []), warning],
    )


def inline_document_identifier_guard(result):
    """Check labeled citation IDs, without guessing a correction or changing business IDs."""
    documents = [r for r in result.get("references", []) if r.get("type") == "document"]
    versions = {r.get("version_id") for r in documents}
    chunks = {r.get("chunk_id") for r in documents}
    changed = False

    def validate(match):
        nonlocal changed
        label, identifier = match.group("label", "identifier")
        allowed = chunks if label.lower().startswith("chunk") or "块" in label else versions
        if identifier in allowed:
            return match.group(0)
        changed = True
        return label + "：（标识未核实，请以随附资料引用为准）"

    content = re.sub(
        r"(?P<label>版本|version(?:_id)?|引用块|块|chunk(?:_id)?)\s*[：:]?\s*`?"
        r"(?P<identifier>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|c_[0-9a-f]{16,64})"
        r"(?![0-9a-z_])`?",
        validate,
        result.get("content", ""),
        flags=re.I,
    )
    if not changed:
        return result
    return result | dict(
        content=content,
        validation_warnings=[
            *result.get("validation_warnings", []),
            "DOCUMENT_INLINE_ID_UNVERIFIED",
        ],
    )
