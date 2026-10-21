"""What the system writes into a request about quotes follows the owner's language."""

import re
from types import SimpleNamespace

from app.quotations.repository import work_result


def result(issues=()):
    row = SimpleNamespace(
        product="Fresh milk 1L", unit_price=None, pack="10", moq_pieces="20", source=None, record=3
    )
    rule = SimpleNamespace(scope_id="scope", version=2)
    return SimpleNamespace(
        id="r",
        file_id="f",
        filename="quote.csv",
        version=1,
        rows=[row],
        issues=list(issues),
        rule=rule,
    )


def test_an_english_owner_reads_no_chinese_in_the_quote_result():
    value = work_result(result(issues=["missing price"]), "en")
    text = str({k: v for k, v in value.items() if k != "rows"}) + str(value["rows"][0][1:])
    assert not re.search(r"[\u4e00-\u9fff]", text)
    assert value["title"] == "quote.csv · comparison v1"
    assert value["rows"][0][1] == "Not given" and value["rows"][0][4] == "Row 3 of the file"
    assert value["references"][2]["label"] == "Quote sorting rule v2"


def test_a_chinese_owner_keeps_the_chinese_text():
    value = work_result(result())
    assert value["title"] == "quote.csv · 整理结果 v1"
    assert value["content"].startswith("已按原件重新计算1条报价。计算完成。")
