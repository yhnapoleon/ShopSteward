# E2 scorer 与真实执行接入检查

2026-09-14。E2 已完成；E3/E4 的正式模型结果尚在运行准备中。

- 17 项 scorer 测试通过：错误动作、数量、Plan ID、版本、无回执、假回执、试算误写、缺失状态、伪造交付、后端拒绝、澄清复核、非法格式等。
- 参数比较保留严格类型；宽上限允许实际采购更少。数量为 0 且 `proposed_purchase=null` 时，必须由真实推荐候选的数量证明为 0。
- decision 模式不产生核心业务成功率。正确模型决策被后端拒绝时，决策正确与执行失败分别记录。
- 澄清复核绑定实际问题和缺项；没有复核不能继续脚本回复。当前由 Codex 逐项检查并标记 `agent_reviewed`，人工复核数为 0。
- 61 项轻量测试通过，覆盖 E1 契约、E2 评分、受限 policy、runner、报告分母、离线重评分和澄清恢复。Ruff 检查通过。
- 8 项真实 PostgreSQL 集成测试通过：独立任务调度、试算、修订、0、宽上限、null、澄清后修订、澄清后试算。固定决策测试验证 harness，不计为模型成绩。

执行适配复用现有 Mission/Plan、Agent job、临时 run token、工具网关和业务引擎。评测仅使用 `shopsteward_test` 中新建的合成对象。scheduler 增加可选 `job_ids`，让评测只领取自身任务；默认行为保持原有语义。

首个 B0 完整决策结果：50 episodes / 58 decisions，动作 56/58，完整参数 35/38，环境错误 0，待复核 0。这里不报告真实执行成功率；原始证据在 `var/posttraining/runs/smoke-v1/decision/B0/`。

B1 使用项目已配置的 `gpt-5.6-luna`、Responses API、温度 0、输出预算 1024、并发 1、单次调用且不自动修复。单条合成探针成功，返回有效 evaluate_plan 动作；701 input tokens、65 output tokens，调用耗时约 4.55 秒。探针不进入正式分数。价格尚未配置，金额记不可用，不能填 0。
