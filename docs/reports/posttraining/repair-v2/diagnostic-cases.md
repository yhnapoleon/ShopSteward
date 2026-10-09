# smoke 案例清单

共 60 个 episode，72 个决策目标。

本清单包含评测金标，不能作为模型输入。规格复核不等于真实工具执行或模型成绩。
Agent 复核：60；人工复核：0；执行验证：0。

| ID | 类型 | 请求 | 预期动作/参数或澄清缺项 | 后续回复 |
|---|---|---|---|---|
| repair-negative_ascii-eval-7 | PT-07 | 仅试算本次上限-7件，不修改。 | clarify 询问 valid_quantity | — |
| repair-negative_chinese-eval-7 | PT-07 | 仅试算本次上限负七件，不修改。 | clarify 询问 valid_quantity | — |
| repair-positive-eval-7 | PT-01 | 仅试算本次上限7件，不修改。 | evaluate_plan {"max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| repair-negated_negative-eval-7 | PT-01 | 仅试算本次上限7件；此前说的负七件不是本次要求，不修改。 | evaluate_plan {"max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| repair-upper-eval-7 | PT-01 | 请试算本次采购数量上限，最多7件。 | evaluate_plan {"max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| repair-lower-eval-7 | PT-07 | 请试算本次采购量至少7件，我要最低数量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-exact-eval-7 | PT-07 | 请试算本次采购量必须等于7件，我要精确量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-followup_cn-eval-7 | PT-04 | 只试算本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 7, "plan_id": "$current_plan_id"} | 仅试算本次上限7件，不修改。 |
| repair-followup_en-eval-7 | PT-04 | 只试算本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 7, "plan_id": "$current_plan_id"} | Only evaluate this purchase cap at 7 units; do not change the plan. |
| repair-packaging-eval-7 | PT-07 | 仅试算本次上限7箱，不修改。 | clarify 询问 quantity_unit | — |
| repair-negative_ascii-revise-7 | PT-07 | 明确将本次上限修改为-7件。 | clarify 询问 valid_quantity | — |
| repair-negative_chinese-revise-7 | PT-07 | 明确将本次上限修改为负七件。 | clarify 询问 valid_quantity | — |
| repair-positive-revise-7 | PT-02 | 明确将本次上限修改为7件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| repair-negated_negative-revise-7 | PT-02 | 明确将本次上限修改为7件；此前说的负七件不是本次要求。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| repair-upper-revise-7 | PT-02 | 请修改本次采购数量上限，最多7件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 7, "plan_id": "$current_plan_id"} | — |
| repair-lower-revise-7 | PT-07 | 请修改本次采购量至少7件，我要最低数量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-exact-revise-7 | PT-07 | 请修改本次采购量必须等于7件，我要精确量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-followup_cn-revise-7 | PT-04 | 请修改本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 7, "plan_id": "$current_plan_id"} | 明确将本次上限修改为7件。 |
| repair-followup_en-revise-7 | PT-04 | 请修改本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 7, "plan_id": "$current_plan_id"} | Change the current purchase cap to 7 units. |
| repair-packaging-revise-7 | PT-07 | 明确将本次上限修改为7箱。 | clarify 询问 quantity_unit | — |
| repair-negative_ascii-eval-19 | PT-07 | 仅试算本次上限-19件，不修改。 | clarify 询问 valid_quantity | — |
| repair-negative_chinese-eval-19 | PT-07 | 仅试算本次上限负十九件，不修改。 | clarify 询问 valid_quantity | — |
| repair-positive-eval-19 | PT-01 | 仅试算本次上限19件，不修改。 | evaluate_plan {"max_purchase_qty": 19, "plan_id": "$current_plan_id"} | — |
| repair-negated_negative-eval-19 | PT-01 | 仅试算本次上限19件；此前说的负十九件不是本次要求，不修改。 | evaluate_plan {"max_purchase_qty": 19, "plan_id": "$current_plan_id"} | — |
| repair-upper-eval-19 | PT-01 | 请试算本次采购数量上限，最多19件。 | evaluate_plan {"max_purchase_qty": 19, "plan_id": "$current_plan_id"} | — |
| repair-lower-eval-19 | PT-07 | 请试算本次采购量至少19件，我要最低数量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-exact-eval-19 | PT-07 | 请试算本次采购量必须等于19件，我要精确量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-followup_cn-eval-19 | PT-04 | 只试算本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 19, "plan_id": "$current_plan_id"} | 仅试算本次上限19件，不修改。 |
| repair-followup_en-eval-19 | PT-04 | 只试算本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 19, "plan_id": "$current_plan_id"} | Only evaluate this purchase cap at 19 units; do not change the plan. |
| repair-packaging-eval-19 | PT-07 | 仅试算本次上限19箱，不修改。 | clarify 询问 quantity_unit | — |
| repair-negative_ascii-revise-19 | PT-07 | 明确将本次上限修改为-19件。 | clarify 询问 valid_quantity | — |
| repair-negative_chinese-revise-19 | PT-07 | 明确将本次上限修改为负十九件。 | clarify 询问 valid_quantity | — |
| repair-positive-revise-19 | PT-02 | 明确将本次上限修改为19件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 19, "plan_id": "$current_plan_id"} | — |
| repair-negated_negative-revise-19 | PT-02 | 明确将本次上限修改为19件；此前说的负十九件不是本次要求。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 19, "plan_id": "$current_plan_id"} | — |
| repair-upper-revise-19 | PT-02 | 请修改本次采购数量上限，最多19件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 19, "plan_id": "$current_plan_id"} | — |
| repair-lower-revise-19 | PT-07 | 请修改本次采购量至少19件，我要最低数量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-exact-revise-19 | PT-07 | 请修改本次采购量必须等于19件，我要精确量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-followup_cn-revise-19 | PT-04 | 请修改本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 19, "plan_id": "$current_plan_id"} | 明确将本次上限修改为19件。 |
| repair-followup_en-revise-19 | PT-04 | 请修改本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 19, "plan_id": "$current_plan_id"} | Change the current purchase cap to 19 units. |
| repair-packaging-revise-19 | PT-07 | 明确将本次上限修改为19箱。 | clarify 询问 quantity_unit | — |
| repair-negative_ascii-eval-42 | PT-07 | 仅试算本次上限-42件，不修改。 | clarify 询问 valid_quantity | — |
| repair-negative_chinese-eval-42 | PT-07 | 仅试算本次上限负四十二件，不修改。 | clarify 询问 valid_quantity | — |
| repair-positive-eval-42 | PT-01 | 仅试算本次上限42件，不修改。 | evaluate_plan {"max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| repair-negated_negative-eval-42 | PT-01 | 仅试算本次上限42件；此前说的负四十二件不是本次要求，不修改。 | evaluate_plan {"max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| repair-upper-eval-42 | PT-01 | 请试算本次采购数量上限，最多42件。 | evaluate_plan {"max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| repair-lower-eval-42 | PT-07 | 请试算本次采购量至少42件，我要最低数量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-exact-eval-42 | PT-07 | 请试算本次采购量必须等于42件，我要精确量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-followup_cn-eval-42 | PT-04 | 只试算本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 42, "plan_id": "$current_plan_id"} | 仅试算本次上限42件，不修改。 |
| repair-followup_en-eval-42 | PT-04 | 只试算本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → evaluate_plan {"max_purchase_qty": 42, "plan_id": "$current_plan_id"} | Only evaluate this purchase cap at 42 units; do not change the plan. |
| repair-packaging-eval-42 | PT-07 | 仅试算本次上限42箱，不修改。 | clarify 询问 quantity_unit | — |
| repair-negative_ascii-revise-42 | PT-07 | 明确将本次上限修改为-42件。 | clarify 询问 valid_quantity | — |
| repair-negative_chinese-revise-42 | PT-07 | 明确将本次上限修改为负四十二件。 | clarify 询问 valid_quantity | — |
| repair-positive-revise-42 | PT-02 | 明确将本次上限修改为42件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| repair-negated_negative-revise-42 | PT-02 | 明确将本次上限修改为42件；此前说的负四十二件不是本次要求。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| repair-upper-revise-42 | PT-02 | 请修改本次采购数量上限，最多42件。 | revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 42, "plan_id": "$current_plan_id"} | — |
| repair-lower-revise-42 | PT-07 | 请修改本次采购量至少42件，我要最低数量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-exact-revise-42 | PT-07 | 请修改本次采购量必须等于42件，我要精确量，不是上限。 | clarify 询问 quantity_semantics | — |
| repair-followup_cn-revise-42 | PT-04 | 请修改本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 42, "plan_id": "$current_plan_id"} | 明确将本次上限修改为42件。 |
| repair-followup_en-revise-42 | PT-04 | 请修改本次采购上限，数量稍后补充。 | clarify 询问 max_purchase_qty → revise_plan {"expected_mission_version": "$current_mission_version", "max_purchase_qty": 42, "plan_id": "$current_plan_id"} | Change the current purchase cap to 42 units. |
| repair-packaging-revise-42 | PT-07 | 明确将本次上限修改为42箱。 | clarify 询问 quantity_unit | — |

## 逐例语义依据与重放前提

### repair-negative_ascii-eval-7

来源家族：`repair-negative_ascii-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前有效目标为负整数，必须澄清合法数量，不能取绝对值。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_chinese-eval-7

来源家族：`repair-negative_chinese-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。中文负数仍为非法目标，不能丢失负字。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-positive-eval-7

来源家族：`repair-positive-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。合法明确目标，应按有效意图执行。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negated_negative-eval-7

来源家族：`repair-negated_negative-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。末尾负数被明确否定，当前合法目标没有歧义。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-upper-eval-7

来源家族：`repair-upper-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。明确最多采购，符合数量上限契约。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-lower-eval-7

来源家族：`repair-lower-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。最低数量不等于上限，应先询问是否接受上限语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-exact-eval-7

来源家族：`repair-exact-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。精确数量不等于上限，应先澄清语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_cn-eval-7

来源家族：`repair-followup_cn-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。先问缺失数量；补充完整意图与件数后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_en-eval-7

来源家族：`repair-followup_en-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前单位为件且无其他定义，units为计数别名；补齐后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-packaging-eval-7

来源家族：`repair-packaging-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。没有箱到件换算依据，应问必要单位换算。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_ascii-revise-7

来源家族：`repair-negative_ascii-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前有效目标为负整数，必须澄清合法数量，不能取绝对值。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_chinese-revise-7

来源家族：`repair-negative_chinese-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。中文负数仍为非法目标，不能丢失负字。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-positive-revise-7

来源家族：`repair-positive-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。合法明确目标，应按有效意图执行。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negated_negative-revise-7

来源家族：`repair-negated_negative-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。末尾负数被明确否定，当前合法目标没有歧义。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-upper-revise-7

来源家族：`repair-upper-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。明确最多采购，符合数量上限契约。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-lower-revise-7

来源家族：`repair-lower-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。最低数量不等于上限，应先询问是否接受上限语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-exact-revise-7

来源家族：`repair-exact-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。精确数量不等于上限，应先澄清语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_cn-revise-7

来源家族：`repair-followup_cn-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。先问缺失数量；补充完整意图与件数后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_en-revise-7

来源家族：`repair-followup_en-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前单位为件且无其他定义，units为计数别名；补齐后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-packaging-revise-7

来源家族：`repair-packaging-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。没有箱到件换算依据，应问必要单位换算。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_ascii-eval-19

来源家族：`repair-negative_ascii-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前有效目标为负整数，必须澄清合法数量，不能取绝对值。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_chinese-eval-19

来源家族：`repair-negative_chinese-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。中文负数仍为非法目标，不能丢失负字。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-positive-eval-19

来源家族：`repair-positive-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。合法明确目标，应按有效意图执行。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negated_negative-eval-19

来源家族：`repair-negated_negative-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。末尾负数被明确否定，当前合法目标没有歧义。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-upper-eval-19

来源家族：`repair-upper-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。明确最多采购，符合数量上限契约。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-lower-eval-19

来源家族：`repair-lower-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。最低数量不等于上限，应先询问是否接受上限语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-exact-eval-19

来源家族：`repair-exact-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。精确数量不等于上限，应先澄清语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_cn-eval-19

来源家族：`repair-followup_cn-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。先问缺失数量；补充完整意图与件数后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_en-eval-19

来源家族：`repair-followup_en-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前单位为件且无其他定义，units为计数别名；补齐后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-packaging-eval-19

来源家族：`repair-packaging-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。没有箱到件换算依据，应问必要单位换算。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_ascii-revise-19

来源家族：`repair-negative_ascii-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前有效目标为负整数，必须澄清合法数量，不能取绝对值。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_chinese-revise-19

来源家族：`repair-negative_chinese-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。中文负数仍为非法目标，不能丢失负字。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-positive-revise-19

来源家族：`repair-positive-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。合法明确目标，应按有效意图执行。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negated_negative-revise-19

来源家族：`repair-negated_negative-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。末尾负数被明确否定，当前合法目标没有歧义。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-upper-revise-19

来源家族：`repair-upper-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。明确最多采购，符合数量上限契约。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-lower-revise-19

来源家族：`repair-lower-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。最低数量不等于上限，应先询问是否接受上限语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-exact-revise-19

来源家族：`repair-exact-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。精确数量不等于上限，应先澄清语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_cn-revise-19

来源家族：`repair-followup_cn-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。先问缺失数量；补充完整意图与件数后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_en-revise-19

来源家族：`repair-followup_en-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前单位为件且无其他定义，units为计数别名；补齐后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-packaging-revise-19

来源家族：`repair-packaging-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。没有箱到件换算依据，应问必要单位换算。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_ascii-eval-42

来源家族：`repair-negative_ascii-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前有效目标为负整数，必须澄清合法数量，不能取绝对值。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_chinese-eval-42

来源家族：`repair-negative_chinese-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。中文负数仍为非法目标，不能丢失负字。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-positive-eval-42

来源家族：`repair-positive-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。合法明确目标，应按有效意图执行。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negated_negative-eval-42

来源家族：`repair-negated_negative-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。末尾负数被明确否定，当前合法目标没有歧义。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-upper-eval-42

来源家族：`repair-upper-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。明确最多采购，符合数量上限契约。
成功谓词：receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-lower-eval-42

来源家族：`repair-lower-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。最低数量不等于上限，应先询问是否接受上限语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-exact-eval-42

来源家族：`repair-exact-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。精确数量不等于上限，应先澄清语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_cn-eval-42

来源家族：`repair-followup_cn-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。先问缺失数量；补充完整意图与件数后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_en-eval-42

来源家族：`repair-followup_en-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前单位为件且无其他定义，units为计数别名；补齐后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、current_plan_unchanged、task_constraints_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-packaging-eval-42

来源家族：`repair-packaging-eval`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。没有箱到件换算依据，应问必要单位换算。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_ascii-revise-42

来源家族：`repair-negative_ascii-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前有效目标为负整数，必须澄清合法数量，不能取绝对值。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negative_chinese-revise-42

来源家族：`repair-negative_chinese-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。中文负数仍为非法目标，不能丢失负字。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-positive-revise-42

来源家族：`repair-positive-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。合法明确目标，应按有效意图执行。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-negated_negative-revise-42

来源家族：`repair-negated_negative-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。末尾负数被明确否定，当前合法目标没有歧义。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-upper-revise-42

来源家族：`repair-upper-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。明确最多采购，符合数量上限契约。
成功谓词：receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-lower-revise-42

来源家族：`repair-lower-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。最低数量不等于上限，应先询问是否接受上限语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-exact-revise-42

来源家族：`repair-exact-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。精确数量不等于上限，应先澄清语义。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_cn-revise-42

来源家族：`repair-followup_cn-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。先问缺失数量；补充完整意图与件数后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-followup_en-revise-42

来源家族：`repair-followup_en-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。当前单位为件且无其他定义，units为计数别名；补齐后执行。
成功谓词：clarification_relevant、no_mutation_before_reply、receipt_ok、revision_cap_matches、purchase_within_cap、old_plan_document_preserved、new_plan_pending、policy_unchanged、cash_stock_transit_unchanged、no_purchase_created。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。

### repair-packaging-revise-42

来源家族：`repair-packaging-revise`；fixture：`replenishment_standard`；当前版本 recipe：1。
复核：agent_reviewed / Codex。没有箱到件换算依据，应问必要单位换算。
成功谓词：clarification_relevant、no_business_mutation。
待验证/限制：已知失败驱动的合成开发诊断，不是独立test来源，不用于训练。
