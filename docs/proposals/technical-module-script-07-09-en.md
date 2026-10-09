# ShopSteward — Technical module speaker notes

展示 [Technical modules 架构图](shopsteward-technical-modules-en.html)。第 7 页讲核心技术，第 8 页讲数据来源，第 9 页讲已完成的端到端链路、预测指标与 Agent 评估待办；英文段落为朗读正文，中文备注不朗读。

讲述方式：第 7 页讲核心机制、业务作用及亮点；第 8 页说明数据来源与用途；第 9 页直接引用历史评测 WAPE，说明当前待改进项和评估方法；其他段落不堆砌指标。图可以保持全景，评委自行阅读；页码按钮只是可选的分区高亮。

## 07 — Core technologies

对应模块：B Orchestration & memory · D RAG · E Forecasting

We bring together four core technologies.

We use LangGraph to coordinate the agent: it breaks requests into tool calls and carries context between steps.

We then use retrieval-augmented generation, or RAG, to find relevant store policies and supplier terms, so recommendations come with supporting evidence.

For demand forecasting, we combine LightGBM with a neural network. Their predictions feed into replenishment planning alongside stock and cash constraints.

Finally, we adapt a Hermes-style memory mechanism to retain user preferences, stable background information and task instructions across conversations.

Together, these help the agent coordinate actions, consult evidence, anticipate demand and remember how the owner works.

## 08 — Data sources

对应数据与模块：E M5 公开销量 · D 公开参考资料与自建业务文档 · F 模拟经营数据

To support these technologies, we use three main data sources.

First, the public M5 dataset provides historical retail sales. We use it to train and test our demand forecasting models.

Second, our knowledge base combines public reference material with business documents we create, including supplier quotations and store policies. The agent retrieves these through RAG when explaining its recommendations.

Finally, we build simulated store scenarios with inventory, cash, sales and delivery events. These let us test how the agent responds to changing business conditions.

## 09 — Progress and next steps

对应模块：A Frontend · D RAG · E Forecasting · B/G Agent evaluation

We have already completed an end-to-end test connecting the frontend, RAG and the forecasting model.

Our forecast WAPE is still around thirty-five percent on our historical evaluation. Reducing this error is one of our next priorities.

The other is a full evaluation of the current agent against the project rubric. We will check tool selection and parameter accuracy, look for hallucinated claims, and assess whether its analysis reaches correct conclusions from the available evidence.

We will use these results to pinpoint failures, make targeted fixes and rerun the evaluation to measure improvement. The next slide explains our evaluation design.

## 核心技术与亮点（备讲，不逐项加读）

| 核心技术 | 在本项目中的作用 | 值得讲的亮点 |
|---|---|---|
| LangGraph | 编排推理步骤、工具调用和上下文 | 把经营请求转成有状态的多步任务 |
| RAG | 检索门店政策、供应商条款及相关文件 | 建议能引用业务依据；这里的 policy 指业务政策，不是 RL 策略 |
| LightGBM + 神经网络集成 | 组合预测结果，为补货规划提供需求输入 | 预测与库存、现金约束共同服务决策；不把预测直接等同于采购数量 |
| Hermes-style memory | 保存用户偏好、稳定背景及任务指令 | 跨对话延续经营偏好，支持修订；动态库存与现金仍由工具查询 |
| Task evaluation | 检查任务完成情况、工具选择和结果 | 找出可用于后续数据准备与模型改进的问题 |
| SFT / Multi-Agent / RL（未来） | 学习工具使用、分工协作、利用模拟反馈改进决策 | 作为待验证方向，与现有基线比较 |

## 与整组讲稿的衔接

- 第 7 页接原第 6 页的 “Now, how is it built?”，按 LangGraph → RAG → 混合预测 → 记忆机制讲解。
- 第 8 页承接核心技术：M5 销量用于预测，公开资料和自建业务文档用于 RAG，模拟经营数据用于场景测试。缺货需求与评测答案隔离留作问答补充。
- 第 9 页说明前端、RAG、预测模型的端到端链路已经完成测试；当前待办为降低预测 WAPE，以及按 rubric 完整评估 Agent 的工具调用、幻觉和分析正确性，定位问题、定向修复并复测。最后接第 10 页的评测设计。
- 不逐项朗读 Nuxt、FastAPI、SQLAlchemy、PostgreSQL 等基础设施技术栈。
- SFT、Multi-Agent 和 RL 保留在架构图的未来扩展区，作为问答备讲，不占用第 9 页原来的进展与挑战主题。

## 技术表述依据（不朗读）

- Hermes 类比有实际代码依据：`agent/src/shopsteward_agent/memory/hermes_policy.py` 适配 Hermes MemoryStore 的编辑逻辑；后端区分 USER、NOTES 与 SKILL。这里不声称复刻整个 Hermes Agent。
- 预测实现见 `ml/src/shopsteward_ml/runtime.py` 与 `_neural.py`，包含 LightGBM 组件与神经网络组件的组合。
- RAG 的作用是取得政策、条款等文档证据，并非由检索模块执行经营规则。

- 第 9 页 WAPE 来源：`docs/reports/forecast-v6-product-integration.md`，v6 历史八周评测为 34.976%，口播取约 35%。这是历史预测误差，不等于 Agent 成功率，也不表示所有门店都具有同样表现。
- 端到端测试已完成的状态按项目负责人本次确认更新；不再把“首次跑通完整链路”列为待办。
- Rubric 评估部分列出本次指定的检查维度，不虚构 rubric 权重、Agent 成绩或改进幅度。
