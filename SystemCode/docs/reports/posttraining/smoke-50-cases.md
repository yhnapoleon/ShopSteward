# smoke 案例清单

共 50 个 episode，58 个决策目标。

本清单包含评测金标，不能作为模型输入。规格复核不等于真实工具执行或模型成绩。
Agent 复核：50；人工复核：0；执行验证：0。

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
