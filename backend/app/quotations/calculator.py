"""Bounded CSV is data only. Decimal calculations and a closed rule vocabulary."""

import csv
import hashlib
import io
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from app.core.errors import AppError
from app.quotations.schemas import QuoteCorrection, QuoteRow

HEADERS = ["商品", "报价金额", "币种", "计价单位", "每包装件数", "最低订购量", "MOQ单位", "来源"]
ENGLISH = [
    "Product",
    "Quote amount",
    "Currency",
    "Pricing unit",
    "Units per pack",
    "Minimum order",
    "MOQ unit",
    "Source",
]
ALIASES = {en.lower(): cn for en, cn in zip(ENGLISH, HEADERS, strict=True)}
UNITS = {
    "unit": "件",
    "units": "件",
    "piece": "件",
    "pieces": "件",
    "box": "箱",
    "boxes": "箱",
    "pack": "包",
    "packs": "包",
}


def invalid(message):
    return AppError(422, "QUOTATION_INVALID", message)


def column(value):
    value = value.strip()
    return ALIASES.get(value.lower(), value)


def validate_file(filename, content):
    if (
        not filename.lower().endswith(".csv")
        or "/" in filename
        or "\\" in filename
        or any(ord(c) < 32 for c in filename)
    ):
        raise invalid("请选择文件名有效的CSV文件。")
    try:
        raw = content.encode("utf-8")
    except UnicodeError:
        raise invalid("CSV必须为有效UTF-8文本。") from None
    if b"\x00" in raw or len(raw) > 200000:
        raise invalid("请选择200KB以内、不含空字节的CSV文件。")
    parse(content)
    return len(raw), hashlib.sha256(raw).hexdigest()


def parse(content):
    try:
        table = [
            row
            for row in csv.reader(io.StringIO(content.lstrip("\ufeff")), strict=True)
            if any(cell.strip() for cell in row)
        ]
    except (csv.Error, UnicodeError):
        raise invalid("CSV格式错误或引号没有闭合。") from None
    if not table:
        raise invalid("请选择1至100条报价资料。")
    headers = [column(c) for c in table[0]]
    if not {"商品", "报价金额", "计价单位"} <= set(headers):
        raise invalid("缺少必要列名，请下载格式模板。")
    if len(headers) != len(set(headers)):
        raise invalid("列名重复，不能确定报价字段。")
    if not 1 <= len(table) - 1 <= 100:
        raise invalid("请选择1至100条报价资料。")
    if any(len(r) > len(headers) for r in table[1:]):
        raise invalid("报价行的列数超过表头，请核对CSV格式。")
    if len(headers) > 30 or any(len(c) > 1000 for r in table for c in r):
        raise invalid("报价字段过长或列数过多。")
    return [dict(zip(headers, [c.strip() for c in r], strict=False)) for r in table[1:]]


def number(value, *, integer=False):
    if not value or not re.fullmatch(r"\d{1,13}(?:\.\d{1,6})?", value):
        return None
    try:
        n = Decimal(value)
        if n <= 0 or n > Decimal("1000000000000") or (integer and n != n.to_integral_value()):
            return None
        return n
    except InvalidOperation:
        return None


def dec(n):
    if n is None:
        return None
    return format(n, "f").rstrip("0").rstrip(".") if "." in format(n, "f") else str(n)


def normalize_corrections(corrections):
    result, seen = [], set()
    for correction in corrections:
        correction = QuoteCorrection.model_validate(correction)
        field = column(correction.field)
        if field not in HEADERS:
            raise invalid("只能纠正模板中列出的报价字段。")
        pair = (correction.record, field)
        if pair in seen:
            raise invalid("同一报价字段不能在一次请求中重复纠正。")
        seen.add(pair)
        result.append(correction.model_copy(update={"field": field}))
    return result


def calculate(content, corrections=(), sort_by="source"):
    if sort_by not in {"unit_price", "source"}:
        raise invalid("不支持的排序规则。")
    records = parse(content)
    for c in normalize_corrections(corrections):
        if c.record > len(records):
            raise invalid("纠正引用了不存在的报价行。")
        records[c.record - 1][c.field] = c.value.strip()
    rows, issues = [], []
    for index, record in enumerate(records, 1):

        def problem(text, record_number=index):
            issues.append(f"第{record_number}条报价：{text}")

        unit = UNITS.get(record.get("计价单位", "").lower(), record.get("计价单位", ""))
        moq_unit = UNITS.get(record.get("MOQ单位", "").lower(), record.get("MOQ单位", ""))
        price = number(record.get("报价金额"))
        pack = number(record.get("每包装件数"), integer=True)
        moq = number(record.get("最低订购量"), integer=True)
        unit_price, basis = None, "缺少计算依据"
        if not record.get("商品"):
            problem("商品名称缺失。")
        if price is None:
            problem("报价金额应为有效正数。")
        if record.get("币种") not in {"CNY", "人民币", "元"}:
            problem("币种缺失或不支持，不能直接换算比较。")
        elif price is not None:
            if unit == "件":
                unit_price, basis = price, "原价按件，不再除包装数"
            elif unit in {"箱", "包"} and pack:
                with localcontext() as ctx:
                    ctx.prec = 40
                    unit_price = (price / pack).quantize(
                        Decimal("0.00000001"), rounding=ROUND_HALF_UP
                    )
                basis = f"{dec(price)}元 ÷ {dec(pack)}件（单件价保留最多8位小数）"
            else:
                problem("计价单位或包装数缺失，不能确定单件价。")
        if not pack:
            problem("包装数量缺失或不是正整数。")
        if not moq or moq_unit not in {"件", "箱", "包"}:
            problem("最低订购量或其单位缺失。")
        if not record.get("来源"):
            problem("供应商来源未提供，仍可按文件记录定位。")
        pieces = (
            moq
            if moq_unit == "件"
            else (moq * pack if moq and pack and moq_unit in {"箱", "包"} else None)
        )
        rows.append(
            QuoteRow(
                record=index,
                product=record.get("商品") or "未命名商品",
                price=dec(price),
                pack=dec(pack),
                moq=dec(moq),
                moq_unit=moq_unit,
                unit=unit,
                currency=record.get("币种", ""),
                source=record.get("来源", ""),
                unit_price=dec(unit_price),
                moq_pieces=dec(pieces),
                basis=basis,
            )
        )
    if sort_by == "unit_price":
        rows.sort(key=lambda r: (r.unit_price is None, Decimal(r.unit_price or "0"), r.record))
    else:
        rows.sort(key=lambda r: (r.source, r.record))
    return rows, issues


def validate_rule(sort_by):
    """Validate amounts/MOQs, sorting, missing-pack and per-unit invariants."""
    header = ",".join(HEADERS) + "\n"
    rows, _ = calculate(header + "B,180,CNY,箱,15,3,箱,A\nA,120,CNY,箱,12,2,箱,Z", sort_by=sort_by)
    a = next(row for row in rows if row.product == "A")
    b = next(row for row in rows if row.product == "B")
    expected_order = ["A", "B"] if sort_by == "unit_price" else ["B", "A"]
    missing, issues = calculate(header + "X,120,CNY,箱,,2,箱,X", sort_by=sort_by)
    unit, _ = calculate(header + "U,12,CNY,件,12,2,件,U", sort_by=sort_by)
    if not (
        [row.product for row in rows] == expected_order
        and a.product == "A"
        and a.unit_price == "10"
        and a.moq_pieces == "24"
        and b.product == "B"
        and b.unit_price == "12"
        and b.moq_pieces == "45"
        and missing[0].unit_price is None
        and issues
        and unit[0].unit_price == "12"
    ):
        raise invalid("规则未通过报价样例验证。")


def csv_export(result):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)

    def safe(value):
        value = "" if value is None else str(value)
        return "'" + value if re.match(r"^[\s\x00-\x1f]*[=+\-@]|^[\t\r\n]", value) else value

    writer.writerow(
        [
            "商品",
            "单件价（元）",
            "原报价",
            "原币种",
            "计价单位",
            "包装件数",
            "最低订购量",
            "MOQ单位",
            "MOQ件数",
            "来源",
            "资料序号",
            "计算依据",
            "待补项",
            "原件名",
            "原件SHA256",
            "事项ID",
            "原件ID",
            "结果ID",
            "结果版本",
            "计算版本",
            "排序",
            "规则作用域",
            "规则版本",
            "规则来源",
            "本行纠正",
            "纠正说明",
            "生成时间",
            "限制",
        ]
    )
    for row in result.rows:
        issues = "；".join(
            issue for issue in result.issues if issue.startswith(f"第{row.record}条报价：")
        )
        corrections = [c.model_dump() for c in result.corrections if c.record == row.record]
        writer.writerow(
            [
                safe(v)
                for v in (
                    row.product,
                    row.unit_price,
                    row.price,
                    row.currency,
                    row.unit,
                    row.pack,
                    row.moq,
                    row.moq_unit,
                    row.moq_pieces,
                    row.source,
                    row.record,
                    row.basis,
                    issues,
                    result.filename,
                    result.input_sha256,
                    result.work_id,
                    result.file_id,
                    result.id,
                    result.version,
                    result.calculation_version,
                    result.sort_by,
                    result.rule.scope_id if result.rule else "",
                    result.rule.version if result.rule else "",
                    json.dumps(result.rule.source, ensure_ascii=False) if result.rule else "",
                    json.dumps(corrections, ensure_ascii=False),
                    result.correction_content,
                    result.created_at.isoformat(),
                    "仅CNY；单件价最多8位小数；缺字段不猜测；未改经营账本",
                )
            ]
        )
    return "\ufeff" + stream.getvalue()
