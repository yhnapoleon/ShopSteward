"""Publish 150 explicitly authored additions plus the unchanged smoke50 subset."""

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "posttraining/datasets"
smoke = [
    json.loads(line) for line in (DATA / "smoke-50.jsonl").read_text(encoding="utf-8").splitlines()
]
rows = copy.deepcopy(smoke)
counts = Counter(row["task_type"] for row in rows)
eval_predicates = smoke[0]["final_predicates"]
revise_predicates = smoke[10]["final_predicates"]


def add(
    task,
    family,
    message,
    action,
    quantity=None,
    *,
    version=1,
    history=None,
    slot=None,
    followup=None,
    rationale,
):
    task = f"PT-{task:02d}"
    counts[task] += 1
    expected = {"allowed_actions": [action], "arguments": {}, "clarification_slot": slot}
    if action in {"evaluate_plan", "revise_plan"}:
        expected["arguments"] = {"plan_id": "$current_plan_id", "max_purchase_qty": quantity}
        if action == "revise_plan":
            expected["arguments"]["expected_mission_version"] = "$current_mission_version"
        predicates = eval_predicates if action == "evaluate_plan" else revise_predicates
    elif action == "clarify":
        predicates = ["clarification_relevant", "no_business_mutation"]
    else:
        expected["arguments"] = {
            "reason": "withdraw_current_request" if action == "no_action" else "unsupported_request"
        }
        predicates = (
            ["request_ended", "mission_not_cancelled", "no_business_mutation"]
            if action == "no_action"
            else ["handoff_recorded", "no_business_mutation"]
        )
    steps = [expected]
    if followup:
        reply, next_action, next_quantity = followup
        arguments = {"plan_id": "$current_plan_id", "max_purchase_qty": next_quantity}
        if next_action == "revise_plan":
            arguments["expected_mission_version"] = "$current_mission_version"
        steps.append(
            {"allowed_actions": [next_action], "arguments": arguments, "clarification_slot": None}
        )
        predicates = [
            "clarification_relevant",
            "no_mutation_before_reply",
            *(eval_predicates if next_action == "evaluate_plan" else revise_predicates),
        ]
    rows.append(
        {
            "episode_id": f"dev-{task.lower().replace('-', '')}-{counts[task]:03d}",
            "task_type": task,
            "scenario_family": family,
            "split": "dev",
            "suite": "core" if task in {"PT-01", "PT-02", "PT-03", "PT-04"} else "challenge",
            "fixture_recipe": "replenishment_standard"
            if version == 1
            else "replenishment_capped"
            if version == 2
            else "replenishment_revised",
            "fixture_mission_version": version,
            "history": history or [],
            "user_message": message,
            "followup_user_message": followup[0] if followup else None,
            "expected_steps": steps,
            "final_predicates": list(predicates),
            "review": {"reviewer": "codex", "status": "agent_reviewed", "rationale": rationale},
            "execution_status": "not_run",
            "known_limitations": [],
        }
    )


# Each numeric target below is authored explicitly, never inferred by the baseline.
for family, cases in [
    (
        "counterfactual-cap-values",
        [
            ("假设本次最多采购35件，先算算效果。", 35),
            ("如果本次最多补货7件，会发生什么变化？", 7),
            ("如果本次采购上限设为999999件，结果怎样？", 999999),
            ("假设这一单完全不补货，即上限为0件，算一下。", 0),
            ("试算本次采购上限3件的方案。", 3),
        ],
    ),
    (
        "trial-verb-paraphrases",
        [
            ("仅做推演：本次最多买25件。", 25),
            ("评估本次最多采购60件的可能结果，先不落实。", 60),
            ("看看本次采购数量封顶15件的模拟结果。", 15),
            ("先做沙盘推演，本次采购限额是45件。", 45),
            ("本次若只允许买18件，计算候选方案供我参考。", 18),
        ],
    ),
    (
        "written-numeral-evaluation",
        [
            ("如果本次上限为两百零五件，试算结果如何？", 205),
            ("只试算本次采购上限一千零一件。", 1001),
            ("假设本次采购上限是一万零三件。", 10003),
            ("只试算本次最多采购九十九件。", 99),
            ("如果本次最多采购十一件，会怎样？", 11),
        ],
    ),
    (
        "evaluation-numeric-distractors",
        [
            ("库存数字先忽略；试算本次上限25件，不是旧的10件。", 25),
            ("试算本次最多买8件，店员刚才提过50件但那不是我的要求。", 8),
            ("前一个建议是40件，现在仅试算上限12件。", 12),
            ("只模拟本次上限65件；数字80件只是旧笔记。", 65),
            ("上限先试算为16件，而不是我误写的61件。", 16),
        ],
    ),
    (
        "english-hypothetical-request",
        [
            ("What if the purchase cap for this mission is 17 units? Do not change the plan.", 17),
            ("Simulate a maximum purchase of 23 units for this request only.", 23),
            ("Evaluate the current plan with a purchase cap of 0 units, read only.", 0),
            ("For this mission, hypothetically cap the order at 125 units.", 125),
            ("只做what-if，本次purchase cap设为42件。", 42),
        ],
    ),
]:
    for message, quantity in cases:
        add(
            1,
            family,
            message,
            "evaluate_plan",
            quantity,
            rationale=f"用户只要求假设或试算，目标上限为{quantity}件；其他数字/措辞不授权正式修订。",
        )
for message, quantity in [
    ("当前上限20件，如果提高5件，试算一下。", 25),
    ("以当前20件上限为基础，假设减去3件。", 17),
    ("当前20件的上限如果翻倍，仅试算结果。", 40),
    ("只试算当前20件上限的一半。", 10),
    ("假设现有20件上限再增加12件，结果如何？", 32),
]:
    add(
        1,
        "relative-evaluation-from-visible-cap",
        message,
        "evaluate_plan",
        quantity,
        version=2,
        rationale=f"可见当前上限20，明确的相对运算得到{quantity}；仅试算，不写入。",
    )

for family, cases in [
    (
        "absolute-cap-revision-values",
        [
            ("将当前方案本次采购上限修改为35件。", 35),
            ("本次采购上限正式改成7件，请生成新方案。", 7),
            ("调整本次最高采购数量为999999件。", 999999),
            ("这次先不补货，请把采购上限改成0件。", 0),
            ("本次数量上限请改为3件。", 3),
        ],
    ),
    (
        "revision-with-old-request-negation",
        [
            ("不沿用旧的50件要求；请把本次上限改为12件。", 12),
            ("别再考虑旧方案了，修改当前方案的上限为25件。", 25),
            ("上次的修改取消讨论；这一次明确修改上限为60件。", 60),
            ("我不改旧方案，只把当前方案上限调整为9件。", 9),
            ("试算阶段结束，正式将本次上限修改成45件。", 45),
        ],
    ),
    (
        "revision-numeric-distractors",
        [
            ("正式修改本次上限为28件，不是旧记录里的82件。", 28),
            ("请把当前采购上限改成13件，30件是误写。", 13),
            ("将本次上限改为55件；那条5件的建议作废。", 55),
            ("本次上限改成21件，不采纳供应商建议的40件。", 21),
            ("修改本次上限为6件；之前60件的数字不要使用。", 6),
        ],
    ),
    (
        "written-numeral-revision",
        [
            ("请把本次采购上限改为两百零五件。", 205),
            ("将本次采购上限修改成一千零一件。", 1001),
            ("本次采购数量上限调整为一万零三件。", 10003),
            ("请将本次最多采购量改为九十九件。", 99),
            ("把本次采购上限改为十一件。", 11),
        ],
    ),
    (
        "english-explicit-revision",
        [
            ("Change the current purchase cap to 17 units for this mission.", 17),
            ("Revise the current plan: maximum purchase quantity is 23 units.", 23),
            ("Please change this order's quantity cap to zero units.", 0),
            ("Set the purchase limit for the current plan to 125 units.", 125),
            ("当前方案purchase cap请正式修改为42件。", 42),
        ],
    ),
]:
    for index, (message, quantity) in enumerate(cases):
        add(
            2,
            family,
            message,
            "revise_plan",
            quantity,
            version=[1, 2, 3, 7, 1][index],
            rationale=f"最后有效要求明确修订当前方案，上限{quantity}；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。",
        )
for message, quantity in [
    ("当前上限20件，请在这个基础上增加5件，修改本次方案。", 25),
    ("把当前20件上限减少3件，正式修订方案。", 17),
    ("将当前20件的采购上限翻倍，修改方案。", 40),
    ("请修改本次方案，把当前20件上限减半。", 10),
    ("现有上限20件，本次再增加12件，请按此修改。", 32),
]:
    add(
        2,
        "relative-revision-from-visible-cap",
        message,
        "revise_plan",
        quantity,
        version=2,
        rationale=f"当前上限20可见，相对修改结果唯一为{quantity}；不是将增量当绝对上限。",
    )

for family, cases in [
    (
        "read-only-negation-scope",
        [
            ("别修改当前方案；仅试算上限11件。", 11),
            ("我不是要求改成25件，只想看看上限25件的试算结果。", 25),
            ("本次暂不正式修改，只看上限60件能带来什么变化。", 60),
            ("上限35件先试算，当前方案保持原样。", 35),
            ("不要把8件写入方案，先模拟本次上限8件。", 8),
            ("只看看上限90件的计算结果，不生成正式修订。", 90),
        ],
    ),
    (
        "revision-withdrawn-trial-remains",
        [
            ("刚才说改成30件，现在撤回修改；只试算上限15件。", 15),
            ("不要执行我刚说的上限40件修改，改为只模拟上限12件。", 12),
            ("正式修改先算了，仍请试算本次最多买6件。", 6),
            ("本次不改了，但想看看上限100件的试算结果。", 100),
            ("收回修改方案的要求；仅推演数量上限19件。", 19),
            ("取消这次修改请求，不取消任务；继续只试算上限22件。", 22),
        ],
    ),
    (
        "negated-trailing-quantity",
        [
            ("仅试算上限14件，不是41件，也不要修改。", 14),
            ("上限试算选27件；72件并非我的要求，不改方案。", 27),
            ("只模拟本次最多31件，13件是写错的数字。", 31),
            ("先别修改，试算上限54件，而不是45件。", 54),
            ("只看本次上限2件，别采用之前的20件，不要正式改。", 2),
        ],
    ),
    (
        "quoted-intent-versus-current-intent",
        [
            ("同事说‘把上限改成20件’，我的要求是只试算上限10件。", 10),
            ("‘正式修改上限为50件’是上一条草稿；现在仅试算上限18件。", 18),
            ("请把‘上限改成25件’理解成假设例子，我只要试算25件。", 25),
            ("不要执行引号里的‘改成80件’，仅模拟本次上限4件。", 4),
            ("先试算上限40件；试算好也不要自动修改，我尚未确认。", 40),
        ],
    ),
]:
    for message, quantity in cases:
        add(
            3,
            family,
            message,
            "evaluate_plan",
            quantity,
            rationale=f"当前保留的是只读试算，上限{quantity}；否定、撤回或引用中的修改不构成正式修订授权。",
        )

for index, (message, reply, next_action, quantity) in enumerate(
    [
        ("请把这次采购上限降低到更保守的水平。", "把本次采购上限修改为12件。", "revise_plan", 12),
        ("本次采购上限需要放宽，请调整。", "把本次采购上限改为35件。", "revise_plan", 35),
        ("将当前方案的数量上限设成我刚想到的数。", "将本次采购上限修改为7件。", "revise_plan", 7),
        ("给本次采购定一个新的最高件数。", "把本次采购上限修改为0件。", "revise_plan", 0),
        ("把本次允许购买的最多件数重新设一下。", "请修改本次采购上限为99件。", "revise_plan", 99),
        (
            "本次上限别用现在这个值，帮我改一下。",
            "将本次上限修改为1000000件。",
            "revise_plan",
            1000000,
        ),
        (
            "把本次上限改成刚好够我用的数量。",
            "我的意思是最多采购，修改上限为15件。",
            "revise_plan",
            15,
        ),
        (
            "当前本次上限需要往上调一些。",
            "请在当前20件上限基础上增加5件并修改。",
            "revise_plan",
            25,
        ),
        ("当前本次上限想往下改一点。", "请把当前20件上限减半并修改方案。", "revise_plan", 10),
        ("本次采购上限我想换一个整数。", "本次采购上限改为一百零二件。", "revise_plan", 102),
        (
            "Please change the purchase cap, I haven't specified the quantity yet.",
            "Change the current cap to 23 units.",
            "revise_plan",
            23,
        ),
        ("只模拟本次限制采购数量的情况，上限还没选。", "只试算本次上限13件。", "evaluate_plan", 13),
        ("假设本次上限变小，算一下会怎样。", "仅试算本次上限0件。", "evaluate_plan", 0),
        ("只想试算不同的最高件数。", "仅试算本次最多采购1件。", "evaluate_plan", 1),
        ("先不改方案，试算本次采购封顶后的结果。", "只试算本次上限37件。", "evaluate_plan", 37),
        (
            "如果这次只能少买一些，先评估一下。",
            "假设本次采购上限为66件，仅试算。",
            "evaluate_plan",
            66,
        ),
        (
            "只做假设试算，本次上限选另一个数。",
            "只试算本次采购上限999999件。",
            "evaluate_plan",
            999999,
        ),
        ("本次上限暂不写入，只想换一个数量模拟。", "仅试算上限两百件。", "evaluate_plan", 200),
        (
            "如果当前20件上限有所增加，先试算一下。",
            "只试算当前20件上限增加7件的结果。",
            "evaluate_plan",
            27,
        ),
        (
            "现在的20件上限如果减少一点呢？只试算。",
            "只试算当前20件上限减少2件。",
            "evaluate_plan",
            18,
        ),
        (
            "Simulate a new purchase cap, but ask me for the quantity first.",
            "Only simulate a cap of 29 units.",
            "evaluate_plan",
            29,
        ),
        ("请试算本次换成我选的那个上限。", "只试算本次上限47件，不是74件。", "evaluate_plan", 47),
    ]
):
    version = 2 if index in {1, 5, 7, 8, 18, 19} else 1
    family = (
        "missing-revision-target"
        if index < 7
        else "missing-target-relative-or-written"
        if index < 11
        else "missing-trial-target"
        if index < 18
        else "missing-trial-relative-or-corrected"
    )
    add(
        4,
        family,
        message,
        "clarify",
        version=version,
        slot="max_purchase_qty",
        followup=(reply, next_action, quantity),
        rationale=f"首句没有唯一数值，必须先询问数量；完整回复后应{next_action}并绑定上限{quantity}。",
    )


def past(quantity, action="evaluate_plan"):
    return {
        "user_message": f"{'只试算' if action == 'evaluate_plan' else '请修改'}本次采购上限{quantity}件。",
        "action": action,
        "max_purchase_qty": quantity,
        "plan_reference": "$current_plan_id",
    }


for message, history, quantity, version in [
    ("按刚刚唯一一次试算的数量上限，正式修改本次方案。", [past(35)], 35, 1),
    ("前面零采购的试算就是我要的，请据此修改上限。", [past(0)], 0, 1),
    ("两个试算中，请按第一种数量上限修改本次方案。", [past(12), past(40)], 12, 1),
    ("两个试算中，请按后一个上限修改当前方案。", [past(7), past(55)], 55, 1),
    ("两次试算数量相同，就按那个上限修改。", [past(18), past(18)], 18, 1),
    ("刚修改过的上限再试算一次，正式方案保持原样。", [past(60, "revise_plan")], 60, 2),
]:
    action = "evaluate_plan" if version == 2 else "revise_plan"
    add(
        5,
        "resolvable-history-reference",
        message,
        action,
        quantity,
        version=version,
        history=history,
        rationale=f"可见历史和明确序号/相同数值使目标唯一为{quantity}；绑定当前对象，不要求用户重复已知数。",
    )
for message, history in [
    ("刚才那两个方案，挑我说的那个上限修改。", [past(9), past(24)]),
    ("按昨天告诉你的采购上限修改这次方案。", []),
    ("按之前提过的另一个上限修改。", [past(30)]),
]:
    add(
        5,
        "unresolvable-history-reference",
        message,
        "clarify",
        history=history,
        slot="history_reference",
        rationale="可见历史不能唯一确定所指目标；询问具体数量或候选，不猜最近值或不可见的昨天对话。",
    )

for index, message in enumerate(
    [
        "撤回本轮修改采购上限的要求，原任务继续。",
        "这条改数量的请求作废，不要再处理。",
        "现在不需要调整上限了，保持现状。",
        "停止处理我的这次修改请求，但不要停掉补货任务。",
        "这次想改成50件的提议不算数，保留已经设好的20件。",
        "我不想把20件改成30件了，撤回当前请求。",
        "Withdraw my current cap-change request; keep the mission and existing plan active.",
    ]
):
    add(
        6,
        "withdraw-request-preserve-mission",
        message,
        "no_action",
        version=2 if index >= 2 else 1,
        rationale="明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。",
    )
for message, slot in [
    ("把本次采购上限改为-1件。", "valid_quantity"),
    ("本次采购上限请修改成负三件。", "valid_quantity"),
    ("将本次采购上限改为0.5件。", "valid_quantity"),
    ("本次采购上限修改成3.14件。", "valid_quantity"),
    ("请将本次采购上限改成一百零一万件。", "valid_quantity"),
    ("把本次上限改成2000000件。", "valid_quantity"),
    ("仅试算本次上限-8件。", "valid_quantity"),
    ("假设本次采购上限为1000002件，试算一下。", "valid_quantity"),
    ("本次不是最多买8件，是必须恰好采购8件。", "quantity_semantics"),
    ("本次必须至少采购30件，我要的是最低数量，不是上限。", "quantity_semantics"),
    ("采购数量必须等于45件，不能少一件；请按精确量修改。", "quantity_semantics"),
    ("请把本次采购上限设置成布尔值true。", "valid_quantity"),
]:
    add(
        7,
        "illegal-cap-values" if slot == "valid_quantity" else "unsupported-exact-or-lower-bound",
        message,
        "clarify",
        slot=slot,
        rationale="输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。",
    )
for message in [
    "请总结上个月各门店的盈利情况。",
    "帮我写本季度门店经营复盘报告。",
    "直接取消已经发给供应商的采购订单。",
    "请把牛奶的销售单价改成18元。",
    "给供应商发邮件，谈一下采购折扣。",
    "为这家店制定未来三个月的营销方案。",
    "删除上一周的库存流水记录。",
    "Approve the purchase plan and submit the order to the supplier now.",
]:
    add(
        8,
        "outside-cap-policy-scope",
        message,
        "handoff",
        rationale="请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。",
    )
for message in [
    "本次采购上限修改为3盒。",
    "把本次最多采购数量改为8包。",
    "本次采购数量最多买2托盘，请修改。",
    "把本次采购上限调整为6袋。",
    "本次以10组为采购上限，调整方案。",
    "只试算本次最多采购5箱，未确定每箱规格。",
    "Change this purchase cap to 4 cartons; I haven't specified units per carton.",
]:
    add(
        9,
        "unknown-package-size",
        message,
        "clarify",
        slot="quantity_unit",
        rationale="工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。",
    )
for message in [
    "请修改本次方案，移除现有20件数量上限，不再加额外件数限制。",
    "不是把上限改为0件，而是取消本次额外的数量上限。",
    "Remove the extra purchase quantity limit from the current plan; do not set it to zero.",
]:
    add(
        10,
        "explicit-unbounded-versus-zero",
        message,
        "revise_plan",
        None,
        version=2,
        rationale="现有上限20，明确移除额外上限应传null；0代表禁止采购，与本要求不同。",
    )


def main():
    target = {f"PT-{i:02d}": n for i, n in enumerate([40, 40, 30, 30, 12, 10, 16, 10, 8, 4], 1)}
    assert counts == target, (counts, target)
    assert len(rows) == 200 and rows[:50] == smoke
    families = Counter(row["scenario_family"] for row in rows)
    assert len(families) >= 40 and max(families.values()) <= 10
    dataset = DATA / "dev-v1.jsonl"
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schema_version": "eval-v0",
        "release_status": "spec_validated_pending_execution",
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "provenance": "Codex-authored synthetic evaluation cases derived from task semantics; family names are semantic groups, not independent real-world sources. Smoke50 is the unchanged subset.",
        "episodes": [
            {key: row[key] for key in ("episode_id", "scenario_family", "split")} for row in rows
        ],
    }
    (DATA / "dev-v1-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    config = json.loads(
        (ROOT / "posttraining/configs/eval_smoke_v1.json").read_text(encoding="utf-8")
    )
    config.update(
        runtime="runtime_dev_v1.json",
        dataset="../datasets/dev-v1.jsonl",
        manifest="../datasets/dev-v1-manifest.json",
        expected_counts=target,
        case_list="../../docs/reports/posttraining/dev-v1-cases.md",
        validation_report="../../docs/reports/posttraining/dev-v1-validation.json",
    )
    (ROOT / "posttraining/configs/eval_dev_v1.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    runtime = json.loads(
        (ROOT / "posttraining/configs/runtime_v1.json").read_text(encoding="utf-8")
    )
    runtime["frozen_contexts"] = "../datasets/frozen-dev-v1.json"
    (ROOT / "posttraining/configs/runtime_dev_v1.json").write_text(
        json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "episodes": len(rows),
                "families": len(families),
                "counts": counts,
                "sha256": manifest["dataset_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
