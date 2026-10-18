# ShopSteward — Slide 10: Targeted model improvement

第 10 页独立替换稿。承接第 9 页的预测 WAPE 和 Agent 待改进项，以针对性后训练为主，评测只保留一句验证方式。第 7–9 页不变。

## Slide title

Targeted model improvement

## Read aloud

Our next step is to improve forecasting and specialise the agent through targeted post-training.

For forecasting, we will refine the model and track WAPE on unseen time periods.

For the agent, we plan supervised fine-tuning on verified replenishment examples, focusing on tool selection, parameter binding and necessary clarification.

For example, the model should distinguish a what-if calculation from an actual plan change, follow corrections in the conversation, and use the right quantities and plan references.

When a quantity or packaging conversion is missing, it should ask instead of guessing. Requests outside this task should return to the general agent.

We will compare the model before and after fine-tuning on the same tasks to check whether these behaviours improve.

To wrap up.

## 篇幅与衔接

- 本版约 121 个英文词，原第 10 页约 132 词，篇幅接近。
- 第 9 页说明问题；第 10 页说明具体改进方法。结尾保留 “To wrap up.” 接总结。
- 预测模型的精度改进与语言模型的 SFT 是两项工作；不以工具调用改善代替 WAPE 改善。

## Slide bullets（展示用，不额外朗读）

- Forecasting: refine the model to reduce WAPE.
- Targeted SFT: tool selection, parameter binding and necessary clarification.
- Training cases: what-if vs. changes, corrections, plan references and missing information.
- Validation: compare the same model before and after fine-tuning.

## 后训练目标与文档依据（备讲）

| 核心目标 | 具体要学会的行为 | 对应任务 |
|---|---|---|
| 工具选择 | 区分假设试算与正式修改；用户明确否定修改时只试算；撤回时不再执行当前请求 | PT-01、PT-02、PT-03、PT-06 |
| 参数绑定 | 提取最终有效数量；理解纠正与历史引用；绑定正确的当前方案及版本 | PT-03、PT-05、PT-07 |
| 必要澄清 | 缺数量、非法数量或包装换算依据时提问，不猜测或擅自取整 | PT-04、PT-07、PT-09 |
| 边界语义 | 区分取消上限与上限为零；范围外请求转回通用路径 | PT-08、PT-10 |

依据：

- [第二阶段 SFT 总计划](../superpowers/plans/2026-09-14-phase2-sft-data-eval-plan.md)：第 1–4 节明确首轮范围、职责边界和任务矩阵。
- [Data 准备与 B2 基线计划](../superpowers/plans/2026-09-17-data-preparation-and-b2-plan.md)：验证训练样本、建立目标模型训练前基线，并按其错误分布调整数据配额。
- [已完成的修复复评](../reports/posttraining/repair-v2/comparison.md)：当前受限任务已有提示/工程修复结果，不把上述任务类别全部描述成当前模型仍未解决的错误。

## 讲述边界（不朗读）

- 首轮 SFT 只训练补货对话中的受限决策，不训练开放式经营分析、需求预测计算、长报告或自主采购。
- 文中的 should 表示训练目标，plan 表示尚待实施；不能把计划写成已经取得微调收益。
- 不笼统声称 SFT 能消除所有幻觉。这里最直接的目标是减少意图误判、错误参数和缺信息时的猜测。
- 具体哪些类别需要更多训练数据，应由目标模型 B2 的训练前错误分布决定；SFT 收益需要同模型对照确认。
- 全面 rubric 评估仍属于第 9 页的待办；第 10 页集中解释后训练方法，不重复详细指标清单。
