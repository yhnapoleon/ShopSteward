import pytest


def test_inline_document_identifiers_use_exact_returned_evidence():
    from app.agent_bridge.evidence_policy import document_answer_guard

    version = "086d332c-690a-4180-90f2-6c8251fd4d08"
    chunk = "c_" + "a" * 64
    refs = [
        dict(
            type="document",
            id="doc",
            version_id=version,
            generation_id="gen",
            metadata_revision=1,
            chunk_id=chunk,
        )
    ]
    text = (
        f"版本：`086d332c-690a-4185-9584-2417b8012097`；引用块：`{chunk[:-1]}`。"
        f"版本：`{version}`；引用块：`{chunk}`。"
        "业务任务：086d332c-690a-4185-9584-2417b8012097"
    )
    original = dict(status="SUCCEEDED", content=text, references=refs)
    result = document_answer_guard(
        original,
        required=True,
        authority={version: dict(document_id="doc", generation_id="gen", metadata_revision=1)},
    )
    assert "版本：`086d332c-690a-4185-9584-2417b8012097`" not in result["content"]
    assert f"引用块：`{chunk[:-1]}`" not in result["content"]
    assert f"版本：`{version}`" in result["content"]
    assert f"引用块：`{chunk}`" in result["content"]
    assert "业务任务：086d332c-690a-4185-9584-2417b8012097" in result["content"]
    assert result["references"] == refs
    assert result["validation_warnings"] == ["DOCUMENT_INLINE_ID_UNVERIFIED"]
    assert original["content"] == text


@pytest.mark.parametrize(
    "query, expected",
    [
        ("当前库存和现金还有多少？", ["get_dashboard"]),
        ("解释当前补货方案", ["get_plan"]),
        ("按供应商退货条款，破损货需要哪些凭证？", ["search_documents"]),
        (
            "结合现有库存、当前补货方案和供应商起订条款判断能否下单",
            ["get_dashboard", "get_plan", "search_documents"],
        ),
        ("请展开上一条引用，核对例外条件", ["read_document_evidence"]),
        ("你好", []),
        ("请记住以后先查供应商条款", ["memory_edit"]),
        ("不用查文档，只看当前库存", ["get_dashboard"]),
        ("库存盘点SOP规定如何处理差异？", ["search_documents"]),
        ("不要查当前库存，只解释库存盘点SOP。", ["search_documents"]),
        ("What does the inventory SOP require?", ["search_documents"]),
        ("现金管理操作规程是什么？", ["search_documents"]),
        ("库存还剩多少？", ["get_dashboard"]),
        ("What is the current inventory?", ["get_dashboard"]),
        ("How much cash is left?", ["get_dashboard"]),
        (
            "Don't check current inventory; explain the inventory SOP.",
            ["search_documents"],
        ),
        (
            "请记住以后优先现金采购。另外请查供应商合同，告诉我能否无条件退货。",
            ["memory_edit", "search_documents"],
        ),
        (
            "请记住以后先查供应商条款，另外请结合当前库存和当前方案查退货条款。",
            ["memory_edit", "get_dashboard", "get_plan", "search_documents"],
        ),
        (
            "请记住以后先查供应商条款。另外请展开上一条引用。",
            ["memory_edit", "read_document_evidence"],
        ),
    ],
)
def test_explicit_request_evidence_requirements(query, expected):
    from app.agent_bridge.evidence_policy import evidence_policy

    assert evidence_policy(query, documents_enabled=True)["required_tools"] == expected


def test_disabled_document_service_never_demands_an_unregistered_tool():
    from app.agent_bridge.evidence_policy import evidence_policy

    result = evidence_policy("供应商合同如何规定退货？", documents_enabled=False)
    assert result["required_tools"] == []
    assert result["document_evidence_unavailable"] is True


def test_mixed_memory_request_retains_missing_document_guard_when_service_disabled():
    from app.agent_bridge.evidence_policy import document_answer_guard, evidence_policy

    policy = evidence_policy(
        "请记住以后优先现金采购。另外请查供应商合同，告诉我能否无条件退货。",
        documents_enabled=False,
    )
    assert policy["required_tools"] == ["memory_edit"]
    assert policy["document_evidence_unavailable"] is True
    result = {"status": "SUCCEEDED", "content": "合同允许无条件退货", "references": []}
    guarded = document_answer_guard(
        result, required=policy["document_evidence_unavailable"], authority={}
    )
    assert guarded["content"] != result["content"]
    assert "DOCUMENT_EVIDENCE_MISSING" in guarded["validation_warnings"]


def test_changed_relation_source_blocks_answer_even_when_primary_document_is_current():
    from app.agent_bridge.evidence_policy import document_answer_guard

    reference = dict(
        type="document", id="d", version_id="v", generation_id="g", metadata_revision=1
    )
    current = {"v": dict(document_id="d", generation_id="g", metadata_revision=1)}
    result = dict(status="SUCCEEDED", content="可以退货", references=[reference])
    assert (
        document_answer_guard(result, required=True, authority=current, relations_changed=False)
        == result
    )
    guarded = document_answer_guard(
        result, required=True, authority=current, relations_changed=True
    )
    assert guarded["content"] != result["content"]
    assert guarded["references"] == []
    assert "DOCUMENT_EVIDENCE_CHANGED" in guarded["validation_warnings"]


def test_explicit_stop_acknowledgement_is_not_replaced_with_missing_evidence():
    from app.agent_bridge.evidence_policy import document_answer_guard

    result = dict(status="SUCCEEDED", content="已停止", references=[], stopped_by_user=True)
    assert document_answer_guard(result, required=True, authority={}) == result


def test_no_document_or_stale_reference_cannot_support_a_clause_answer():
    from app.agent_bridge.evidence_policy import document_answer_guard

    result = dict(content="可以无条件退货", references=[])
    guarded = document_answer_guard(result, required=True, authority={})
    assert guarded["content"] != result["content"]
    assert "DOCUMENT_EVIDENCE_MISSING" in guarded["validation_warnings"]
    reference = dict(
        type="document", id="d", version_id="v", generation_id="g", metadata_revision=1
    )
    current = {"v": dict(document_id="d", generation_id="g", metadata_revision=2)}
    result["references"] = [reference]
    guarded = document_answer_guard(result, required=True, authority=current)
    assert guarded["references"] == []
    assert "DOCUMENT_EVIDENCE_CHANGED" in guarded["validation_warnings"]
    current["v"]["metadata_revision"] = 1
    assert document_answer_guard(result, required=True, authority=current) == result
