# smoke 案例清单

共 200 个 episode，230 个决策目标。

本清单包含评测金标，不能作为模型输入。规格复核不等于真实工具执行或模型成绩。
Agent 复核：200；人工复核：0；执行验证：0。

| ID | 类型 | 请求 | 预期动作/参数或澄清缺项 | 后续回复 |
|---|---|---|---|---|
| dev-pt01-001 | PT-01 | 如果本次采购上限是20件，会怎样？ | evaluate_plan {"max_purchase_qty": 20, "plan_id": "$current_plan_id"} | — |
| dev-pt01-002 | PT-01 | 假设这次一件也不额外采购，也就是采购上限0件，帮我试算。 | evaluate_plan {"max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt01-003 | PT-01 | 如果本次最多采购1件，结果会是什么？ | evaluate_plan {"max_purchase_qty": 1, "plan_id": "$current_plan_id"} | — |
| dev-pt01-004 | PT-01 | 假设本次采购数量上限为1000000件，请看一下结果。 | evaluate_plan {"max_purchase_qty": 1000000, "plan_id": "$current_plan_id"} | — |
| dev-pt01-005 | PT-01 | 如果这次最多采购二十件呢？ | evaluate_plan {"max_purchase_qty": 20, "plan_id": "$current_plan_id"} | — |
| dev-pt01-006 | PT-01 | 本次采购上限假设是35件，能试算一下吗？ | evaluate_plan {"max_purchase_qty": 35, "plan_id": "$current_plan_id"} | — |
| dev-pt01-007 | PT-01 | 试算本次采购最多12件的方案给我看。 | evaluate_plan {"max_purchase_qty": 12, "plan_id": "$current_plan_id"} | — |
| dev-pt01-008 | PT-01 | 正式方案保持原样，模拟本次最多30件的情况。 | evaluate_plan {"max_purchase_qty": 30, "plan_id": "$current_plan_id"} | — |
| dev-pt01-009 | PT-01 | 当前额外上限是20件，如果本次改按40件的上限试算，会怎样？ | evaluate_plan {"max_purchase_qty": 40, "plan_id": "$current_plan_id"} | — |
| dev-pt01-010 | PT-01 | 如果把本次上限调成80件，我想看看结果。 | evaluate_plan {"max_purchase_qty": 80, "plan_id": "$current_plan_id"} | — |
| dev-pt02-001 | PT-02 | 把本次采购上限改成20件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 20, "plan_id": "$current_plan_id"} | — |
| dev-pt02-002 | PT-02 | 把本次采购数量上限改成0件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt02-003 | PT-02 | 请将本次采购上限修改为1件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 1, "plan_id": "$current_plan_id"} | — |
| dev-pt02-004 | PT-02 | 将本次采购数量上限改成1000000件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 1000000, "plan_id": "$current_plan_id"} | — |
| dev-pt02-005 | PT-02 | 把这次采购上限改成二十五件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt02-006 | PT-02 | 旧方案我不改了；请把当前方案的本次采购上限改成30件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 30, "plan_id": "$current_plan_id"} | — |
| dev-pt02-007 | PT-02 | 麻烦将本次采购上限调整为15件，谢谢。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 15, "plan_id": "$current_plan_id"} | — |
| dev-pt02-008 | PT-02 | 当前本次上限20件，请改成10件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 10, "plan_id": "$current_plan_id"} | — |
| dev-pt02-009 | PT-02 | 本次采购上限改成40件，不，改成30件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 30, "plan_id": "$current_plan_id"} | — |
| dev-pt02-010 | PT-02 | 按当前方案，把本次采购上限改成60件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 60, "plan_id": "$current_plan_id"} | — |
| dev-pt03-001 | PT-03 | 先别改，只看本次上限20件的试算结果。 | evaluate_plan {"max_purchase_qty": 20, "plan_id": "$current_plan_id"} | — |
| dev-pt03-002 | PT-03 | 不要保存修改，只试算本次采购上限0件。 | evaluate_plan {"max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt03-003 | PT-03 | 原本想把本次上限改成30件，现在先只试算上限10件。 | evaluate_plan {"max_purchase_qty": 10, "plan_id": "$current_plan_id"} | — |
| dev-pt03-004 | PT-03 | 把上限改成20件——这句话先撤回，只做本次上限20件的试算。 | evaluate_plan {"max_purchase_qty": 20, "plan_id": "$current_plan_id"} | — |
| dev-pt03-005 | PT-03 | 正式方案照旧，请模拟本次采购上限40件。 | evaluate_plan {"max_purchase_qty": 40, "plan_id": "$current_plan_id"} | — |
| dev-pt03-006 | PT-03 | 别调整正式方案，假设本次最多采购一百万件，看看结果。 | evaluate_plan {"max_purchase_qty": 1000000, "plan_id": "$current_plan_id"} | — |
| dev-pt03-007 | PT-03 | 不用修改成80件，只试算本次最多八件。 | evaluate_plan {"max_purchase_qty": 8, "plan_id": "$current_plan_id"} | — |
| dev-pt03-008 | PT-03 | 只看本次上限20件的试算，不是30件，也不要修改。 | evaluate_plan {"max_purchase_qty": 20, "plan_id": "$current_plan_id"} | — |
| dev-pt04-001 | PT-04 | 把本次采购上限调低一些。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 20, "plan_id": "$current_plan_id"} | 把本次采购上限改成20件。 |
| dev-pt04-002 | PT-04 | 如果把本次采购上限调低一些，会怎样？ | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 10, "plan_id": "$current_plan_id"} | 只试算本次采购上限10件。 |
| dev-pt04-003 | PT-04 | 把本次采购上限提高一点。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 50, "plan_id": "$current_plan_id"} | 把本次采购上限改成50件。 |
| dev-pt04-004 | PT-04 | 帮我把本次采购上限改成一个合适的数。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 30, "plan_id": "$current_plan_id"} | 把本次采购上限改成30件。 |
| dev-pt04-005 | PT-04 | 试算一下本次采购上限换成另一档的结果。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 0, "plan_id": "$current_plan_id"} | 只试算本次采购上限0件。 |
| dev-pt04-006 | PT-04 | 先把本次采购上限改一下。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 1, "plan_id": "$current_plan_id"} | 把本次采购上限改成1件。 |
| dev-pt04-007 | PT-04 | 请将本次采购上限修改为我能接受的数量。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 80, "plan_id": "$current_plan_id"} | 把本次采购上限改成80件。 |
| dev-pt04-008 | PT-04 | 如果给本次采购设一个数量上限，结果如何？ | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 1000000, "plan_id": "$current_plan_id"} | 只试算本次采购上限1000000件。 |
| dev-pt05-001 | PT-05 | 按刚才试算的上限修改本次方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 20, "plan_id": "$current_plan_id"} | — |
| dev-pt05-002 | PT-05 | 按前面两个试算里的那个上限修改本次方案。 | clarify 询问 history_reference | — |
| dev-pt05-003 | PT-05 | 照之前说的那个数量，把本次上限改一下。 | clarify 询问 history_reference | — |
| dev-pt06-001 | PT-06 | 算了，这次不用改了。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-002 | PT-06 | 先不改本次采购上限了，现有方案留着。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-003 | PT-06 | 之前改好的20件上限保留；这次想调40件的请求算了。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt07-001 | PT-07 | 把本次采购上限改成-5件。 | clarify 询问 valid_quantity | — |
| dev-pt07-002 | PT-07 | 把本次采购上限改成20.5件。 | clarify 询问 valid_quantity | — |
| dev-pt07-003 | PT-07 | 把本次采购上限改成1000001件。 | clarify 询问 valid_quantity | — |
| dev-pt07-004 | PT-07 | 本次必须刚好买20件，不是最多20件。 | clarify 询问 quantity_semantics | — |
| dev-pt08-001 | PT-08 | 给我做一份本季度经营分析报告。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-002 | PT-08 | 直接批准当前采购方案并替我下单。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt09-001 | PT-09 | 把本次采购上限改成20箱。 | clarify 询问 quantity_unit | — |
| dev-pt10-001 | PT-10 | 取消本次额外采购数量上限，恢复为无额外上限。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": null, "plan_id": "$current_plan_id"} | — |
| dev-pt01-011 | PT-01 | 假设本次最多采购35件，先算算效果。 | evaluate_plan {"max_purchase_qty": 35, "plan_id": "$current_plan_id"} | — |
| dev-pt01-012 | PT-01 | 如果本次最多补货7件，会发生什么变化？ | evaluate_plan {"max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| dev-pt01-013 | PT-01 | 如果本次采购上限设为999999件，结果怎样？ | evaluate_plan {"max_purchase_qty": 999999, "plan_id": "$current_plan_id"} | — |
| dev-pt01-014 | PT-01 | 假设这一单完全不补货，即上限为0件，算一下。 | evaluate_plan {"max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt01-015 | PT-01 | 试算本次采购上限3件的方案。 | evaluate_plan {"max_purchase_qty": 3, "plan_id": "$current_plan_id"} | — |
| dev-pt01-016 | PT-01 | 仅做推演：本次最多买25件。 | evaluate_plan {"max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt01-017 | PT-01 | 评估本次最多采购60件的可能结果，先不落实。 | evaluate_plan {"max_purchase_qty": 60, "plan_id": "$current_plan_id"} | — |
| dev-pt01-018 | PT-01 | 看看本次采购数量封顶15件的模拟结果。 | evaluate_plan {"max_purchase_qty": 15, "plan_id": "$current_plan_id"} | — |
| dev-pt01-019 | PT-01 | 先做沙盘推演，本次采购限额是45件。 | evaluate_plan {"max_purchase_qty": 45, "plan_id": "$current_plan_id"} | — |
| dev-pt01-020 | PT-01 | 本次若只允许买18件，计算候选方案供我参考。 | evaluate_plan {"max_purchase_qty": 18, "plan_id": "$current_plan_id"} | — |
| dev-pt01-021 | PT-01 | 如果本次上限为两百零五件，试算结果如何？ | evaluate_plan {"max_purchase_qty": 205, "plan_id": "$current_plan_id"} | — |
| dev-pt01-022 | PT-01 | 只试算本次采购上限一千零一件。 | evaluate_plan {"max_purchase_qty": 1001, "plan_id": "$current_plan_id"} | — |
| dev-pt01-023 | PT-01 | 假设本次采购上限是一万零三件。 | evaluate_plan {"max_purchase_qty": 10003, "plan_id": "$current_plan_id"} | — |
| dev-pt01-024 | PT-01 | 只试算本次最多采购九十九件。 | evaluate_plan {"max_purchase_qty": 99, "plan_id": "$current_plan_id"} | — |
| dev-pt01-025 | PT-01 | 如果本次最多采购十一件，会怎样？ | evaluate_plan {"max_purchase_qty": 11, "plan_id": "$current_plan_id"} | — |
| dev-pt01-026 | PT-01 | 库存数字先忽略；试算本次上限25件，不是旧的10件。 | evaluate_plan {"max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt01-027 | PT-01 | 试算本次最多买8件，店员刚才提过50件但那不是我的要求。 | evaluate_plan {"max_purchase_qty": 8, "plan_id": "$current_plan_id"} | — |
| dev-pt01-028 | PT-01 | 前一个建议是40件，现在仅试算上限12件。 | evaluate_plan {"max_purchase_qty": 12, "plan_id": "$current_plan_id"} | — |
| dev-pt01-029 | PT-01 | 只模拟本次上限65件；数字80件只是旧笔记。 | evaluate_plan {"max_purchase_qty": 65, "plan_id": "$current_plan_id"} | — |
| dev-pt01-030 | PT-01 | 上限先试算为16件，而不是我误写的61件。 | evaluate_plan {"max_purchase_qty": 16, "plan_id": "$current_plan_id"} | — |
| dev-pt01-031 | PT-01 | What if the purchase cap for this mission is 17 units? Do not change the plan. | evaluate_plan {"max_purchase_qty": 17, "plan_id": "$current_plan_id"} | — |
| dev-pt01-032 | PT-01 | Simulate a maximum purchase of 23 units for this request only. | evaluate_plan {"max_purchase_qty": 23, "plan_id": "$current_plan_id"} | — |
| dev-pt01-033 | PT-01 | Evaluate the current plan with a purchase cap of 0 units, read only. | evaluate_plan {"max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt01-034 | PT-01 | For this mission, hypothetically cap the order at 125 units. | evaluate_plan {"max_purchase_qty": 125, "plan_id": "$current_plan_id"} | — |
| dev-pt01-035 | PT-01 | 只做what-if，本次purchase cap设为42件。 | evaluate_plan {"max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| dev-pt01-036 | PT-01 | 当前上限20件，如果提高5件，试算一下。 | evaluate_plan {"max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt01-037 | PT-01 | 以当前20件上限为基础，假设减去3件。 | evaluate_plan {"max_purchase_qty": 17, "plan_id": "$current_plan_id"} | — |
| dev-pt01-038 | PT-01 | 当前20件的上限如果翻倍，仅试算结果。 | evaluate_plan {"max_purchase_qty": 40, "plan_id": "$current_plan_id"} | — |
| dev-pt01-039 | PT-01 | 只试算当前20件上限的一半。 | evaluate_plan {"max_purchase_qty": 10, "plan_id": "$current_plan_id"} | — |
| dev-pt01-040 | PT-01 | 假设现有20件上限再增加12件，结果如何？ | evaluate_plan {"max_purchase_qty": 32, "plan_id": "$current_plan_id"} | — |
| dev-pt02-011 | PT-02 | 将当前方案本次采购上限修改为35件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 35, "plan_id": "$current_plan_id"} | — |
| dev-pt02-012 | PT-02 | 本次采购上限正式改成7件，请生成新方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| dev-pt02-013 | PT-02 | 调整本次最高采购数量为999999件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 999999, "plan_id": "$current_plan_id"} | — |
| dev-pt02-014 | PT-02 | 这次先不补货，请把采购上限改成0件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt02-015 | PT-02 | 本次数量上限请改为3件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 3, "plan_id": "$current_plan_id"} | — |
| dev-pt02-016 | PT-02 | 不沿用旧的50件要求；请把本次上限改为12件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 12, "plan_id": "$current_plan_id"} | — |
| dev-pt02-017 | PT-02 | 别再考虑旧方案了，修改当前方案的上限为25件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt02-018 | PT-02 | 上次的修改取消讨论；这一次明确修改上限为60件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 60, "plan_id": "$current_plan_id"} | — |
| dev-pt02-019 | PT-02 | 我不改旧方案，只把当前方案上限调整为9件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 9, "plan_id": "$current_plan_id"} | — |
| dev-pt02-020 | PT-02 | 试算阶段结束，正式将本次上限修改成45件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 45, "plan_id": "$current_plan_id"} | — |
| dev-pt02-021 | PT-02 | 正式修改本次上限为28件，不是旧记录里的82件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 28, "plan_id": "$current_plan_id"} | — |
| dev-pt02-022 | PT-02 | 请把当前采购上限改成13件，30件是误写。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 13, "plan_id": "$current_plan_id"} | — |
| dev-pt02-023 | PT-02 | 将本次上限改为55件；那条5件的建议作废。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 55, "plan_id": "$current_plan_id"} | — |
| dev-pt02-024 | PT-02 | 本次上限改成21件，不采纳供应商建议的40件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 21, "plan_id": "$current_plan_id"} | — |
| dev-pt02-025 | PT-02 | 修改本次上限为6件；之前60件的数字不要使用。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 6, "plan_id": "$current_plan_id"} | — |
| dev-pt02-026 | PT-02 | 请把本次采购上限改为两百零五件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 205, "plan_id": "$current_plan_id"} | — |
| dev-pt02-027 | PT-02 | 将本次采购上限修改成一千零一件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 1001, "plan_id": "$current_plan_id"} | — |
| dev-pt02-028 | PT-02 | 本次采购数量上限调整为一万零三件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 10003, "plan_id": "$current_plan_id"} | — |
| dev-pt02-029 | PT-02 | 请将本次最多采购量改为九十九件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 99, "plan_id": "$current_plan_id"} | — |
| dev-pt02-030 | PT-02 | 把本次采购上限改为十一件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 11, "plan_id": "$current_plan_id"} | — |
| dev-pt02-031 | PT-02 | Change the current purchase cap to 17 units for this mission. | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 17, "plan_id": "$current_plan_id"} | — |
| dev-pt02-032 | PT-02 | Revise the current plan: maximum purchase quantity is 23 units. | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 23, "plan_id": "$current_plan_id"} | — |
| dev-pt02-033 | PT-02 | Please change this order's quantity cap to zero units. | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt02-034 | PT-02 | Set the purchase limit for the current plan to 125 units. | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 125, "plan_id": "$current_plan_id"} | — |
| dev-pt02-035 | PT-02 | 当前方案purchase cap请正式修改为42件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| dev-pt02-036 | PT-02 | 当前上限20件，请在这个基础上增加5件，修改本次方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt02-037 | PT-02 | 把当前20件上限减少3件，正式修订方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 17, "plan_id": "$current_plan_id"} | — |
| dev-pt02-038 | PT-02 | 将当前20件的采购上限翻倍，修改方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 40, "plan_id": "$current_plan_id"} | — |
| dev-pt02-039 | PT-02 | 请修改本次方案，把当前20件上限减半。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 10, "plan_id": "$current_plan_id"} | — |
| dev-pt02-040 | PT-02 | 现有上限20件，本次再增加12件，请按此修改。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 32, "plan_id": "$current_plan_id"} | — |
| dev-pt03-009 | PT-03 | 别修改当前方案；仅试算上限11件。 | evaluate_plan {"max_purchase_qty": 11, "plan_id": "$current_plan_id"} | — |
| dev-pt03-010 | PT-03 | 我不是要求改成25件，只想看看上限25件的试算结果。 | evaluate_plan {"max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt03-011 | PT-03 | 本次暂不正式修改，只看上限60件能带来什么变化。 | evaluate_plan {"max_purchase_qty": 60, "plan_id": "$current_plan_id"} | — |
| dev-pt03-012 | PT-03 | 上限35件先试算，当前方案保持原样。 | evaluate_plan {"max_purchase_qty": 35, "plan_id": "$current_plan_id"} | — |
| dev-pt03-013 | PT-03 | 不要把8件写入方案，先模拟本次上限8件。 | evaluate_plan {"max_purchase_qty": 8, "plan_id": "$current_plan_id"} | — |
| dev-pt03-014 | PT-03 | 只看看上限90件的计算结果，不生成正式修订。 | evaluate_plan {"max_purchase_qty": 90, "plan_id": "$current_plan_id"} | — |
| dev-pt03-015 | PT-03 | 刚才说改成30件，现在撤回修改；只试算上限15件。 | evaluate_plan {"max_purchase_qty": 15, "plan_id": "$current_plan_id"} | — |
| dev-pt03-016 | PT-03 | 不要执行我刚说的上限40件修改，改为只模拟上限12件。 | evaluate_plan {"max_purchase_qty": 12, "plan_id": "$current_plan_id"} | — |
| dev-pt03-017 | PT-03 | 正式修改先算了，仍请试算本次最多买6件。 | evaluate_plan {"max_purchase_qty": 6, "plan_id": "$current_plan_id"} | — |
| dev-pt03-018 | PT-03 | 本次不改了，但想看看上限100件的试算结果。 | evaluate_plan {"max_purchase_qty": 100, "plan_id": "$current_plan_id"} | — |
| dev-pt03-019 | PT-03 | 收回修改方案的要求；仅推演数量上限19件。 | evaluate_plan {"max_purchase_qty": 19, "plan_id": "$current_plan_id"} | — |
| dev-pt03-020 | PT-03 | 取消这次修改请求，不取消任务；继续只试算上限22件。 | evaluate_plan {"max_purchase_qty": 22, "plan_id": "$current_plan_id"} | — |
| dev-pt03-021 | PT-03 | 仅试算上限14件，不是41件，也不要修改。 | evaluate_plan {"max_purchase_qty": 14, "plan_id": "$current_plan_id"} | — |
| dev-pt03-022 | PT-03 | 上限试算选27件；72件并非我的要求，不改方案。 | evaluate_plan {"max_purchase_qty": 27, "plan_id": "$current_plan_id"} | — |
| dev-pt03-023 | PT-03 | 只模拟本次最多31件，13件是写错的数字。 | evaluate_plan {"max_purchase_qty": 31, "plan_id": "$current_plan_id"} | — |
| dev-pt03-024 | PT-03 | 先别修改，试算上限54件，而不是45件。 | evaluate_plan {"max_purchase_qty": 54, "plan_id": "$current_plan_id"} | — |
| dev-pt03-025 | PT-03 | 只看本次上限2件，别采用之前的20件，不要正式改。 | evaluate_plan {"max_purchase_qty": 2, "plan_id": "$current_plan_id"} | — |
| dev-pt03-026 | PT-03 | 同事说‘把上限改成20件’，我的要求是只试算上限10件。 | evaluate_plan {"max_purchase_qty": 10, "plan_id": "$current_plan_id"} | — |
| dev-pt03-027 | PT-03 | ‘正式修改上限为50件’是上一条草稿；现在仅试算上限18件。 | evaluate_plan {"max_purchase_qty": 18, "plan_id": "$current_plan_id"} | — |
| dev-pt03-028 | PT-03 | 请把‘上限改成25件’理解成假设例子，我只要试算25件。 | evaluate_plan {"max_purchase_qty": 25, "plan_id": "$current_plan_id"} | — |
| dev-pt03-029 | PT-03 | 不要执行引号里的‘改成80件’，仅模拟本次上限4件。 | evaluate_plan {"max_purchase_qty": 4, "plan_id": "$current_plan_id"} | — |
| dev-pt03-030 | PT-03 | 先试算上限40件；试算好也不要自动修改，我尚未确认。 | evaluate_plan {"max_purchase_qty": 40, "plan_id": "$current_plan_id"} | — |
| dev-pt04-009 | PT-04 | 请把这次采购上限降低到更保守的水平。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 12, "plan_id": "$current_plan_id"} | 把本次采购上限修改为12件。 |
| dev-pt04-010 | PT-04 | 本次采购上限需要放宽，请调整。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 35, "plan_id": "$current_plan_id"} | 把本次采购上限改为35件。 |
| dev-pt04-011 | PT-04 | 将当前方案的数量上限设成我刚想到的数。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 7, "plan_id": "$current_plan_id"} | 将本次采购上限修改为7件。 |
| dev-pt04-012 | PT-04 | 给本次采购定一个新的最高件数。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 0, "plan_id": "$current_plan_id"} | 把本次采购上限修改为0件。 |
| dev-pt04-013 | PT-04 | 把本次允许购买的最多件数重新设一下。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 99, "plan_id": "$current_plan_id"} | 请修改本次采购上限为99件。 |
| dev-pt04-014 | PT-04 | 本次上限别用现在这个值，帮我改一下。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 1000000, "plan_id": "$current_plan_id"} | 将本次上限修改为1000000件。 |
| dev-pt04-015 | PT-04 | 把本次上限改成刚好够我用的数量。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 15, "plan_id": "$current_plan_id"} | 我的意思是最多采购，修改上限为15件。 |
| dev-pt04-016 | PT-04 | 当前本次上限需要往上调一些。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 25, "plan_id": "$current_plan_id"} | 请在当前20件上限基础上增加5件并修改。 |
| dev-pt04-017 | PT-04 | 当前本次上限想往下改一点。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 10, "plan_id": "$current_plan_id"} | 请把当前20件上限减半并修改方案。 |
| dev-pt04-018 | PT-04 | 本次采购上限我想换一个整数。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 102, "plan_id": "$current_plan_id"} | 本次采购上限改为一百零二件。 |
| dev-pt04-019 | PT-04 | Please change the purchase cap, I haven't specified the quantity yet. | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 23, "plan_id": "$current_plan_id"} | Change the current cap to 23 units. |
| dev-pt04-020 | PT-04 | 只模拟本次限制采购数量的情况，上限还没选。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 13, "plan_id": "$current_plan_id"} | 只试算本次上限13件。 |
| dev-pt04-021 | PT-04 | 假设本次上限变小，算一下会怎样。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 0, "plan_id": "$current_plan_id"} | 仅试算本次上限0件。 |
| dev-pt04-022 | PT-04 | 只想试算不同的最高件数。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 1, "plan_id": "$current_plan_id"} | 仅试算本次最多采购1件。 |
| dev-pt04-023 | PT-04 | 先不改方案，试算本次采购封顶后的结果。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 37, "plan_id": "$current_plan_id"} | 只试算本次上限37件。 |
| dev-pt04-024 | PT-04 | 如果这次只能少买一些，先评估一下。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 66, "plan_id": "$current_plan_id"} | 假设本次采购上限为66件，仅试算。 |
| dev-pt04-025 | PT-04 | 只做假设试算，本次上限选另一个数。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 999999, "plan_id": "$current_plan_id"} | 只试算本次采购上限999999件。 |
| dev-pt04-026 | PT-04 | 本次上限暂不写入，只想换一个数量模拟。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 200, "plan_id": "$current_plan_id"} | 仅试算上限两百件。 |
| dev-pt04-027 | PT-04 | 如果当前20件上限有所增加，先试算一下。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 27, "plan_id": "$current_plan_id"} | 只试算当前20件上限增加7件的结果。 |
| dev-pt04-028 | PT-04 | 现在的20件上限如果减少一点呢？只试算。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 18, "plan_id": "$current_plan_id"} | 只试算当前20件上限减少2件。 |
| dev-pt04-029 | PT-04 | Simulate a new purchase cap, but ask me for the quantity first. | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 29, "plan_id": "$current_plan_id"} | Only simulate a cap of 29 units. |
| dev-pt04-030 | PT-04 | 请试算本次换成我选的那个上限。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 47, "plan_id": "$current_plan_id"} | 只试算本次上限47件，不是74件。 |
| dev-pt05-004 | PT-05 | 按刚刚唯一一次试算的数量上限，正式修改本次方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 35, "plan_id": "$current_plan_id"} | — |
| dev-pt05-005 | PT-05 | 前面零采购的试算就是我要的，请据此修改上限。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 0, "plan_id": "$current_plan_id"} | — |
| dev-pt05-006 | PT-05 | 两个试算中，请按第一种数量上限修改本次方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 12, "plan_id": "$current_plan_id"} | — |
| dev-pt05-007 | PT-05 | 两个试算中，请按后一个上限修改当前方案。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 55, "plan_id": "$current_plan_id"} | — |
| dev-pt05-008 | PT-05 | 两次试算数量相同，就按那个上限修改。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 18, "plan_id": "$current_plan_id"} | — |
| dev-pt05-009 | PT-05 | 刚修改过的上限再试算一次，正式方案保持原样。 | evaluate_plan {"max_purchase_qty": 60, "plan_id": "$current_plan_id"} | — |
| dev-pt05-010 | PT-05 | 刚才那两个方案，挑我说的那个上限修改。 | clarify 询问 history_reference | — |
| dev-pt05-011 | PT-05 | 按昨天告诉你的采购上限修改这次方案。 | clarify 询问 history_reference | — |
| dev-pt05-012 | PT-05 | 按之前提过的另一个上限修改。 | clarify 询问 history_reference | — |
| dev-pt06-004 | PT-06 | 撤回本轮修改采购上限的要求，原任务继续。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-005 | PT-06 | 这条改数量的请求作废，不要再处理。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-006 | PT-06 | 现在不需要调整上限了，保持现状。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-007 | PT-06 | 停止处理我的这次修改请求，但不要停掉补货任务。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-008 | PT-06 | 这次想改成50件的提议不算数，保留已经设好的20件。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-009 | PT-06 | 我不想把20件改成30件了，撤回当前请求。 | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt06-010 | PT-06 | Withdraw my current cap-change request; keep the mission and existing plan active. | no_action {"reason": "withdraw_current_request"} | — |
| dev-pt07-005 | PT-07 | 把本次采购上限改为-1件。 | clarify 询问 valid_quantity | — |
| dev-pt07-006 | PT-07 | 本次采购上限请修改成负三件。 | clarify 询问 valid_quantity | — |
| dev-pt07-007 | PT-07 | 将本次采购上限改为0.5件。 | clarify 询问 valid_quantity | — |
| dev-pt07-008 | PT-07 | 本次采购上限修改成3.14件。 | clarify 询问 valid_quantity | — |
| dev-pt07-009 | PT-07 | 请将本次采购上限改成一百零一万件。 | clarify 询问 valid_quantity | — |
| dev-pt07-010 | PT-07 | 把本次上限改成2000000件。 | clarify 询问 valid_quantity | — |
| dev-pt07-011 | PT-07 | 仅试算本次上限-8件。 | clarify 询问 valid_quantity | — |
| dev-pt07-012 | PT-07 | 假设本次采购上限为1000002件，试算一下。 | clarify 询问 valid_quantity | — |
| dev-pt07-013 | PT-07 | 本次不是最多买8件，是必须恰好采购8件。 | clarify 询问 quantity_semantics | — |
| dev-pt07-014 | PT-07 | 本次必须至少采购30件，我要的是最低数量，不是上限。 | clarify 询问 quantity_semantics | — |
| dev-pt07-015 | PT-07 | 采购数量必须等于45件，不能少一件；请按精确量修改。 | clarify 询问 quantity_semantics | — |
| dev-pt07-016 | PT-07 | 请把本次采购上限设置成布尔值true。 | clarify 询问 valid_quantity | — |
| dev-pt08-003 | PT-08 | 请总结上个月各门店的盈利情况。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-004 | PT-08 | 帮我写本季度门店经营复盘报告。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-005 | PT-08 | 直接取消已经发给供应商的采购订单。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-006 | PT-08 | 请把牛奶的销售单价改成18元。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-007 | PT-08 | 给供应商发邮件，谈一下采购折扣。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-008 | PT-08 | 为这家店制定未来三个月的营销方案。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-009 | PT-08 | 删除上一周的库存流水记录。 | handoff {"reason": "unsupported_request"} | — |
| dev-pt08-010 | PT-08 | Approve the purchase plan and submit the order to the supplier now. | handoff {"reason": "unsupported_request"} | — |
| dev-pt09-002 | PT-09 | 本次采购上限修改为3盒。 | clarify 询问 quantity_unit | — |
| dev-pt09-003 | PT-09 | 把本次最多采购数量改为8包。 | clarify 询问 quantity_unit | — |
| dev-pt09-004 | PT-09 | 本次采购数量最多买2托盘，请修改。 | clarify 询问 quantity_unit | — |
| dev-pt09-005 | PT-09 | 把本次采购上限调整为6袋。 | clarify 询问 quantity_unit | — |
| dev-pt09-006 | PT-09 | 本次以10组为采购上限，调整方案。 | clarify 询问 quantity_unit | — |
| dev-pt09-007 | PT-09 | 只试算本次最多采购5箱，未确定每箱规格。 | clarify 询问 quantity_unit | — |
| dev-pt09-008 | PT-09 | Change this purchase cap to 4 cartons; I haven't specified units per carton. | clarify 询问 quantity_unit | — |
| dev-pt10-002 | PT-10 | 请修改本次方案，移除现有20件数量上限，不再加额外件数限制。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": null, "plan_id": "$current_plan_id"} | — |
| dev-pt10-003 | PT-10 | 不是把上限改为0件，而是取消本次额外的数量上限。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": null, "plan_id": "$current_plan_id"} | — |
| dev-pt10-004 | PT-10 | Remove the extra purchase quantity limit from the current plan; do not set it to zero. | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": null, "plan_id": "$current_plan_id"} | — |

## 逐例语义依据与重放前提

### dev-pt01-001

来源家族：`cap20-intent-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。“如果”明确假设；绑定当前方案，只传上限20，不生成正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-002

来源家族：`zero-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户明确把本次采购上限设为0做假设；0不可替换为无额外上限。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-003

来源家族：`one-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。有效下边界正整数1，保持试算只读。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-004

来源家族：`max-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。1000000是合法上界；实际建议采购量可以远小于上限。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-005

来源家族：`chinese-numeral-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。把中文数字二十绑定为整数20；不改变假设意图。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-006

来源家族：`noncandidate-cap-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。35作为上限合法，不要求当前候选必须有35件，更不能强制购买35件。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-007

来源家族：`trial-verb-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。“试算”足以限定只读，不能因出现“方案”就选择修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-008

来源家族：`keep-plan-simulate`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。明确保持正式方案，模拟上限30；业务实际采购量由工具决定。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-009

来源家族：`existing-cap-hypothesis`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。当前上限20与试算上限40不同；只能传40试算，当前约束保留20。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-010

来源家族：`change-word-hypothesis`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。虽然出现“调成”，外层假设语义仍要求evaluate_plan。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-001

来源家族：`cap20-intent-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。明确修改上限20，绑定当前Plan与可见Mission版本；只产生待确认方案。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-002

来源家族：`zero-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。明确正式上限0；不等于取消额外上限，也不取消Mission。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-003

来源家族：`one-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。正式修改，严格整数1，保留当前版本参数。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-004

来源家族：`max-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。合法上界修订；工具可以返回小于1000000件的建议采购量。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-005

来源家族：`chinese-numeral-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。中文二十五对应25；不是精确购买25件。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-006

来源家族：`current-versus-historical-plan`；fixture：`replenishment_revised`；当前版本 recipe：3。
复核：agent_reviewed / codex。显式选择当前方案，不绑定历史Plan；版本取当前可见状态。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-007

来源家族：`polite-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。礼貌表达仍是明确修订意图，数量15完整，不应多问。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-008

来源家族：`existing-cap-revision`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。新上限是10，不能复制旧约束20；与只读修改假设成对。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-009

来源家族：`self-correction-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。同一消息中后面的明确纠正覆盖前面的40；只发出一次修订。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-010

来源家族：`current-version-binding`；fixture：`replenishment_revised`；当前版本 recipe：7。
复核：agent_reviewed / codex。版本recipe为7；参数必须从当前上下文取7，不能默认1。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-001

来源家族：`cap20-intent-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。否定修改且明确只看试算；不能请求revise_plan。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-002

来源家族：`zero-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。不保存优先，数量0保留，不能把0当成空值。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-003

来源家族：`negated-prior-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效请求是试算10；不能沿用前文的修订30。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-004

来源家族：`withdraw-then-evaluate`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。撤回的是修订动作，后面仍有有效试算请求，不能简单no_action。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-005

来源家族：`keep-plan-simulate`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。“照旧”保留正式方案，模拟40只调用试算。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-006

来源家族：`max-cap-pair`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。中文一百万是合法上界；否定正式修改，不应误判超范围。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-007

来源家族：`negated-quantity-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。80处于被否定的修订片段；有效试算参数为八即8。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-008

来源家族：`quantity-correction-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。被否定的30不能覆盖肯定的20；末尾再次明确只读。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-001

来源家族：`missing-lower-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。方向不能决定具体上限；先问数量，完整回复后才修订20。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-002

来源家族：`missing-lower-hypothesis`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。假设意图明确但数量缺失；回复保留试算，不应升级为正式修订。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-003

来源家族：`missing-higher-revision`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。已有上限20，不能从“一点”推导固定增幅；先问目标上限，用户完整回复50后修订。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-004

来源家族：`missing-suitable-cap`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。本轮不训练自主经营决策；不能猜“合适”的数，用户给30后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-005

来源家族：`missing-trial-cap-zero`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。“另一档”没有唯一数值；回复为0后保留严格零值，不当作null。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-006

来源家族：`missing-revision-cap-one`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。修改意图有，数量没有；回复给出1后不需要再次澄清。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-007

来源家族：`missing-acceptable-cap`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可接受数量不在可见状态里；先问必要数量，再按80生成新方案。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-008

来源家族：`missing-hypothetical-cap-max`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。不能自行选择上限；明确回复给合法上界后做试算。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-001

来源家族：`unique-prior-evaluation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。只有一次先前试算20，指代唯一；语义金标为修订20，来源规则是否接受另测。
历史：只试算本次上限20件。 → evaluate_plan，上限 20；对象 $current_plan_id。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：当前消息没有重复数量；按原计划将跨消息来源支持单列，真实网关接受情况在E3/E4验证。

### dev-pt05-002

来源家族：`ambiguous-prior-evaluations`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。历史有20与40两个试算，消息没有指明选择哪个；必须问清指代，不能猜最近数。
历史：只试算本次上限20件。 → evaluate_plan，上限 20；对象 $current_plan_id。
历史：再只试算本次上限40件。 → evaluate_plan，上限 40；对象 $current_plan_id。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt05-003

来源家族：`missing-prior-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史为空，先问所指上限；不能编造上一轮数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt06-001

来源家族：`withdraw-current-request`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。没有剩余试算或修改请求，结束当前请求即可，不取消Mission。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-002

来源家族：`keep-existing-cap-on-withdrawal`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。已有上限20保留；撤回请求不是清除上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-003

来源家族：`withdraw-new-change-keep-old`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。明确保留已成功修改的20，只撤回当前调40请求；不能回滚旧修改。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt07-001

来源家族：`negative-cap`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。负数不符合数量契约，应说明需要0到1000000的整数，不截成0。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-002

来源家族：`fractional-cap`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。件数上限必须为整数，不能静默取整到20或21。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-003

来源家族：`over-max-cap`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。比合法上界大1，需澄清合法数量，不能截断成1000000。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-004

来源家族：`exact-versus-cap`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户明确要求精确量；当前工具只能表达上限，需确认是否接受上限语义，不能偷偷改成上限20。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt08-001

来源家族：`unsupported-quarterly-report`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。开放式报告超出数量上限工具决策范围，转交且本轮不修改业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-002

来源家族：`unsupported-purchase-execution`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。审批下单超出学生动作集；转交不等于完成采购或获得授权。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt09-001

来源家族：`unknown-package-conversion`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。上下文单位为件，未提供每箱件数；问换算依据，不能把20箱绑定20件。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt10-001

来源家族：`remove-cap-versus-zero`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。已有上限20；明确取消对应null，不能写0，也不能改变现金政策。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已有直接revision API的null案例；Agent工具网关与fixture的实际行为尚未验证，E1只发布规格候选。

### dev-pt01-011

来源家族：`counterfactual-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为35件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-012

来源家族：`counterfactual-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为7件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-013

来源家族：`counterfactual-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为999999件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-014

来源家族：`counterfactual-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为0件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-015

来源家族：`counterfactual-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为3件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-016

来源家族：`trial-verb-paraphrases`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为25件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-017

来源家族：`trial-verb-paraphrases`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为60件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-018

来源家族：`trial-verb-paraphrases`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为15件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-019

来源家族：`trial-verb-paraphrases`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为45件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-020

来源家族：`trial-verb-paraphrases`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为18件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-021

来源家族：`written-numeral-evaluation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为205件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-022

来源家族：`written-numeral-evaluation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为1001件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-023

来源家族：`written-numeral-evaluation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为10003件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-024

来源家族：`written-numeral-evaluation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为99件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-025

来源家族：`written-numeral-evaluation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为11件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-026

来源家族：`evaluation-numeric-distractors`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为25件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-027

来源家族：`evaluation-numeric-distractors`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为8件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-028

来源家族：`evaluation-numeric-distractors`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为12件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-029

来源家族：`evaluation-numeric-distractors`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为65件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-030

来源家族：`evaluation-numeric-distractors`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为16件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-031

来源家族：`english-hypothetical-request`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为17件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-032

来源家族：`english-hypothetical-request`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为23件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-033

来源家族：`english-hypothetical-request`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为0件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-034

来源家族：`english-hypothetical-request`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为125件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-035

来源家族：`english-hypothetical-request`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。用户只要求假设或试算，目标上限为42件；其他数字/措辞不授权正式修订。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-036

来源家族：`relative-evaluation-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。可见当前上限20，明确的相对运算得到25；仅试算，不写入。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-037

来源家族：`relative-evaluation-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。可见当前上限20，明确的相对运算得到17；仅试算，不写入。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-038

来源家族：`relative-evaluation-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。可见当前上限20，明确的相对运算得到40；仅试算，不写入。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-039

来源家族：`relative-evaluation-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。可见当前上限20，明确的相对运算得到10；仅试算，不写入。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt01-040

来源家族：`relative-evaluation-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。可见当前上限20，明确的相对运算得到32；仅试算，不写入。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-011

来源家族：`absolute-cap-revision-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限35；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-012

来源家族：`absolute-cap-revision-values`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限7；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-013

来源家族：`absolute-cap-revision-values`；fixture：`replenishment_revised`；当前版本 recipe：3。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限999999；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-014

来源家族：`absolute-cap-revision-values`；fixture：`replenishment_revised`；当前版本 recipe：7。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限0；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-015

来源家族：`absolute-cap-revision-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限3；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-016

来源家族：`revision-with-old-request-negation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限12；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-017

来源家族：`revision-with-old-request-negation`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限25；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-018

来源家族：`revision-with-old-request-negation`；fixture：`replenishment_revised`；当前版本 recipe：3。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限60；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-019

来源家族：`revision-with-old-request-negation`；fixture：`replenishment_revised`；当前版本 recipe：7。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限9；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-020

来源家族：`revision-with-old-request-negation`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限45；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-021

来源家族：`revision-numeric-distractors`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限28；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-022

来源家族：`revision-numeric-distractors`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限13；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-023

来源家族：`revision-numeric-distractors`；fixture：`replenishment_revised`；当前版本 recipe：3。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限55；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-024

来源家族：`revision-numeric-distractors`；fixture：`replenishment_revised`；当前版本 recipe：7。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限21；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-025

来源家族：`revision-numeric-distractors`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限6；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-026

来源家族：`written-numeral-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限205；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-027

来源家族：`written-numeral-revision`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限1001；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-028

来源家族：`written-numeral-revision`；fixture：`replenishment_revised`；当前版本 recipe：3。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限10003；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-029

来源家族：`written-numeral-revision`；fixture：`replenishment_revised`；当前版本 recipe：7。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限99；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-030

来源家族：`written-numeral-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限11；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-031

来源家族：`english-explicit-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限17；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-032

来源家族：`english-explicit-revision`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限23；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-033

来源家族：`english-explicit-revision`；fixture：`replenishment_revised`；当前版本 recipe：3。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限0；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-034

来源家族：`english-explicit-revision`；fixture：`replenishment_revised`；当前版本 recipe：7。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限125；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-035

来源家族：`english-explicit-revision`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。最后有效要求明确修订当前方案，上限42；从上下文绑定当前ID/版本，不能被旧数量或否定旧请求干扰。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-036

来源家族：`relative-revision-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。当前上限20可见，相对修改结果唯一为25；不是将增量当绝对上限。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-037

来源家族：`relative-revision-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。当前上限20可见，相对修改结果唯一为17；不是将增量当绝对上限。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-038

来源家族：`relative-revision-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。当前上限20可见，相对修改结果唯一为40；不是将增量当绝对上限。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-039

来源家族：`relative-revision-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。当前上限20可见，相对修改结果唯一为10；不是将增量当绝对上限。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt02-040

来源家族：`relative-revision-from-visible-cap`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。当前上限20可见，相对修改结果唯一为32；不是将增量当绝对上限。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-009

来源家族：`read-only-negation-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限11；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-010

来源家族：`read-only-negation-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限25；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-011

来源家族：`read-only-negation-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限60；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-012

来源家族：`read-only-negation-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限35；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-013

来源家族：`read-only-negation-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限8；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-014

来源家族：`read-only-negation-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限90；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-015

来源家族：`revision-withdrawn-trial-remains`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限15；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-016

来源家族：`revision-withdrawn-trial-remains`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限12；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-017

来源家族：`revision-withdrawn-trial-remains`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限6；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-018

来源家族：`revision-withdrawn-trial-remains`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限100；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-019

来源家族：`revision-withdrawn-trial-remains`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限19；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-020

来源家族：`revision-withdrawn-trial-remains`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限22；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-021

来源家族：`negated-trailing-quantity`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限14；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-022

来源家族：`negated-trailing-quantity`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限27；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-023

来源家族：`negated-trailing-quantity`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限31；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-024

来源家族：`negated-trailing-quantity`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限54；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-025

来源家族：`negated-trailing-quantity`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限2；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-026

来源家族：`quoted-intent-versus-current-intent`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限10；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-027

来源家族：`quoted-intent-versus-current-intent`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限18；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-028

来源家族：`quoted-intent-versus-current-intent`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限25；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-029

来源家族：`quoted-intent-versus-current-intent`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限4；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt03-030

来源家族：`quoted-intent-versus-current-intent`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。当前保留的是只读试算，上限40；否定、撤回或引用中的修改不构成正式修订授权。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-009

来源家族：`missing-revision-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限12。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-010

来源家族：`missing-revision-target`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限35。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-011

来源家族：`missing-revision-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限7。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-012

来源家族：`missing-revision-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限0。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-013

来源家族：`missing-revision-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限99。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-014

来源家族：`missing-revision-target`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限1000000。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-015

来源家族：`missing-revision-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限15。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-016

来源家族：`missing-target-relative-or-written`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限25。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-017

来源家族：`missing-target-relative-or-written`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限10。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-018

来源家族：`missing-target-relative-or-written`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限102。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-019

来源家族：`missing-target-relative-or-written`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应revise_plan并绑定上限23。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-020

来源家族：`missing-trial-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限13。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-021

来源家族：`missing-trial-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限0。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-022

来源家族：`missing-trial-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限1。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-023

来源家族：`missing-trial-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限37。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-024

来源家族：`missing-trial-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限66。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-025

来源家族：`missing-trial-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限999999。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-026

来源家族：`missing-trial-target`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限200。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-027

来源家族：`missing-trial-relative-or-corrected`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限27。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-028

来源家族：`missing-trial-relative-or-corrected`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限18。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-029

来源家族：`missing-trial-relative-or-corrected`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限29。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt04-030

来源家族：`missing-trial-relative-or-corrected`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。首句没有唯一数值，必须先询问数量；完整回复后应evaluate_plan并绑定上限47。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-004

来源家族：`resolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史和明确序号/相同数值使目标唯一为35；绑定当前对象，不要求用户重复已知数。
历史：只试算本次采购上限35件。 → evaluate_plan，上限 35；对象 $current_plan_id。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-005

来源家族：`resolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史和明确序号/相同数值使目标唯一为0；绑定当前对象，不要求用户重复已知数。
历史：只试算本次采购上限0件。 → evaluate_plan，上限 0；对象 $current_plan_id。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-006

来源家族：`resolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史和明确序号/相同数值使目标唯一为12；绑定当前对象，不要求用户重复已知数。
历史：只试算本次采购上限12件。 → evaluate_plan，上限 12；对象 $current_plan_id。
历史：只试算本次采购上限40件。 → evaluate_plan，上限 40；对象 $current_plan_id。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-007

来源家族：`resolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史和明确序号/相同数值使目标唯一为55；绑定当前对象，不要求用户重复已知数。
历史：只试算本次采购上限7件。 → evaluate_plan，上限 7；对象 $current_plan_id。
历史：只试算本次采购上限55件。 → evaluate_plan，上限 55；对象 $current_plan_id。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-008

来源家族：`resolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史和明确序号/相同数值使目标唯一为18；绑定当前对象，不要求用户重复已知数。
历史：只试算本次采购上限18件。 → evaluate_plan，上限 18；对象 $current_plan_id。
历史：只试算本次采购上限18件。 → evaluate_plan，上限 18；对象 $current_plan_id。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-009

来源家族：`resolvable-history-reference`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。可见历史和明确序号/相同数值使目标唯一为60；绑定当前对象，不要求用户重复已知数。
历史：请修改本次采购上限60件。 → revise_plan，上限 60；对象 $current_plan_id。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt05-010

来源家族：`unresolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史不能唯一确定所指目标；询问具体数量或候选，不猜最近值或不可见的昨天对话。
历史：只试算本次采购上限9件。 → evaluate_plan，上限 9；对象 $current_plan_id。
历史：只试算本次采购上限24件。 → evaluate_plan，上限 24；对象 $current_plan_id。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt05-011

来源家族：`unresolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史不能唯一确定所指目标；询问具体数量或候选，不猜最近值或不可见的昨天对话。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt05-012

来源家族：`unresolvable-history-reference`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。可见历史不能唯一确定所指目标；询问具体数量或候选，不猜最近值或不可见的昨天对话。
历史：只试算本次采购上限30件。 → evaluate_plan，上限 30；对象 $current_plan_id。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt06-004

来源家族：`withdraw-request-preserve-mission`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-005

来源家族：`withdraw-request-preserve-mission`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-006

来源家族：`withdraw-request-preserve-mission`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-007

来源家族：`withdraw-request-preserve-mission`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-008

来源家族：`withdraw-request-preserve-mission`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-009

来源家族：`withdraw-request-preserve-mission`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt06-010

来源家族：`withdraw-request-preserve-mission`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。明确撤回本请求而保留Mission及既有方案；不能继续修改，也不能将撤回当取消数量上限。
成功谓词：request_ended、mission_not_cancelled、no_business_mutation。

### dev-pt07-005

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-006

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-007

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-008

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-009

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-010

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-011

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-012

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-013

来源家族：`unsupported-exact-or-lower-bound`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-014

来源家族：`unsupported-exact-or-lower-bound`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-015

来源家族：`unsupported-exact-or-lower-bound`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt07-016

来源家族：`illegal-cap-values`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。输入不满足有效数量上限契约；应明确询问合法整数或可接受的上限语义，不能截断、取整或偷换下限/精确量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt08-003

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-004

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-005

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-006

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-007

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-008

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-009

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt08-010

来源家族：`outside-cap-policy-scope`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。请求不属于当前受限数量上限动作集，应转交通用路径，本轮不擅自操作业务。
成功谓词：handoff_recorded、no_business_mutation。

### dev-pt09-002

来源家族：`unknown-package-size`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt09-003

来源家族：`unknown-package-size`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt09-004

来源家族：`unknown-package-size`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt09-005

来源家族：`unknown-package-size`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt09-006

来源家族：`unknown-package-size`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt09-007

来源家族：`unknown-package-size`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt09-008

来源家族：`unknown-package-size`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / codex。工具单位是件，用户的包装单位没有换算依据；应询问每包装件数，不能直接绑定包装数量。
成功谓词：clarification_relevant、no_business_mutation。

### dev-pt10-002

来源家族：`explicit-unbounded-versus-zero`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。现有上限20，明确移除额外上限应传null；0代表禁止采购，与本要求不同。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt10-003

来源家族：`explicit-unbounded-versus-zero`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。现有上限20，明确移除额外上限应传null；0代表禁止采购，与本要求不同。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。

### dev-pt10-004

来源家族：`explicit-unbounded-versus-zero`；fixture：`replenishment_capped`；当前版本 recipe：2。
复核：agent_reviewed / codex。现有上限20，明确移除额外上限应传null；0代表禁止采购，与本要求不同。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
