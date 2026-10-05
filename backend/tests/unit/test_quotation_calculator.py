import csv
import io
from datetime import UTC, datetime

import pytest

from app.core.errors import AppError
from app.quotations.calculator import (
    ENGLISH,
    HEADERS,
    calculate,
    csv_export,
    validate_file,
    validate_rule,
)
from app.quotations.processor_tools import long_term_intent
from app.quotations.schemas import QuoteCorrection, QuoteResult

HEADER = ",".join(HEADERS) + "\n"


def test_decimal_calculation_aliases_sorting_and_moq():
    rows, issues = calculate(
        ",".join(ENGLISH) + "\nB,180,CNY,box,15,3,box,B\nA,120,CNY,box,12,2,box,Z",
        sort_by="unit_price",
    )
    assert [r.product for r in rows] == ["A", "B"]
    assert [r.unit_price for r in rows] == ["10", "12"]
    assert [r.moq_pieces for r in rows] == ["24", "45"]
    assert not issues
    rows, _ = calculate(HEADER + "A,0.3,CNY,箱,3,2,箱,Z\nB,0.4,CNY,件,10,3,件,A", sort_by="source")
    assert [r.product for r in rows] == ["B", "A"]
    assert [r.unit_price for r in rows] == ["0.4", "0.1"]
    assert rows[0].moq_pieces == "3"


def test_missing_pack_and_unsupported_currency_are_not_ranked_or_zero():
    rows, issues = calculate(
        HEADER + "A,120,CNY,箱,,2,箱,A\nB,120,USD,箱,12,2,箱,B\nC,12,CNY,件,,2,件,C",
        sort_by="unit_price",
    )
    assert [r.record for r in rows] == [3, 1, 2]
    assert rows[1].unit_price is None and rows[1].moq_pieces is None
    assert rows[2].unit_price is None and rows[2].currency == "USD"
    assert rows[0].unit_price == "12"
    assert issues


@pytest.mark.parametrize(
    "content",
    [
        "Product,商品,Quote amount,Pricing unit\nA,B,120,box",
        "Product,Quote amount,Pricing unit\nA,120,box,extra",
        HEADER,
        HEADER + "A,120,CNY,箱,12,2,箱,A\n" * 101,
        HEADER + '"unclosed,120,CNY,箱,12,2,箱,A',
    ],
)
def test_reject_ambiguous_or_invalid_csv(content):
    with pytest.raises(AppError):
        validate_file("quote.csv", content)


@pytest.mark.parametrize(
    "filename,content",
    [
        ("../quote.csv", HEADER + "A,120,CNY,箱,12,2,箱,A"),
        ("quote.csv\r\nInjected: true", HEADER + "A,120,CNY,箱,12,2,箱,A"),
        ("quote.csv", "中" * 70000),
        ("quote.csv", HEADER + "A\x00,120,CNY,箱,12,2,箱,A"),
    ],
)
def test_upload_boundaries_are_bytes_and_safe_filename(filename, content):
    with pytest.raises(AppError):
        validate_file(filename, content)


def test_corrections_are_applied_to_new_rows_and_never_mutate_original():
    content = HEADER + "A,120,CNY,箱,,2,箱,A"
    original, _ = calculate(content)
    fixed, issues = calculate(
        content, [QuoteCorrection(record=1, field="Units per pack", value="12")]
    )
    assert original[0].unit_price is None
    assert fixed[0].unit_price == "10" and not issues
    assert calculate(content)[0][0].unit_price is None
    for corrections in [
        [QuoteCorrection(record=2, field="包装件数", value="12")],
        [QuoteCorrection(record=1, field="allow_purchase", value="true")],
        [
            QuoteCorrection(record=1, field="商品", value="B"),
            QuoteCorrection(record=1, field="Product", value="C"),
        ],
    ]:
        with pytest.raises(AppError):
            calculate(content, corrections)


def test_rule_is_closed_and_validates_both_sample_outcomes():
    validate_rule("unit_price")
    validate_rule("source")
    with pytest.raises(AppError):
        validate_rule("skip_cash_floor")


@pytest.mark.parametrize(
    "content",
    [
        "不要以后都这样排序",
        "仅本次，不要记住",
        "不要记住，以后按单价排序",
        "以后这个词出现在报价文件里",
        "don't remember this sorting rule",
        "only this time sort by price",
    ],
)
def test_negative_or_descriptive_text_does_not_authorize_rule(content):
    assert not long_term_intent(content)


@pytest.mark.parametrize(
    "content", ["以后都按单件价排序", "记住这个排序规则", "Please remember this sorting rule"]
)
def test_explicit_long_term_sort_is_recognized(content):
    assert long_term_intent(content)


def test_csv_export_has_fixed_evidence_and_neutralizes_formulas():
    content = HEADER + " =HYPERLINK(1),120,CNY,箱,,2,箱, @SUM(1)"
    rows, issues = calculate(content)
    result = QuoteResult(
        id="result",
        work_id="work",
        file_id="file",
        filename="a.csv",
        version=2,
        input_sha256="f" * 64,
        sort_by="source",
        rows=rows,
        issues=issues,
        rule=None,
        corrections=[],
        correction_content="仅本次",
        created_at=datetime.now(UTC),
    )
    parsed = list(csv.DictReader(io.StringIO(csv_export(result).lstrip("\ufeff"))))
    row = parsed[0]
    assert row["商品"].startswith("'=") and row["来源"].startswith("'@")
    assert row["结果ID"] == "result" and row["原件SHA256"] == "f" * 64
    assert row["结果版本"] == "2" and row["事项ID"] == "work"
    assert row["单件价（元）"] == "" and "包装" in row["待补项"]
    assert row["计算依据"] == "缺少计算依据" and row["纠正说明"] == "仅本次"
