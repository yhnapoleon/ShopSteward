# Dev-v1 代表性失败分析

逐例由Codex核对原始输出与冻结金标，非人工复核。下列42条解释覆盖40个不同episode；同一episode跨模式不会当多个独立案例。

## dev-pt07-011 · decision/B1

请求：仅试算本次上限-8件。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "valid_quantity"}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 8}}]

将-8中的负号丢失，直接试算+8；数量不合法本应先澄清。此例期望动作不是工具，故不进入151个完整参数分母。

## dev-pt07-014 · decision/B1

请求：本次必须至少采购30件，我要的是最低数量，不是上限。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "quantity_semantics"}]
实际：[{"name": "handoff", "arguments": {"reason": "unsupported_request"}}]

将最低采购量请求转交。冻结契约要求先澄清是否接受上限语义；handoff避免了错误修改，但仍不满足本单答案路由标准。

## dev-pt04-019 · execution/B1

请求：Please change the purchase cap, I haven't specified the quantity yet.
脚本回复：Change the current cap to 23 units.

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"}, {"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 23, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请提供要设置的采购数量上限（0–1000000件的整数）；如需取消额外上限，请明确说“取消上限”。"}}, {"name": "clarify", "arguments": {"question": "当前采购数量单位是“件”。请确认将采购上限设置为23件，还是“units”代表其他单位？"}}]

收到英文23 units后再次询问单位，没有执行修订。decision模式同例成功；execution重新调用时失败，显示单次调用和上下文差异下的行为波动。

## dev-pt02-006 · decision/B0

请求：旧方案我不改了；请把当前方案的本次采购上限改成30件。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 30, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "no_action", "arguments": {"reason": "withdraw_current_request"}}]

把否定旧方案扩大为撤回整个请求，忽略后半句对当前方案的明确修改。

## dev-pt03-008 · decision/B0

请求：只看本次上限20件的试算，不是30件，也不要修改。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 20}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 30}}]

取最后出现但被否定的30，而非有效目标20；动作对，完整参数错。

## dev-pt05-001 · decision/B0

请求：按刚才试算的上限修改本次方案。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 20, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

只有一次20件历史试算，仍重复询问。可见历史已充分，问题来自规则没有解析历史。

## dev-pt01-016 · execution/B0

请求：仅做推演：本次最多买25件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 25}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 25, "expected_mission_version": 1}}]

未识别“仅做推演”，选择修订25；真实网关接受并修改测试方案，不能因HTTP成功计任务成功。

## dev-pt01-017 · execution/B0

请求：评估本次最多采购60件的可能结果，先不落实。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 60}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 60, "expected_mission_version": 1}}]

“评估、先不落实”仍被判修订60，测试方案发生非预期变化；关键词检查没有覆盖该否定表达。

## dev-pt01-019 · execution/B0

请求：先做沙盘推演，本次采购限额是45件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 45}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 45, "expected_mission_version": 1}}]

推演45被误选修订；后端EXPLICIT_REVISION_REQUIRED拒绝，这是阻止模型错误，不是阻止正确语义。

## dev-pt01-020 · execution/B0

请求：本次若只允许买18件，计算候选方案供我参考。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 18}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 18, "expected_mission_version": 1}}]

把“若只允许、供参考”识别为修订；后端拒绝，模型动作仍判错。

## dev-pt01-035 · execution/B0

请求：只做what-if，本次purchase cap设为42件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 42}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 42, "expected_mission_version": 1}}]

混合语言what-if没有命中规则的假设词；误修订42被后端拒绝。

## dev-pt01-026 · decision/B0

请求：库存数字先忽略；试算本次上限25件，不是旧的10件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 25}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 10}}]

将旧记录10当作目标，忽略当前明确的25；需在数字之外辨认其语义角色。

## dev-pt01-027 · decision/B0

请求：试算本次最多买8件，店员刚才提过50件但那不是我的要求。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 8}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 50}}]

采用店员提议50而不是用户的8，未辨别转述与当前选择。

## dev-pt01-030 · decision/B0

请求：上限先试算为16件，而不是我误写的61件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 16}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 61}}]

采用误写的61，未处理纠正关系；正确上限16。

## dev-pt01-031 · decision/B0

请求：What if the purchase cap for this mission is 17 units? Do not change the plan.

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 17}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

数字提取仅支持“件”，无法使用已明确的17 units，产生多余澄清。

## dev-pt01-036 · decision/B0

请求：当前上限20件，如果提高5件，试算一下。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 25}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 5}}]

将增加量5直接当上限；可见当前20，加5应为25。

## dev-pt01-037 · decision/B0

请求：以当前20件上限为基础，假设减去3件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 17}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 3}}]

将减少量3当上限，而不是20减3得到17。

## dev-pt01-038 · decision/B0

请求：当前20件的上限如果翻倍，仅试算结果。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 40}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 20}}]

翻倍仍返回20，缺少相对数量运算，目标应40。

## dev-pt01-039 · decision/B0

请求：只试算当前20件上限的一半。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 10}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 20}}]

一半仍返回20，目标应10。

## dev-pt02-018 · decision/B0

请求：上次的修改取消讨论；这一次明确修改上限为60件。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 60, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": null, "expected_mission_version": 3}}]

“取消讨论”与后文“上限”触发过宽的取消上限规则，错误传null而非60。

## dev-pt02-020 · decision/B0

请求：试算阶段结束，正式将本次上限修改成45件。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 45, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 45}}]

仅看到前文“试算”，忽略“阶段结束、正式修改”，未以最后有效意图为准。

## dev-pt02-021 · decision/B0

请求：正式修改本次上限为28件，不是旧记录里的82件。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 28, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 82, "expected_mission_version": 1}}]

取被否定的旧值82，不取明确修订值28。

## dev-pt02-024 · decision/B0

请求：本次上限改成21件，不采纳供应商建议的40件。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 21, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 40, "expected_mission_version": 7}}]

绑定当前版本7正确，但采用供应商建议40而非21；正确ID/版本不能抵消数量错误。

## dev-pt02-033 · decision/B0

请求：Please change this order's quantity cap to zero units.

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 0, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

未解析英文zero units，重复问数量；语义是合法的上限0。

## dev-pt02-040 · decision/B0

请求：现有上限20件，本次再增加12件，请按此修改。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 32, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 12, "expected_mission_version": 2}}]

将增量12当绝对上限，应以当前20计算32。

## dev-pt03-019 · execution/B0

请求：收回修改方案的要求；仅推演数量上限19件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 19}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 19, "expected_mission_version": 1}}]

撤回修改但保留推演19被误修订且被网关接受，真实测试方案发生变化。

## dev-pt03-020 · execution/B0

请求：取消这次修改请求，不取消任务；继续只试算上限22件。

预期：[{"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 22}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": null, "expected_mission_version": 1}}]

撤回本请求被解释成取消数量上限，写入null；有效要求实际是只试算22。

## dev-pt04-015 · decision/B0

请求：把本次上限改成刚好够我用的数量。
脚本回复：我的意思是最多采购，修改上限为15件。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"}, {"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 15, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "当前工具只能设置采购数量上限，您是否接受最多采购的上限含义？"}}]

只确认上限含义，没有询问缺失件数；复核失败，不发送第二步15件答案。

## dev-pt04-016 · decision/B0

请求：当前本次上限需要往上调一些。
脚本回复：请在当前20件上限基础上增加5件并修改。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"}, {"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 25, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}, {"name": "revise_plan", "arguments": {"max_purchase_qty": 5, "expected_mission_version": 2}}]

第一步问对，第二步把增加5件当目标5，澄清成功不能代表全任务成功。

## dev-pt04-019 · decision/B0

请求：Please change the purchase cap, I haven't specified the quantity yet.
脚本回复：Change the current cap to 23 units.

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"}, {"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 23, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}, {"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

第一步问对，收到23 units仍问相同问题，违反最多一次澄清流程。

## dev-pt04-027 · decision/B0

请求：如果当前20件上限有所增加，先试算一下。
脚本回复：只试算当前20件上限增加7件的结果。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"}, {"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 27}, "clarification_slot": null}]
实际：[{"name": "evaluate_plan", "arguments": {"max_purchase_qty": 20}}]

把已知旧上限20当新目标，尚未给增量却直接执行；不能继续注入脚本答案帮助其完成。

## dev-pt04-030 · decision/B0

请求：请试算本次换成我选的那个上限。
脚本回复：只试算本次上限47件，不是74件。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "max_purchase_qty"}, {"allowed_actions": ["evaluate_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 47}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}, {"name": "evaluate_plan", "arguments": {"max_purchase_qty": 74}}]

补充答复中47是有效目标，74被否定，规则仍取74。

## dev-pt05-006 · decision/B0

请求：两个试算中，请按第一种数量上限修改本次方案。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 12, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

历史有12和40，第一种的指代明确为12；规则不读历史而多余澄清。

## dev-pt05-008 · decision/B0

请求：两次试算数量相同，就按那个上限修改。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": 18, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

两次历史都是18，目标数值唯一，不能仅因为有两轮就视为歧义。

## dev-pt06-008 · decision/B0

请求：这次想改成50件的提议不算数，保留已经设好的20件。

预期：[{"allowed_actions": ["no_action"], "arguments": {"reason": "withdraw_current_request"}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 20, "expected_mission_version": 2}}]

撤回新提议并保留20，应no_action，规则却重新修订20。保留值不代表新写入要求。

## dev-pt06-009 · decision/B0

请求：我不想把20件改成30件了，撤回当前请求。

预期：[{"allowed_actions": ["no_action"], "arguments": {"reason": "withdraw_current_request"}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 30, "expected_mission_version": 2}}]

明确撤回当前调30请求，规则仍修订30，撤回词序未覆盖。

## dev-pt07-006 · decision/B0

请求：本次采购上限请修改成负三件。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "valid_quantity"}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 3, "expected_mission_version": 1}}]

中文“负三件”被截取为三件，负号语义丢失，与B1的-8错误属同一补数方向。

## dev-pt07-014 · decision/B0

请求：本次必须至少采购30件，我要的是最低数量，不是上限。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "quantity_semantics"}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 30, "expected_mission_version": 1}}]

把最低30偷换成最高30，工具类型与参数虽合法，但无法表达原要求。

## dev-pt07-015 · decision/B0

请求：采购数量必须等于45件，不能少一件；请按精确量修改。

预期：[{"allowed_actions": ["clarify"], "arguments": {}, "clarification_slot": "quantity_semantics"}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 1, "expected_mission_version": 1}}]

精确45请求被错误转换成修订1，既丢失精确语义又提取“不能少一件”的干扰数字。

## dev-pt08-006 · decision/B0

请求：请把牛奶的销售单价改成18元。

预期：[{"allowed_actions": ["handoff"], "arguments": {"reason": "unsupported_request"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

改售价属于范围外，不应询问采购上限；缺数字不是所有请求的统一解释。

## dev-pt08-007 · decision/B0

请求：给供应商发邮件，谈一下采购折扣。

预期：[{"allowed_actions": ["handoff"], "arguments": {"reason": "unsupported_request"}, "clarification_slot": null}]
实际：[{"name": "clarify", "arguments": {"question": "请明确本次采购上限是多少件；如果要修改，请完整说明修改要求和数量。"}}]

供应商邮件请求应handoff，规则只识别少数范围外关键词，错误澄清。

## dev-pt10-002 · decision/B0

请求：请修改本次方案，移除现有20件数量上限，不再加额外件数限制。

预期：[{"allowed_actions": ["revise_plan"], "arguments": {"plan_id": "$current_plan_id", "max_purchase_qty": null, "expected_mission_version": "$current_mission_version"}, "clarification_slot": null}]
实际：[{"name": "revise_plan", "arguments": {"max_purchase_qty": 20, "expected_mission_version": 2}}]

移除上限应null，规则未识别移除/不再限制，仍绑定现有20。
