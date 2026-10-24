# B2-A Agent 首版框架实现与验证

日期：2026-09-07。基准分支 `YH` / `ab01ae3`；本次实现尚未提交、推送。用户授权的是 LangGraph、Hermes 派生记忆、任务 Skill、对话方案循环与后台跟进的首版框架。

## 已交付

`agent/` 是可安装的 `shopsteward_agent` 包，包含真实 LangGraph StateGraph、可配置 OpenAI 风格模型适配、带租约保护的官方 PostgreSQL saver、纯函数化 Hermes 条目策略与扩展接口。`backend/app/agent_bridge/` 负责会话、Run、授权工具、知识版本、持久跟进和独立 Agent worker 的装配。业务 worker 保留原8类 handler。

用户可以持续讨论当前方案：查询事实和解释 Plan → 只读假设试算 → 显式调整本轮数量上限 → 后端生成新待确认 Plan → 用户通过既有精确审批 API 确认。旧 Plan 的内容保留，正式现金 Policy 不受一次性约束影响。当前方案修订范围为补货数量上限，并非任意经营目标优化器。

通用偏好进入 USER，稳定背景进入 NOTES，补货流程及任务偏好进入 SKILL。它们支持明确增改删、版本冲突检测、来源追溯和跨会话使用。每次模型节点加载当前知识；读取问题不会自动变成写入，澄清中明确否定写入会覆盖原保存意图。后台跟进按持久事件水位与状态指纹去重，结果保存到应用消息。

源码 OpenAPI 为40个操作、36条路径，其中新增11个 Agent 操作、8条路径。迁移 `0007_agent`、`0008_agent_constraints`、`0009_agent_scopes` 已在专用测试库与独立验收库运行；知识位于 `agent_data`，图检查点位于 `agent_checkpoints`。

## 自动验证

| 检查 | 实际结果 |
|---|---|
| backend + agent：backend目录 `python -m pytest tests ../agent/tests -c pyproject.toml -q --tb=short -rs` | 226 passed，91.65秒，无跳过 |
| simulator：指定 simulation 配置和专用测试库 | 12 passed，3.49秒，无跳过 |
| `ruff check backend agent simulation` | 通过 |
| `ruff format --check backend agent simulation` | 160 files already formatted |
| 测试库 `alembic check` | No new upgrade operations detected |
| `docs/api/validate_contracts.py` | 设计契约、引用、示例、负例、Plan金额及hash通过 |
| `docs/api/validate_frontend_data_contract.py` | 7个已实现GET、8个既有runtime schema、示例与负例通过 |
| `backend/tools/export_agent_contract.py` | 实际应用导出8条Agent路径、36条总路径 |
| `uv build --package shopsteward-agent --offline` | wheel与sdist构建通过，第三方许可随包携带 |
| 授权 API Key 精确内容扫描 | 变更及未跟踪的非忽略文件中未发现该Key；不是对所有类型凭证的完整扫描 |
| `git diff --check` | 通过；Git仅提示已有文件换行规范化 |

测试环境使用真实 PostgreSQL：`shopsteward_test`、`shopsteward_sim_test`。联合测试包括模型/HTTP替身测试及真实 PG 事务测试；它们不全部属于真实模型调用。

重点覆盖：同会话消息排队与唯一最终回复；owner/store隔离；工具禁用审批、参数越界拒绝、回执重放和旧token拒绝；what-if只读与修订后新Plan；知识版本与删除；澄清恢复与旧interrupt重放；取消和第三次租约失效后的队列解锁；官方checkpoint与pending writes的旧writer拒绝；运行中事件不丢失、无变化不重复派发。

## 真实模型与进程

使用官方 OpenAI `gpt-4.1-mini`，仅发送合成验收数据，Key从用户授权的本地文件读取。详见 [进程报告](agent-v1-process-report.md) 和 [机器证据](../api/agent-v1-process-result.json)。

- 三轮独立记忆验收：3个合成门店、24个Run、51项检查，验证 USER/SKILL 保存、跨会话读取、纠正、删除。最近6条新会话读取回复同时核对了偏好格式、任务流程和金额。
- 此前完整基线中14个非记忆检查通过：解释当前Plan、只读max20试算、新待确认Plan、后台跟进、真实65秒无变化观测与状态变化后触发。该基线中的记忆失败保留，修复后使用上述三轮专门复测。
- 恢复套件7项检查通过：实际中断自建worker，等待租约失效后attempt2恢复且只发布一次；两个真实worker处理同会话；运行中取消不发布；真实模型澄清后在同一Run恢复。
- 累计报告用量392667 tokens，另有2个Run用量未知；不是完整计费总额。早期失败及复测证据保留，未用最终SUCCEEDED状态替代内容核对。

真实进程验收完成后，最后增加了“澄清时否定保存”的后端拒绝测试：先复现错误写入，再修复并纳入226项联合回归。这个新增拒绝分支没有再次调用真实模型。

## 审查与修复

独立运行时/后端审查后，修复了会话行锁与业务事件外键之间的锁等待环，改为兼容外键 KEY SHARE 的 NO KEY UPDATE，并用真实PG并发测试验证。恢复输入绑定原interrupt ID，避免旧恢复消息在崩溃重放时回答新的问题。明确记忆命令要求成功工具回执，允许澄清，防止模型只口头声称保存。模型输出金额使用后端分值和确定性显示校验，异常说明可回退并保留警示。

## 已知边界及下一步

首版框架可通过 API 使用，尚无聊天页面。原开发库与8000/8001进程未切换；隔离8024 API和自建worker已停止。启动新版步骤见 [Agent README](../../agent/README.md)，不要直接重复占用8000。

语义摘要暂未实现，历史采用最近80条消息窗口。外部 RAG/SkillProvider、真实预测和自动从执行结果学习技能尚未装配。当前任务Skill为显式可维护的版本化流程文本。首版不是完整的长期负载或自然语言正确性证明。

原A8故障矩阵未全部进程化注入，尤其未测试“记忆事务提交后HTTP响应丢失”的真实进程场景；工具回执/版本/租约有集成覆盖。Agent跟进扫描随worker领取轮次运行，模型占用执行槽时可延后；不承诺负载下的固定跟进时延。多供应商、多SKU优化继续属于后续工作包。
