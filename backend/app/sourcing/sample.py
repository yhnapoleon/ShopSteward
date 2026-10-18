"""Sample supplier documents for one item, in the layout of the sourcing dataset.

Three invented suppliers, each a different reading problem: a price notice already
in force, a quote priced by the case, and the cheapest supplier that does not
deliver to the store's district. The texts are made up; nothing here is a real quote.
"""

from datetime import timedelta

DISTRICT = "滨江区"
OTHER_ITEMS = ("ITEM_1017", "ITEM_1018", "ITEM_1021", "ITEM_1024", "ITEM_1030")
TERMS = (
    "第三条 订货与确认\n门店应在每日16:00前下单。"
    "订货数量须为装箱规格的整数倍，且不低于报价单载明的起订量。"
    "交期自下单当日起按自然日计算，下单当日不计入。\n"
    "第六条 价格与交期调整\n报价单载明的单价与交期可由本公司以书面通知函调整。"
    "通知函自其载明的生效日期起执行，生效日期之前不影响现行报价；"
    "同一商品有多份已生效通知函的，以生效日期最近的一份为准。"
    "报价单有效期届满后，其价格不再保证，须重新报价。\n"
    "第七条 结算\n货款按月结算，账期30天。"
)


def _yuan(minor):
    return f"{minor / 100:.2f}"


def _lead(days):
    return f"下单后{days}个自然日内送达" if days else "下单当日送达"


def _round(minor):
    return max(10, round(minor / 10) * 10)


def _quote(name, number, issued, until, per, rows, mode):
    lines = [
        f"{name} 商品报价单",
        "",
        f"报价单号：{number}",
        f"报价日期：{issued}",
        f"有效期：{issued} 至 {until}（含首尾两日）",
        "币种：人民币，含税",
        f"计价单位：{per}（下表起订量与单价均按“{per}”计）",
        f"配送方式：{mode}",
        "",
        f"| 货号 | 品类 | 装箱规格 | 起订量（{per}） | 单价（元/{per}） | 交期 |",
        "|---|---|---|---|---|---|",
    ]
    for item, pack, moq, price, lead in rows:
        scale = pack if per == "箱" else 1
        lines.append(
            f"| {item} | 日用百货 | {pack}件/箱 | {moq // scale} | {_yuan(price * scale)} "
            f"| {_lead(lead)} |"
        )
    return "\n".join(
        [
            *lines,
            "",
            "说明：",
            "1. 订货数量须为装箱规格的整数倍。",
            "2. 本报价单的单价与交期可由书面通知函调整，规则见《供货合作条款》第六条。",
        ]
    )


def _price_notice(name, number, issued, effective, item, old, new):
    return "\n".join(
        [
            f"{name} 调价通知函",
            "",
            f"通知编号：{number}",
            f"发文日期：{issued}",
            f"生效日期：{effective}",
            "",
            "致各合作门店：",
            "受上游成本变动影响，自生效日期起，下列商品的供货单价调整如下，报价单其余内容不变。",
            "",
            "| 货号 | 原单价（元/件） | 新单价（元/件） |",
            "|---|---|---|",
            f"| {item} | {_yuan(old)} | {_yuan(new)} |",
            "",
            "生效日期之前下达的订单仍按原单价结算。",
        ]
    )


def _terms(name, zone):
    return "\n".join(
        [
            f"{name} 供货合作条款（门店版）",
            "",
            "第一条 适用范围",
            "本条款适用于本公司与合作门店之间的日常订货、配送与结算，与报价单、通知函共同构成供货约定。",
            "第二条 配送范围",
            f"本公司自有车队的配送范围为：{'、'.join(zone)}。上述范围以外的门店暂不提供配送，也不接受自提订单。",
            TERMS,
        ]
    )


def _history(name, store_id, district, rows):
    head = f"{name} 近期履约记录（门店：{store_id}，{district}）"
    if not rows:
        return head + "\n\n该门店暂无履约记录。"
    return "\n".join(
        [
            head,
            "",
            "订单号,下单日期,约定送达日期,实际送达日期,订货数量,实收数量",
            *(
                f"{po},{ordered},{promised},{actual},{qty},{qty}"
                for po, ordered, promised, actual, qty in rows
            ),
        ]
    )


def sample_suppliers(sku_id, store_id, today, base_price_minor, district=DISTRICT):
    """Three suppliers' documents about `sku_id`, dated around `today`."""

    def day(offset):
        return (today + timedelta(days=offset)).isoformat()

    def others(price, pack, lead):
        return [
            (item, pack, pack * 2, _round(price * (0.6 + 0.2 * index)), lead)
            for index, item in enumerate(OTHER_ITEMS)
        ]

    def deliveries(prefix, late):
        return [
            (
                f"{prefix}-{index + 1:02d}",
                day(-40 + 6 * index),
                day(-38 + 6 * index),
                day(-38 + 6 * index + (1 if index in late else 0)),
                40,
            )
            for index in range(5)
        ]

    def supplier(sid, name, quote, notices, zone, record):
        return {
            "supplier_id": sid,
            "name": name,
            "documents": [
                {"doc_id": f"{sid}-quote", "kind": "quote", "text": quote},
                *(
                    {"doc_id": f"{sid}-notice-{number}", "kind": "notice", "text": text}
                    for number, text in enumerate(notices, 1)
                ),
                {"doc_id": f"{sid}-terms", "kind": "terms", "text": _terms(name, zone)},
                {
                    "doc_id": f"{sid}-history",
                    "kind": "history",
                    "text": _history(name, store_id, district, record),
                },
            ],
        }

    listed, raised = _round(base_price_minor * 0.92), _round(base_price_minor * 1.02)
    by_case, cheapest = _round(base_price_minor * 0.95), _round(base_price_minor * 0.86)
    a_rows = others(listed, 10, 2)
    a_rows.insert(2, (sku_id, 10, 20, listed, 2))
    b_rows = others(by_case, 10, 1)
    b_rows.insert(3, (sku_id, 10, 20, by_case, 1))
    c_rows = others(cheapest, 10, 0)
    c_rows.insert(1, (sku_id, 10, 20, cheapest, 0))
    return [
        supplier(
            "A",
            "安和商贸",
            _quote("安和商贸", "BJ-A-01", day(-20), day(30), "件", a_rows, "次日达"),
            [_price_notice("安和商贸", "TZ-A-01", day(-8), day(-5), sku_id, listed, raised)],
            [district, "西湖区", "上城区"],
            deliveries("PO-A", {3}),
        ),
        supplier(
            "B",
            "百川批发",
            _quote("百川批发", "BJ-B-01", day(-12), day(40), "箱", b_rows, "次日达"),
            [],
            [district, "拱墅区"],
            deliveries("PO-B", set()),
        ),
        supplier(
            "C",
            "诚达供应链",
            _quote("诚达供应链", "BJ-C-01", day(-6), day(25), "件", c_rows, "当日达"),
            [],
            ["萧山区", "余杭区"],
            [],
        ),
    ]
