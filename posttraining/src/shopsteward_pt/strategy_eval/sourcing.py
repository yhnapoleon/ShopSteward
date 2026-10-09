"""Multi-supplier sourcing worlds: one truth, one view per role.

A world is a real M5 demand week with a stock gap and a few invented suppliers.
Each supplier's documents are rendered from typed facts, so the card a reviewer
should return for that supplier is known exactly, and the deterministic solver's
answer for the offers the documents really support is the root-level oracle.
A reviewer sees one supplier's documents; the root sees cards, never documents.
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from .cards import decide, to_offer
from .cases import PARTITIONS, START, _hash, build
from .cases import write_dataset as _write
from .claims import required_conditions
from .sources import _number

DATASET = "ops-sourcing-v1"
AS_OF = START.date()
# Declared assumptions that turn an M5 dollar shelf price into a CNY supply price.
FX, COST_SHARE = 7.1, 0.7
DISTRICTS = ("滨江区", "西湖区", "拱墅区", "上城区", "萧山区", "余杭区")
NAMES = {"A": "安和商贸", "B": "百川批发", "C": "诚达供应链", "D": "德润贸易", "E": "恩泽商行"}
MODES = {
    "Same Day": "当日达",
    "First Class": "次日达",
    "Second Class": "两日达",
    "Standard Class": "普通配送",
}
CATEGORY = {"FOODS": "食品", "HOUSEHOLD": "家居日用", "HOBBIES": "休闲用品"}
# family -> the misreading of one supplier's documents that would change the decision
FAMILIES = {
    "baseline": None,
    "case_price": "unit",
    "notice_price": "notices",
    "future_notice": "future",
    "lead_change": "notices",
    "superseded": "revoked",
    "expired": "expiry",
    "withdrawn": "notices",
    "not_covered": "near_miss",
    "zone": "zone",
}
# Families whose catch removes the cheap supplier; in the others it stays the best choice.
LOSES = {"notice_price", "lead_change", "expired", "withdrawn", "not_covered", "zone"}
NO_OFFER = ("withdrawn", "not_covered", "zone")
OFFERING = tuple(name for name in FAMILIES if name not in NO_OFFER and FAMILIES[name])
ROWS = (20, 32)  # other items listed in one supplier's quote


def _day(offset):
    return (AS_OF + timedelta(days=offset)).isoformat()


def _yuan(minor):
    return f"{minor / 100:.2f}"


def _lead(days):
    return f"下单后{days}个自然日内送达" if days else "下单当日送达"


def _price(shelf_cents, factor):
    return max(10, round(shelf_cents * FX * COST_SHARE * factor / 10) * 10)


def _nearest(rows, sku):
    return min(rows, key=lambda row: (abs(_number(row["item_id"]) - _number(sku)), row["item_id"]))


def read(facts, request, mistake=None):
    """Return (card, evidence): what the documents support, and which document says it.

    These are the rules the terms document states in prose. `mistake` applies one
    named misreading instead, to show that the catch matters to the decision.
    """
    sid, sku, as_of, quote = (
        facts["supplier_id"],
        request["sku_id"],
        request["as_of"],
        facts["quote"],
    )
    done = facts["history"]
    card = {
        "supplier_id": sid,
        "status": "no_offer",
        "reason": None,
        "offer": None,
        "history": {
            "deliveries": len(done),
            "late": sum(row["actual"] > row["promised"] for row in done),
        },
    }
    row = next((row for row in quote["rows"] if row["item_id"] == sku), None)
    if row is None and mistake == "near_miss":
        row = _nearest(quote["rows"], sku)
    notices = [n for n in facts["notices"] if sku in n["lines"]]
    if mistake != "future":
        notices = [n for n in notices if n["effective"] <= as_of]
    revoked = {n["revokes"] for n in notices if n["revokes"]}
    if mistake == "revoked":
        notices = [n for n in notices if not n["revokes"]]
    elif mistake == "notices":
        notices = []
    else:
        notices = [n for n in notices if n["no"] not in revoked]
    notices.sort(key=lambda n: n["effective"])
    withdrawal = next((n for n in notices if n["kind"] == "withdraw"), None)
    if request["district"] not in facts["zone"] and mistake != "zone":
        card["reason"] = "STORE_NOT_SERVED"
        return card, {"status": [f"{sid}-terms"]}
    if row is None:
        card["reason"] = "SKU_NOT_COVERED"
        return card, {"status": [f"{sid}-quote"]}
    if withdrawal:
        card["reason"] = "SUPPLY_WITHDRAWN"
        return card, {"status": [withdrawal["doc_id"]]}
    price, lead = row["price"], row["lead"]
    evidence = {name: [f"{sid}-quote"] for name in ("unit_price_minor", "lead_time_days")}
    for notice in notices:
        if notice["kind"] == "price":
            price, evidence["unit_price_minor"] = notice["lines"][sku][1], [notice["doc_id"]]
        else:
            lead, evidence["lead_time_days"] = notice["lines"][sku][1], [notice["doc_id"]]
    # Misread as per unit what the quote states per case.
    per_case = mistake == "unit" and quote["unit"] == "箱"
    card.update(
        status="offer",
        offer={
            "unit_price_minor": price * row["pack"] if per_case else price,
            "minimum_order_quantity": row["moq"] // row["pack"] if per_case else row["moq"],
            "pack_size": row["pack"],
            "lead_time_days": lead,
            "valid_from": quote["valid_from"],
            "valid_until": _day(14) if mistake == "expiry" else quote["valid_until"],
            "offer_version": quote["no"],
        },
    )
    return card, {
        **evidence,
        "minimum_order_quantity": [f"{sid}-quote"],
        "valid_until": [f"{sid}-quote"],
    }


def _facts(rng, sid, window, modes, *, factor, mode, variant, district, need):
    """One supplier's typed facts; `variant` decides which document carries the catch."""
    sku, shelf = window["item_id"], window["sell_price_cents"]
    lead, pack = modes[mode]["promised_days"], rng.choice((6, 10, 12))
    cover = -(-need // pack) * pack
    price = _price(shelf, factor)
    rows = []
    for other in rng.sample(window["neighbors"], rng.randint(*ROWS)):
        size = rng.choice((6, 10, 12, 24))
        rows.append(
            {
                "item_id": other["item_id"],
                "pack": size,
                "moq": size * rng.choice((1, 2, 3)),
                "price": _price(other["sell_price_cents"], factor),
                "lead": lead,
            }
        )
    wanted = {"pack": pack, "moq": max(pack, cover - pack * rng.choice((0, 1))), "price": price}
    if variant == "not_covered":
        # The closest item number is listed on the terms the missing one would have had.
        _nearest(rows, sku).update(wanted)
    else:
        rows.append({"item_id": sku, **wanted, "lead": lead})
    issued = -rng.randint(12, 30)
    stamp = (AS_OF + timedelta(days=issued)).strftime("%m%d")
    notices, others = [], [row for row in rows if row["item_id"] != sku]

    def notice(kind, lines, issued, effective, revokes=None):
        notices.append(
            {
                "kind": kind,
                "issued": issued,
                "effective": effective,
                "lines": lines,
                "revokes": revokes,
            }
        )
        return notices[-1]

    def change(row, kind):
        if kind == "price":
            return row["price"], row["price"] + 10 * rng.randint(2, 9)
        return (lead, lead + rng.randint(1, 3)) if kind == "lead" else None

    past = (-rng.randint(6, 10), -rng.randint(1, 4))
    raised = _price(shelf, rng.choice((1.14, 1.2)))
    hike = {sku: (price, raised)}
    if variant in ("notice_price", "future_notice", "superseded"):
        # Other items ride along, so naming the item is not enough to find the line.
        hike.update(
            (row["item_id"], change(row, "price")) for row in rng.sample(others, rng.randint(0, 2))
        )
    if variant == "notice_price":
        notice("price", hike, *past)
    elif variant == "future_notice":
        notice("price", hike, -rng.randint(1, 5), rng.randint(2, 9))
    elif variant == "superseded":
        first = notice("price", hike, -9, -7)
        notice("price", {sku: (raised, price + 10 * rng.randint(1, 3))}, -4, -3, revokes=first)
    elif variant == "lead_change":
        notice("lead", {sku: (lead, rng.choice((4, 5)))}, *past)
    elif variant == "withdrawn":
        notice("withdraw", {sku: None}, *past)
    # Notices about other items only, some not yet in force: a notice existing is not the answer.
    for _ in range(rng.choice((0, 1, 1, 2))):
        row, kind = rng.choice(others), rng.choice(("price", "price", "lead", "withdraw"))
        notice(kind, {row["item_id"]: change(row, kind)}, -rng.randint(3, 10), rng.choice((-2, 5)))
    notices.sort(key=lambda n: n["issued"])
    for number, entry in enumerate(notices, 1):
        entry.update(doc_id=f"{sid}-notice-{number}", no=f"TZ-{sid}-{stamp}-{number:02d}")
    for entry in notices:
        entry.update(
            issued=_day(entry["issued"]),
            effective=_day(entry["effective"]),
            revokes=entry["revokes"] and entry["revokes"]["no"],
        )
    served = [d for d in DISTRICTS if d != district]
    zone = rng.sample(served, 3) if variant == "zone" else [district, *rng.sample(served, 2)]
    days, weights = zip(
        *((int(day), n) for day, n in modes[mode]["actual_days"].items()), strict=True
    )
    history = []
    # A supplier that does not deliver to the store has no record with it.
    for ago in (
        []
        if variant == "zone"
        else sorted(rng.sample(range(8, 70), rng.randint(8, 12)), reverse=True)
    ):
        took = rng.choices(days, weights)[0]
        history.append(
            {
                "po": f"PO-{sid}-{(AS_OF - timedelta(days=ago)).strftime('%m%d')}",
                "ordered": _day(-ago),
                "promised": _day(lead - ago),
                "actual": _day(took - ago),
                "qty": pack * rng.randint(2, 6),
            }
        )
    return {
        "supplier_id": sid,
        "name": NAMES[sid],
        "variant": variant,
        "mode": mode,
        "zone": sorted(zone, key=DISTRICTS.index),
        "quote": {
            "no": f"BJ-{sid}-{stamp}",
            "issued": _day(issued),
            "valid_from": _day(issued),
            "valid_until": _day(-rng.randint(1, 5) if variant == "expired" else rng.randint(7, 45)),
            "unit": "箱" if variant == "case_price" else "件",
            "rows": sorted(rows, key=lambda row: row["item_id"]),
        },
        "notices": notices,
        "history": history,
    }


def _quote(facts, category):
    quote = facts["quote"]
    per = quote["unit"]
    lines = [
        f"{facts['name']} 商品报价单",
        "",
        f"报价单号：{quote['no']}",
        f"报价日期：{quote['issued']}",
        f"有效期：{quote['valid_from']} 至 {quote['valid_until']}（含首尾两日）",
        "币种：人民币，含税",
        f"计价单位：{per}（下表起订量与单价均按“{per}”计）",
        f"配送方式：{MODES[facts['mode']]}",
        "",
        f"| 货号 | 品类 | 装箱规格 | 起订量（{per}） | 单价（元/{per}） | 交期 |",
        "|---|---|---|---|---|---|",
    ]
    for row in quote["rows"]:
        scale = row["pack"] if per == "箱" else 1
        lines.append(
            f"| {row['item_id']} | {category} | {row['pack']}件/箱 | {row['moq'] // scale} "
            f"| {_yuan(row['price'] * scale)} | {_lead(row['lead'])} |"
        )
    lines += [
        "",
        "说明：",
        "1. 订货数量须为装箱规格的整数倍。",
        "2. 本报价单的单价与交期可由书面通知函调整，规则见《供货合作条款》第六条。",
    ]
    return "\n".join(lines)


def _notice(facts, notice):
    per = facts["quote"]["unit"]
    packs = {row["item_id"]: row["pack"] if per == "箱" else 1 for row in facts["quote"]["rows"]}
    lines = notice["lines"]
    if notice["kind"] == "price":
        title = "调价通知函（更正）" if notice["revokes"] else "调价通知函"
        opening = (
            f"本通知函撤销 {notice['revokes']} 号通知函中关于下列商品的调价内容。"
            "自生效日期起，下列商品的供货单价按下表执行。"
            if notice["revokes"]
            else "受上游成本变动影响，自生效日期起，下列商品的供货单价调整如下，报价单其余内容不变。"
        )
        body = [f"| 货号 | 原单价（元/{per}） | 新单价（元/{per}） |", "|---|---|---|"] + [
            f"| {item} | {_yuan(old * packs[item])} | {_yuan(new * packs[item])} |"
            for item, (old, new) in lines.items()
        ]
        closing = "生效日期之前下达的订单仍按原单价结算。"
    elif notice["kind"] == "lead":
        title = "交期调整通知函"
        opening = "因仓库搬迁，自生效日期起，下列商品的交期调整如下，报价单其余内容不变。"
        body = ["| 货号 | 原交期 | 新交期 |", "|---|---|---|"] + [
            f"| {item} | {_lead(old)} | {_lead(new)} |" for item, (old, new) in lines.items()
        ]
        closing = "恢复原交期将另行通知。"
    else:
        title = "暂停供货通知函"
        opening = "因产线检修，自生效日期起暂停供应下列商品，报价单中对应条目停止执行。"
        body = [f"- {item}" for item in lines]
        closing = "暂停期间不接受上述商品的新订单，恢复时间另行通知。"
    return "\n".join(
        [
            f"{facts['name']} {title}",
            "",
            f"通知编号：{notice['no']}",
            f"发文日期：{notice['issued']}",
            f"生效日期：{notice['effective']}",
            "",
            "致各合作门店：",
            opening,
            "",
            *body,
            "",
            closing,
        ]
    )


def _terms(facts):
    return "\n".join(
        [
            f"{facts['name']} 供货合作条款（门店版）",
            "",
            "第一条 适用范围",
            "本条款适用于本公司与合作门店之间的日常订货、配送与结算，与报价单、通知函共同构成供货约定。",
            "第二条 配送范围",
            f"本公司自有车队的配送范围为：{'、'.join(facts['zone'])}。"
            "上述范围以外的门店暂不提供配送，也不接受自提订单。",
            "第三条 订货与确认",
            "门店应在每日16:00前通过订货系统下单。订货数量须为装箱规格的整数倍，且不低于报价单载明的起订量。"
            "交期自下单当日起按自然日计算，下单当日不计入。",
            "第四条 验收",
            "门店应在到货当日完成点收，对数量短少或外箱破损在送货单上注明并由送货人签字确认，未注明的视为验收合格。",
            "第五条 退换货",
            "因本公司原因造成的质量问题，门店可在到货后3日内凭送货单与照片申请退换；因门店储存不当造成的损失不予退换。",
            "第六条 价格与交期调整",
            "报价单载明的单价与交期可由本公司以书面通知函调整。通知函自其载明的生效日期起执行，生效日期之前不影响现行报价；"
            "同一商品有多份已生效通知函的，以生效日期最近的一份为准；被后续通知函明确撤销的内容不再执行。"
            "报价单有效期届满后，其价格不再保证，须重新报价。",
            "第七条 结算",
            "货款按月结算，账期30天。门店应在对账单确认后的账期内付款，逾期按日加收万分之三的滞纳金。",
            "第八条 不可抗力",
            "因自然灾害、交通管制、政府行为等不可抗力导致延迟或无法交货的，本公司应及时通知门店，双方互不承担违约责任。",
            "第九条 保密",
            "双方对合作中获知的价格、销量与客户信息负有保密义务，未经对方书面同意不得向第三方披露。",
            "第十条 争议解决",
            "因本条款产生的争议由双方协商解决；协商不成的，提交本公司所在地人民法院处理。",
        ]
    )


def _history(facts, request):
    head = f"{facts['name']} 近期履约记录（门店：{request['store_id']}，{request['district']}）"
    if not facts["history"]:
        return head + "\n\n该门店暂无履约记录。"
    rows = [
        f"{row['po']},{row['ordered']},{row['promised']},{row['actual']},{row['qty']},{row['qty']}"
        for row in facts["history"]
    ]
    return "\n".join(
        [head, "", "订单号,下单日期,约定送达日期,实际送达日期,订货数量,实收数量", *rows]
    )


def documents(facts, request, category):
    sid = facts["supplier_id"]
    return [
        {"doc_id": f"{sid}-quote", "kind": "quote", "text": _quote(facts, category)},
        *(
            {"doc_id": notice["doc_id"], "kind": "notice", "text": _notice(facts, notice)}
            for notice in facts["notices"]
        ),
        {"doc_id": f"{sid}-terms", "kind": "terms", "text": _terms(facts)},
        {"doc_id": f"{sid}-history", "kind": "history", "text": _history(facts, request)},
    ]


def _world(rng, window, modes, family):
    """Sample one world, or None when the draw does not produce the family's outcome."""
    demand, sku = window["demand"], window["item_id"]
    k = rng.choice((1, 2, 3))
    arrives = min(6, k + rng.choice((1, 2, 3)))
    need = sum(demand[k:arrives])
    request = {
        "store_id": window["store_id"],
        "district": rng.choice(DISTRICTS),
        "sku_id": sku,
        "as_of": AS_OF.isoformat(),
        "shortfall_qty": need,
        "short_from": _day(k),
    }
    mistake = FAMILIES[family]
    # A baseline world carries no catch at all, so it has no supplier to rule out.
    ids = sorted(rng.sample(sorted(NAMES), rng.choice((2, 3, 3, 4, 5) if mistake else (2, 3))))
    cheap, rival, *rest = rng.sample(ids, len(ids))
    quick = sorted(mode for mode, value in modes.items() if value["promised_days"] <= k)

    def supplier(sid, factors, speeds, variants):
        return _facts(
            rng,
            sid,
            window,
            modes,
            factor=rng.choice(factors),
            mode=rng.choice(speeds),
            variant=rng.choice(variants) if mistake else "plain",
            district=request["district"],
            need=need,
        )

    facts = {
        cheap: supplier(cheap, (0.86, 0.9), quick, (family,)),
        # The rival's own catches never move it: its price and speed read true either way.
        rival: supplier(
            rival,
            (1.0, 1.04),
            quick,
            ("plain", "plain", "case_price", "future_notice", "superseded"),
        ),
    }
    room = 1  # the solver takes three offers and the misreading may count the cheap one
    for sid in rest:
        offers = bool(room) and rng.random() < 0.6
        room -= offers
        facts[sid] = supplier(
            sid, (1.12, 1.18, 1.26), sorted(modes), ("plain", *OFFERING) if offers else NO_OFFER
        )
    truth = {sid: read(facts[sid], request) for sid in ids}
    cards = [truth[sid][0] for sid in ids]
    offer = truth[rival][0]["offer"]
    cover = max(
        -(-need // offer["pack_size"]) * offer["pack_size"], offer["minimum_order_quantity"]
    )
    budget = (cover + rng.choice((0, 1)) * offer["pack_size"]) * offer["unit_price_minor"]
    recovery = build(
        on_hand=sum(demand[:k]),
        demand=demand,
        inbound=[(sum(demand[k:]), 0, arrives)],
        cash=50000 + budget + rng.choice((0, 3000, 10000)),
        budget=budget,
        offers=[],
    )
    recovery.update(store_id=request["store_id"], sku_id=sku)
    recovery["arrivals"][0]["sku_id"] = sku
    result = decide(recovery, cards)
    if result is None or len(result.candidates) > 14:
        return None
    by_id = {c.id: c for c in result.candidates}
    chosen = by_id[result.recommended_candidate_id]
    if not (
        by_id["wait"].lost_qty > 0
        and chosen.lost_qty == 0
        and chosen.supplier_id == (rival if family in LOSES else cheap)
    ):
        return None
    catch = None
    if mistake:
        naive = [
            read(facts[sid], request, mistake)[0] if sid == cheap else truth[sid][0] for sid in ids
        ]
        misled = decide(recovery, naive)
        if misled is None or misled.recommended_candidate_id == chosen.id:
            return None
        catch = {
            "supplier_id": cheap,
            "mistake": mistake,
            "misread_recommendation": misled.recommended_candidate_id,
        }
    category = CATEGORY[sku.split("_", 1)[0]]
    return {
        "source": {key: window[key] for key in ("series_id", "week_start", "sell_price_cents")},
        "request": request,
        "catch": catch,
        "suppliers": [
            {
                "supplier_id": sid,
                "name": NAMES[sid],
                "variant": facts[sid]["variant"],
                "documents": documents(facts[sid], request, category),
                "card": truth[sid][0],
                "evidence": {**truth[sid][1], "history": [f"{sid}-history"]},
            }
            for sid in ids
        ],
        "recovery": recovery,
        "result": result,
    }


def generate(sources):
    """Deterministic for a given sources file. Partitions never share an M5 series."""
    from app.planning.recovery.schemas import RecoveryInput

    windows, modes = sources["m5"]["windows"], sources["dataco"]["modes"]
    series = sorted({window["series_id"] for window in windows})
    random.Random(DATASET).shuffle(series)
    fixtures, names, total, taken = [], list(FAMILIES), sum(PARTITIONS.values()), 0
    for partition, count in PARTITIONS.items():
        low, high = (round(len(series) * part / total) for part in (taken, taken + count))
        taken += count
        pool = [window for window in windows if window["series_id"] in series[low:high]]
        random.Random(f"{DATASET}:{partition}").shuffle(pool)
        for index in range(count):
            family = names[index % len(names)]
            rng = random.Random(f"{DATASET}:{partition}:{family}:{index}")
            # Some weeks cannot host a family (prices too close, gap too small); try the next.
            for window in list(pool):
                world = next(
                    filter(None, (_world(rng, window, modes, family) for _ in range(200))), None
                )
                if world:
                    pool.remove(window)
                    break
            else:
                raise RuntimeError(f"no {partition} week can host {family}")
            case_id = f"{partition}-{family}-{index:02d}"
            result, recovery = world.pop("result"), world.pop("recovery")
            offers = [
                to_offer(supplier["card"], recovery["sku_id"])
                for supplier in world["suppliers"]
                if supplier["card"]["status"] == "offer"
            ]
            snapshot = RecoveryInput.model_validate({**recovery, "offers": offers})
            proposal = {"id": f"proposal:{case_id}", **result.model_dump(mode="json")}
            fixtures.append(
                {
                    "case_id": case_id,
                    "partition": partition,
                    "family": family,
                    **world,
                    "snapshot": {"recovery": snapshot.model_dump(mode="json")},
                    "proposal": proposal,
                    "required": required_conditions(proposal),
                }
            )
    bodies = [_hash({k: f[k] for k in ("snapshot", "required")}) for f in fixtures]
    if len(set(bodies)) != len(bodies):
        raise RuntimeError("two cases share one fixture; partitions would leak")
    return fixtures


def write_dataset(directory):
    """Write the worlds next to the `sources.json` they are built from."""
    directory = Path(directory)
    sources = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    return _write(
        directory,
        generate(sources),
        dataset=DATASET,
        simple={"baseline"},
        inputs=("sources.json",),
        research_status="development worlds: real M5 demand and prices, DataCo delivery "
        "delays, invented suppliers and documents; no locked test set",
    )
