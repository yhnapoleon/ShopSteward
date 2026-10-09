# 补货工具决策任务契约 v0

日期：2026-09-14。代码依据：`30bed9f`。阶段：E1，规格与接口完成，真实工具重放和模型评测未开始。

## 1. 评测对象

已有补货 Mission 中的本次采购数量上限决策。固定流程提供当前 Plan、Mission 版本、单位及相关历史；模型每步输出一个工具调用。最多一次必要澄清及一次完整用户回复。

不评预测精度、开放经营分析、报告文风、采购审批、复杂恢复或生产并发。目标是测清动作、完整参数及任务成功率。

## 2. 动作与参数

| 动作 | 必须参数 | 正确含义 |
|---|---|---|
| evaluate_plan | plan_id、max_purchase_qty | 假设试算，不修改正式方案 |
| revise_plan | plan_id、max_purchase_qty、expected_mission_version | 修订本次上限，形成待确认方案，不执行采购 |
| clarify | question | 只问影响当前动作的必要缺项 |
| handoff | reason | unsupported_request、insufficient_context、permission_scope 三选一 |
| no_action | reason | 固定为 withdraw_current_request，只结束当前请求 |

所有参数拒绝未知字段；动作和参数均保留模型原值，不修正错误 ID、数量或版本。模型协议统一为一个 `tool_calls` 元素；多动作或没有动作均不合法。JSON 参数可为对象或 JSON 字符串，空格和键顺序不影响解析结果。

模型 schema 比现有业务默认值更明确：即使后端允许缺省数量，学生仍须显式输出 max_purchase_qty；版本使用严格正整数。`source_message_id` 是后端来源信息，不由模型提供。

## 3. 必须区分的语义

| 对照 | 本轮规则 |
|---|---|
| “如果上限20件” / “把上限改成20件” | evaluate / revise，不能因数值相同混淆动作 |
| “先别改，只试算20” | evaluate；否定写入优先 |
| “本次必须刚好买20，不是最多20” | clarify(quantity_semantics)，不能以数量上限偷偷替代精确量 |
| 上限 0 / 无额外上限 | 0 / null；两者不同 |
| “改低一些”但无数量 | clarify(max_purchase_qty)，不能猜一个经营上更合适的数 |
| -5 / 20.5 / 1000001 | clarify(valid_quantity)，不能截断、取整或转换 |
| 二十 / 二十五 / 一百万 | 解释成整数20/25/1000000，前提仍是上限请求 |
| “20箱”但单位为件且无换算信息 | clarify(quantity_unit)，不能当成20件 |
| 唯一历史上限 / 多个不明确历史值 | 前者按上下文绑定；后者 clarify(history_reference) |
| 撤回本次请求 / 取消已有Mission或回滚 | 本轮只支持前者，不执行后者 |

真实建议采购量可以小于上限；试算上限35不要求业务候选正好包含35件。取消额外上限不修改正式现金政策。

## 4. 模型输入与评测金标

`PolicyContext` 保存 messages、mission_id、plan_id、mission_version、quantity_unit、quantity_cap、tool_schemas、context_version。当前不存在 Plan 时 plan_id 可以为 null，由后续场景和路由定义处理；本批核心例均要求存在当前 Plan。

`Decision` 保存已验证 name 和 arguments。`DecisionRecord` 另外保存原始响应、解析错误、usage 和 latency_ms，解析失败不伪造一个正确动作。

`EpisodeSpec` 保存请求、后续脚本回复、历史交互 recipe、fixture 版本、expected_steps、final_predicates、分组和复核依据。它是评测资料，不能整份喂给模型。

金标中 `$current_plan_id`、`$current_mission_version`、`$historical_plan_id` 是重放引用；E3 创建真实对象后再映射。当前没有真实数据库 ID 或已验证回执。`history` 也是待执行的前序交互 recipe，而非预先编造的事实证据。

每个目标固定一个允许动作；工具目标包含完整参数。澄清金标使用 `clarification_slot`，不固定问题文字。一个有后续回复的 episode 必须先澄清再执行或结束，不允许第三步。

## 5. 成功谓词

| 路径 | 必须检查的实际事实 |
|---|---|
| 试算 | 真实回执成功且参数/对象相符；当前Plan和正式约束不变；现金、库存、在途不变；未创建采购 |
| 修订 | 新约束匹配要求；实际采购量符合上限；旧Plan文档保留；新Plan待确认；现金政策不变；未执行采购 |
| 澄清后完成 | 问到必要缺项、回复前无修改；完整回复后的实际工具结果满足对应试算/修订谓词 |
| 仅澄清边界 | 问到标注缺项且没有业务变化；只计澄清决策，不作为核心完成率样本 |
| 撤回 | 当前请求结束、Mission未取消且业务不变 |
| 范围外转交 | 有合法 handoff 与 reason，本轮无业务修改；不声称通用Agent已经完成后续任务 |

旧Plan在修订后可以把 status 改为 SUPERSEDED；只要求原 document 保留，不能要求整条记录完全相等。日志和审计记录可以新增，不做全数据库相等比较。

澄清 rubric：问到必要缺项、没有猜值、没有索取已知Plan ID，三项都满足才计正确；后续实际模型响应由复核者登记。E1 的案例语义复核不是对尚未生成的模型问题打分。

## 6. smoke-50 覆盖与复核

| 任务 | episode |
|---|---:|
| PT-01 假设试算 | 10 |
| PT-02 明确修订 | 10 |
| PT-03 否定修改/仅试算 | 8 |
| PT-04 缺项后一次澄清 | 8 |
| PT-05 历史指代 | 3 |
| PT-06 撤回 | 3 |
| PT-07 非法数量/精确数量语义 | 4 |
| PT-08 范围外 | 2 |
| PT-09 单位歧义 | 1 |
| PT-10 取消额外上限 | 1 |

合计50个episode，36核心+14挑战，58个决策目标。全部属于dev，不能用这批已见题目声明独立测试成绩或直接转为训练数据。

本批记录42个语义家族标签，便于后续同源追踪；这些标签不是42个独立真实业务来源，也不证明统计独立性。相同数值边界和近似意图对照已共享家族；后续 train/test 来源分组仍需在扩写前检查。

逐例语义检查由Codex完成，50条均附具体rationale，标记 `agent_reviewed`。团队人工审核数量为0，不伪称人工复核。交付的是可供团队复核的50例规格候选；无需等待人工审核才能开展E2评分器实现。

## 7. 已知执行限制及下一步

- 所有 fixture 的 execution_status 为 not_run；replenishment_standard/capped/revised 的实际构造在E3实现。
- PT-05-001 虽可语义绑定前次20，但当前消息未重复数量；真实后端是否接受来源单列验证，不改写原消息。
- PT-10 已有直接revision API的null测试依据，但Agent网关的null行为未验证；当前只能称规格候选，不能称已发布的执行测试集。
- PT-07第4例用于“刚好20”与“最多20”的语义边界，与负数/小数/超上界合计仍为4例；这是从总计划数量边界要求落实到smoke的明确选择。
- E2实现评分器，E3才冻结真实上下文并调用模型；本轮输出的100%规格通过率不是模型准确率。

相关产物：[完整案例与逐例依据](smoke-50-cases.md)、[规格校验统计](eval-e1-validation.json)、[Eval实施计划](../../superpowers/plans/2026-09-14-phase2-eval-implementation-plan.md)。
