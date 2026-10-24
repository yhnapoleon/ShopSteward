# ShopSteward Agent Framework Implementation Plan

## 2026-09-07 实施对照（优先于下方原始建议）

用户随后明确授权按计划实现，并补充任务 Skill 持续维护和对话方案反馈循环。首版框架已落地；当前源码与运行步骤见 [Agent README](../../../agent/README.md)，实测范围与未覆盖项见 [测试报告](../../reports/agent-v1-test-report.md)。下方原始设计细节保留为规划基线，不代表每个建议均已实现。

| 工作包 | 实际交付 |
|---|---|
| A0 / A2 | 固定 LangGraph 等依赖；官方 PG saver 事务租约保护，含 pending writes；真实 worker 中断恢复及旧 writer 拒绝 |
| A1 / A3 | 会话消息 FIFO、Run/Job、独立 Agent worker、真实模型有限工具图、澄清/resume/cancel、幂等最终回复 |
| A4 | 当前 Mission 绑定的业务工具、只读试算、显式数量约束修订与新 Plan；既有审批保留 |
| A5 | Hermes 固定版本派生条目规则、PG 私有 USER/NOTES、版本化可写补货任务 SKILL、来源与版本冲突 |
| A6 | 持久事件水位与指纹、用户开启的周期跟进、无变化不调用模型、运行中事件保留后继 |
| A7 | 11 个真实操作、当前知识读取/编辑、模型与 EvidenceProvider/SkillProvider 扩展接口；外部 provider 尚未装配 |
| A8 | 联合自动回归与真实模型/进程核心闭环通过；详见报告，未把原计划全部故障矩阵标为完成 |

实现调整：通用偏好放 USER，任务偏好和流程放 `SKILL(task_type=replenishment)`；用户明确命令可以增改删，当前版本每个模型节点重新加载。一次性的数量限制放 Mission.task_constraints，在本轮采购成功后清除，不写长期记忆、不改变现金 Policy。对话循环通过新 Run/澄清恢复组织，确定性试算、Plan 版本和批准仍归 backend。

实际知识 API 是 `/api/v1/stores/{store_id}/agent-knowledge`；没有新增原草案 `/agent-memories`。历史上下文采用最近80条消息窗口，暂未实现 Conversation 语义摘要。外部 SkillProvider 是只读扩展接口，已落地的用户任务 Skill 由版本化知识服务维护；不运行任意技能脚本。没有部署独立 Agent HTTP 服务。

尚未完成原计划中的全部进程故障注入，特别是“记忆提交后 HTTP 响应丢失”的真实进程场景；工具回执重放、版本冲突与租约失效有集成测试。完整故障矩阵、长期负载和语义摘要保留为后续加固项。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 下方保留原始执行清单；实际工作包交付以顶部实施对照与验证报告为准。未逐项核验的原清单复选框不作完成声明。

**Goal:** 交付真实模型对话、受限业务工具、跨会话 Hermes 派生记忆与持久后台跟进的 B2-A 首版。

**Architecture:** 独立 Agent worker 复用 backend JobRun，调用独立 shopsteward_agent Python 包中的 LangGraph StateGraph。产品侧会话/授权/触发归 backend，主图/模型/记忆归 agent；同一 PG 应用数据库的独立 schema 支持 checkpoint、记忆与租约事务组合。

**Tech Stack:** Python >=3.11、FastAPI、PostgreSQL、LangGraph、langgraph-checkpoint-postgres、psycopg、langchain-openai；现有 SQLAlchemy/asyncpg 保持。

**Spec:** [2026-09-07-agent-framework-design.md](../specs/2026-09-07-agent-framework-design.md)

## Global Constraints

- 结构正确、功能完整满足要求、没有赘余设计。
- Python >=3.11；Windows/PowerShell；数据库使用 PostgreSQL；金额遵守既有整数分契约。
- business worker 保留原8类handler；Agent模型任务只由profile=agent的worker领取。
- 不新增经营审批、采购、模拟推进权限；graph等待状态不改写Mission状态。
- 所有checkpoint写入、记忆变更、工具效果及最终发布均校验当前租约；测试包含换主后的旧writer。
- 用户会话按principal/store/Mission隔离；同会话只有一个未结束Run；用户消息不合并。
- API GET不触发模型或任务；模型调用/HTTP不在数据库写事务内。
- 不把模型Key、短期工具token、租约token写进图状态、提示、日志或Git。
- 不清理他人改动；调研开始时基础为YH/da79cbd，期间外部提交推进到YH/ab01ae3，执行前重新核对。
- 不实现完整RAG、B1预测、多SKU优化、程序性技能自动学习或第二套Agent HTTP运行服务。

---

## 0. 执行顺序与交付里程碑

| 工作包 | 依赖 | 交付物 | 预计净开发量* |
|---|---|---|---|
| A0 依赖及恢复实验 | 无 | 固定依赖、真实PG事务组合证据 | 0.5～1天 |
| A1 会话、Run与专用worker | A0 | 持久消息入队、领取、结果发布 | 1～1.5天 |
| A2 checkpoint及澄清恢复 | A1 | 真正可重启、租约保护的图运行 | 1～2天 |
| A3 模型适配与有限工具循环 | A2 | 真模型协议、预算、结构化结果 | 0.5～1天 |
| A4 backend工具授权与效果幂等 | A1/A3 | 受限经营工具，精确Plan卡片 | 1～2天 |
| A5 Hermes记忆适配 | A2/A3 | 有界、可纠正删除、跨会话记忆 | 1.5～2天 |
| A6 事件及周期跟进 | A4/A5 | 页面关闭后持续跟进，变化去重 | 1～1.5天 |
| A7 扩展接口及产品读取 | A4/A5 | 模型/证据/技能接缝、可用查询入口 | 0.5～1天 |
| A8 端到端故障与模型验收 | A6/A7 | A-01/M-01/F-01/R-01及B0回归证据 | 1～2天 |

*估计约8～14人天，是在现有B0环境可用基础上的工程判断，不是排期承诺；未含完整前端页面、外部审批等待或完整L-01。A0、A2属于先解决的兼容性风险，不能用空目录和假模型算完成。

建议按表顺序串行推进；多个测试进程不得同时清理现有backend/simulator测试库。每包有自己的验证和审查，不等到最后才第一次联调。

## 1. 文件职责图

下列路径相对 ShopSteward 仓库根；Create 表示实施时新增，原计划中的拟创建代码清单；实际文件以仓库为准。文件按实际职责建立，没有逻辑的文件不为目录对称而提前生成。

```text
agent/
  pyproject.toml                         可安装workspace包及依赖
  README.md / .env.example              配置、运行、验收
  src/shopsteward_agent/
    contracts.py                        Run输入输出、Scope、引用、版本等DTO
    ports.py                            实际装配所需的Protocol
    config.py                           Agent与模型配置
    graph.py                            StateGraph装配与路由
    state.py                            可持久化状态及reducer
    context.py                          当前事实、记忆和有界消息组装
    nodes.py                            模型/澄清/结果节点，小规模保持内聚
    executor.py                         AgentExecutor实现
    models/client.py / factory.py       首个OpenAI适配及模型构造
    tools/catalog.py / execution.py     显式工具规格、循环与结果归一
    tools/backend_client.py            固定基址HTTP调用
    memory/hermes_policy.py            有来源标注的必要条目核心
    memory/service.py / postgres.py    记忆用例、事务、版本与来源
    persistence/checkpoints.py         官方saver的租约事务包装
    extensions.py                      只读Evidence/Skill/Experience接口实现
  migrations/                          agent_data自有表迁移
  tests/unit/                          纯逻辑、预算、scope、协议
  tests/integration/                   真PG checkpoint/记忆与恢复
  tests/fixtures/                      录制协议和确定性测试数据
  tools/probe_model.py                 显式运行的兼容性探针
  tools/setup_checkpoints.py           显式上游schema初始化
backend/app/agent_bridge/
  models.py / schemas.py               产品会话、消息、Run、触发和工具记录
  repository.py                        入队、串行、发布、消费水位
  router.py                           用户消息/会话/运行/记忆投影入口
  jobs.py                             agent_followup handler工厂
  composition.py                      Python包与后端依赖装配
  authorization.py                    当前授权、短期工具凭证
  tool_router.py                      Agent专用受限业务入口
  checkpoint_fence.py                 同连接JobRun租约校验回调
  triggers.py                         业务触发登记与周期合并
backend/migrations/versions/
  0007_agent_runs.py                   产品侧表与索引（实施前核对最新head）
backend/tests/integration/
  test_agent_runs.py / test_agent_tools.py / test_agent_followups.py
backend/tools/verify_agent.py          自管进程验收，保留场景与证据
docs/api/agent-v1.openapi.json         本次增量设计与实现映射
docs/reports/agent-v1-test-report.md    分层验收结果
docs/third-party/hermes-memory.md      commit、原文件、修改与许可说明
```

必须修改的既有文件：backend/app/worker.py、bootstrap.py、core/config.py、api/schemas.py、main.py、migrations/env.py、scheduling/dispatcher.py，以及实际产生业务timeline/事件的最小入口。不要把整个B0业务层迁移到新目录。

## 2. 共同接口与测试约定

在A1创建 contracts.py / ports.py。DTO沿用严格字段校验、UTC时间、JSON可序列化的原则。

| 类型 | 固定字段 |
|---|---|
| RunRequest | run_id、conversation_id、mission_id、principal_id、store_id、trigger、message_id、message、graph_version、deadline_at |
| ExecutionContext | 当前运行权限、ModelClient、BackendToolClient、MemoryService、checkpoint factory、租约取消信号；仅进程内 |
| RunOutcome | status、response_text、references、proposed_actions、pending_question、usage、warnings、versions |
| MemoryScope | principal_id、store_id、target(USER/NOTES) |
| MemorySource | message_id、run_id、author_principal_id、source_kind(USER_EXPLICIT/RUN_EVIDENCE) |
| MemoryChange | action(add/replace/remove)、entry_id或null、expected_revision或null、content或null |
| MemoryMutationResult | success、scope_version、changed_entry_ids、error_code、done |
| ToolRequest | invocation_id、name、arguments；授权Run信息由传输context注入 |
| ToolResult | invocation_id、ok、data、references、error_code、retryable |
| ModelTurn | text、tool_calls、finish_reason、usage；供应商原始附加字段不扩散到业务层 |

```python
# 以下为拟实现接口签名，不是已经存在的运行代码。
AgentExecutor.execute(request: RunRequest, context: ExecutionContext) -> RunOutcome
ModelClient.complete(messages: list, tools: list, deadline_at: datetime) -> ModelTurn
BackendToolClient.call(request: ToolRequest) -> ToolResult
MemoryService.recall(scope: MemoryScope, query: str) -> MemoryBundle
MemoryService.apply_changes(scope, changes, expected_version, operation_id, source) -> MemoryMutationResult
EvidenceProvider.search(query: str, scope: MemoryScope) -> list[Evidence]
SkillProvider.list(task: str, scope: MemoryScope) -> list[SkillSummary]
SkillProvider.load(skill_id: str, version: str, scope: MemoryScope) -> SkillDocument
ExperienceReader.search(scope: MemoryScope, query: str, limit: int) -> list[ExperienceSummary]
```

Evidence包含id/source_uri/excerpt/observed_at/valid_until；SkillDocument包含id/version/content/required_tools/source；ExperienceSummary包含run_id/summary/references/occurred_at。未装配的检索/技能返回空列表，不对模型注册不可用工具。

测试优先验证外部可观察结果。每包先写对应失败情境，再实现、运行目标测试。以下代码块给出核心断言/关键算法；fixture在各包conftest中实现，不能让测试依赖开发库或用户Key。

## A0：依赖、源码归档及checkpoint事务实验

**Files:** Modify agent/pyproject.toml、根uv.lock；Create agent/tests/integration/test_checkpoint_transaction.py、agent/tools/setup_checkpoints.py、docs/third-party/hermes-memory.md、docs/reports/agent-a0-compatibility.md。

**Consumes:** 已有Python环境、专用测试库配置和[调研报告](../../research/2026-09-07-agent-framework-research.md)。
**Produces:** 固定依赖组合、可回滚的PG saver写入实验与Hermes采用清单。

- [ ] 核对Git/迁移head，不更新开发库。agent改成可安装的`shopsteward_agent`包；在agent依赖中尝试精确候选langgraph==1.2.11、langgraph-checkpoint-postgres==3.1.2、langchain-openai==1.6.0，psycopg[binary,pool]交由解析并锁定；FastAPI不自动加到agent包。
- [ ] 执行workspace依赖解析，检查backend已有依赖是否被提升；如冲突，保存resolver原因并选满足公共依赖约束的明确版本重新验证，不能依赖不受控的latest。
- [ ] 使用专用测试库中的agent_checkpoints_test schema运行setup。构造简单两节点StateGraph；在外层psycopg transaction内调用绑定同连接的AsyncPostgresSaver，再主动异常，确认checkpoint、blobs、writes全部未留下。
- [ ] 覆盖pipeline支持与非pipeline路径，确认没有提前提交；记录实际包版本、PG版本及返回值。核心实验必须呈现以下行为：

```python
with pytest.raises(RuntimeError):
    async with conn.transaction():
        saved = await saver.aput(config, checkpoint, {}, checkpoint['channel_versions'])
        raise RuntimeError('rollback probe')
assert await saver.aget_tuple(saved) is None
```

- [ ] 从固定Hermes提交归档必要原文件及同提交LICENSE，列出采用函数和拟修改边界；仅归档不import全局Hermes运行时。固定许可证获取失败则不能进入源码分发。
- [ ] 如使用真实模型探针，Key只从用户指定文件读取，基址固定已确认官方地址。保存脱敏能力结果。当前已有一次REST协议通过记录；这里仍须验证最终langchain-openai客户端路径。

**Verify:** 在agent目录运行`..\.venv\Scripts\python.exe -m pytest tests/integration/test_checkpoint_transaction.py -q`，设置专用AGENT_TEST_DATABASE_URL；无数据库时本包验收不能标通过。依赖锁定后运行backend单元/API测试检查解析影响。

**Exit:** 必须拿到真实PG回滚证据。此处未通过，不继续宣称具备租约安全的恢复。

## A1：产品会话、持久Run与worker隔离

**Files:** Create agent contracts.py、ports.py、backend agent_bridge models/schemas/repository/router/jobs/composition；Modify worker.py、bootstrap.py、main.py、core/config.py、backend/pyproject.toml、migrations/env.py；Create migration0007及test_agent_runs.py。

**Consumes:** A0依赖；现有JobRun、command幂等、User/store授权、Handler工厂。
**Produces:** POST message→同事务Message/Run/Job→Agent专用worker→唯一assistant Message。

- [ ] 写消息幂等、同键异内容、会话owner隔离和重启保留测试；两条用户消息都保留，只有队首获得会话运行槽。
- [ ] 建Conversation/Message/Run/ToolInvocation/Trigger表及外键；`(conversation_id, seq)`唯一、最终assistant`run_id`部分唯一、触发`source_key`唯一；用可锁定Conversation行串行分配seq与active_run_id。
- [ ] 只有已取得active_run_id的Run创建可领取Job；其他Run保留QUEUED，避免多个Job争用同一个图线程。完成/取消释放槽位并在同事务创建下一个Run的Job。
- [ ] 给worker增加profile参数：business保持原工厂与dispatcher；agent显式加载新包和agent handler，默认并发1，不装业务dispatcher。
- [ ] 用确定性EchoExecutor仅验证传输/队列链路，明确标记测试替身，不作为真模型交付。Handler的apply锁Conversation/Run，在repo.complete同租约事务中发布；after_complete只安排下一条任务。
- [ ] on_error对最终失败收口Run；agent专用before_claim核对因recover_expired耗尽重试而直接FAILED的Job，释放其会话槽并安排下一条，WAITING_INPUT除外。用SKIP LOCKED和有界扫描避免忙会话阻塞，测试“任务三次丢租约后后续用户消息仍能运行”。

```python
assert first.agent_run_id == replay.agent_run_id
assert await count_user_messages(conversation_id) == 1
assert await claimed_job_types(profile='business') <= ORIGINAL_B0_TYPES
assert await claimed_job_types(profile='agent') == {'agent_followup'}
```

- [ ] API未配置Agent时返回明确503；业务health/worker不依赖模型可达。POST的幂等重放仍重查当前会话可见性。

**Verify:** backend目录运行`..\.venv\Scripts\python.exe -m pytest tests/integration/test_agent_runs.py tests/api/test_foundation.py -q`。fixture中创建用户A/B、店铺A/B、Mission和独立会话，避免测试管理员掩盖隔离问题。

## A2：真正的checkpoint、澄清和租约恢复

**Files:** Create agent state.py、graph.py、executor.py、persistence/checkpoints.py；Create backend agent_bridge/checkpoint_fence.py；Extend jobs/repository/router；Create agent/tests/integration/test_graph_recovery.py、test_checkpoint_fencing.py。

**Consumes:** A1 Run/ExecutionContext；A0 saver事务证据。
**Produces:** 可恢复StateGraph、同会话串行、中断resume/cancel及所有checkpoint写入保护。

- [ ] 先写失去租约后`aput`和`aput_writes`均无变化的真实PG测试；测试必须包含旧协程仍存活、新worker已领取的场景。
- [ ] 按设计§8构造per-operation独占连接：schema固定；transaction内调用fence、官方saver，再检查clock_timestamp。factory实例持有lease上下文，不把token放进configurable或metadata。

```python
async with pool.connection() as conn:
    async with conn.transaction():
        await fence.assert_owned(conn)
        saved = await AsyncPostgresSaver(conn).aput(config, checkpoint, metadata, versions)
        await fence.assert_owned(conn)
return saved
```

- [ ] 同模式保护aput_writes；只读接口使用官方saver。提供最小序列化类型限制，不开启pickle。测试读回节点next/消息类型，不只比较计数。
- [ ] 最小图加入澄清节点；使用`interrupt({interrupt_id, question})`，resume请求匹配该interrupt；新执行段创建新Job但保留Run/thread。图版本不兼容返回明确GRAPH_VERSION_UNAVAILABLE。
- [ ] 稳定区分首次输入与恢复：新Run使用输入dict；运行中崩溃用None从当前checkpoint继续；WAITING_INPUT用Command(resume=...)；严禁重放相同用户输入造成第二条消息。
- [ ] graph_thread_id使用agent_run_id，产品conversation_id仅组织历史；固定input_through_seq、摘要covered_through_seq，测试取消旧Run后新Run不续跑旧节点，运行时不能读到排队在后的用户消息。
- [ ] cancel撤销token、取消READY任务并关闭Run，RUNNING协程在节点边界停止；最终事务再次检查取消。清理阻塞会话时安排下一个Run。

```python
await replace_lease(job_id)
with pytest.raises(LeaseLost):
    await stale_saver.aput_writes(config, [('messages', stale_reply)], task_id='old')
assert await load_current_checkpoint() == checkpoint_before_stale_write
```

**Verify:** agent目录运行`..\.venv\Scripts\python.exe -m pytest tests/integration/test_graph_recovery.py tests/integration/test_checkpoint_fencing.py -q`。重启测试使用实际进程；只取消async task不替代进程崩溃。

## A3：模型适配和有限循环

**Files:** Create models/client.py、models/factory.py、config.py、context.py、nodes.py、tools/catalog.py、tools/execution.py；Create tests/unit/test_model_protocol.py、test_graph_budget.py、tools/probe_model.py。

**Consumes:** ModelClient/ModelTurn、checkpoint/context接口。
**Produces:** OpenAI标准Chat Completions适配器、工具循环、预算与可预测失败。

- [ ] 用录制HTTP响应覆盖正常文本、function.arguments解析、非法JSON、未知工具、null usage、401/429/5xx及deadline。返回未知usage为null，认证错误不重试。
- [ ] 实现factory，明确`use_responses_api=False`作为标准Chat Completions路径；模型名、base_url、Key文件从部署配置读取，测试不得读取真实Key。
- [ ] 默认不发未验证可选字段；工具schema由目录生成。将LangChain AIMessage/tool_calls映射ModelTurn，再由项目执行器校验。第一次协议修复最多一次；供应商差异局限在adapter。
- [ ] 节点检查剩余budget后调用模型；每Run8模型/12工具/90秒预算，单次模型30秒。消息窗口保持tool_call/result成对；有界摘要失败时保留近期完整组并显式截断历史范围。

```python
assert budget.allow_model_call() is False  # 第9次
assert outcome.error_code == 'AGENT_BUDGET_EXHAUSTED'
assert model_response_without_usage.usage is None
assert outgoing_payload['model'] == settings.model
```

- [ ] 使用实际LangChain客户端重跑中文、tool请求、结果回填探针，输出模型/客户端版本与脱敏报告；与本轮REST探针区分。加入第二个配置的mock base_url证明可切换，但不能把mock称为第二供应商实测。

**Verify:** agent目录运行`..\.venv\Scripts\python.exe -m pytest tests/unit/test_model_protocol.py tests/unit/test_graph_budget.py -q`；显式运行probe_model.py后检查能力报告。普通CI不消耗模型API。

## A4：业务工具、运行授权和精确结果

**Files:** Create backend agent_bridge/authorization.py、tool_router.py；Create agent tools/backend_client.py；Extend catalog/execution/nodes；Create backend/tests/integration/test_agent_tools.py、agent/tests/unit/test_result_references.py。

**Consumes:** A1 Run当前权限、A3 ToolRequest/ToolResult；既有Mission/Plan/dashboard/Action/timeline/sales summary/request_check用例。
**Produces:** 7个实际受限业务工具与有据可查的Plan卡片。

- [ ] 写viewer不可request_check、跨Mission/店铺资源拒绝、伪造Run及旧attempt token失效测试；原来源Service token不能作为Agent token。
- [ ] 领取时生成随机Run token，摘要/expiry绑定当前Job；HTTP入口每次验证现有授权与Run租约。当前配置中principal已移除或门店权限撤销立即拒绝，不沿用创建时旧授权。
- [ ] 按显式目录映射到已有查询用例；store/principal由Run注入，检查资源归属；不通过任意URL或管理员身份代调用。
- [ ] ToolInvocation首次保存invocation_id/args_hash；request_check效果与工具回执同事务；final lease check按既有store→mission→业务记录→job顺序。重放返回原结果，不生成新key。

```python
assert await call_tool(expired_token, 'request_check', args) == unauthorized
assert replay.result == first.result
assert await count_checks_for_invocation(invocation_id) == 1
assert 'approve_plan' not in model_tool_names
```

- [ ] validate_result核对引用来自已读工具结果。SUGGEST_PURCHASE只接受plan引用；采购卡片重新由Plan生成并呈现版本/hash/expiry；未知引用返回结构化校验失败或一次有界修复。
- [ ] 场景断言40件推荐、80件现金淘汰、Action受理不等于到货；Agent直接要求审批/advance时不能调用对应功能。

**Verify:** backend目录运行`..\.venv\Scripts\python.exe -m pytest tests/integration/test_agent_tools.py -q`；agent运行test_result_references.py。断响应测试必须检查数据库效果，不仅检查HTTP调用次数。

## A5：Hermes派生记忆与跨会话闭环

**Files:** Create agent memory/hermes_policy.py、service.py、postgres.py；Create agent迁移、tests/unit/test_hermes_policy.py、tests/integration/test_memory_service.py；Extend memory_edit工具和backend用户记忆投影API。

**Consumes:** A0固定源码、MemoryScope/Change/Source、当前写入fence、ToolInvocation、用户消息来源。
**Produces:** USER/NOTES有界持久记忆、来源/版本/去重、纠正/删除、跨会话读取。

- [ ] 写无副作用条目算法测试：重复add、歧义替换、原子batch、最终预算溢出；用普通Python列表副本作为输入，不读全局Hermes目录。
- [ ] 抽取必要纯逻辑，移除路径/全局配置/registry/后台线程依赖；每个采用函数记录上游位置与改动。外层使用entry_id/revision，避免依赖模型复述整段旧内容。
- [ ] agent_data迁移建scope和entry revision；PG读取和事务由MemoryService管理。修改使用scope锁与expected_version，并在最终提交前检验运行所有权；批量失败不写任何revision。

```python
before = await memory.recall(scope, '')
result = await memory.apply_changes(scope, over_budget_changes, before.version, op_id, source)
assert result.error_code == 'MEMORY_BUDGET_EXCEEDED'
assert (await memory.recall(scope, '')).entries == before.entries
```

- [ ] memory_edit只允许当前用户明确偏好的可追溯来源；后台经历写成运行记录，不自动提升成USER事实。成功后刷新本Run memory scope版本；失败如实反馈。
- [ ] 新Run每次重载；run恢复时剥离旧memory块并按当前有效revision重建，测试删除后旧checkpoint不会复活该条目。
- [ ] 用户PATCH记忆执行相同版本规则，但使用用户授权而非Job lease；用户纠正与运行中写入竞争时旧version失败。用户私有记忆不能由同店另一用户读写。
- [ ] 通过真模型在会话A指定“先现金、再库存、最后建议”，新会话B采用；改为“先风险”后生效；删除后不再注入。验证实际prompt版本和输出，不只数表行。

**Verify:** agent目录运行`..\.venv\Scripts\python.exe -m pytest tests/unit/test_hermes_policy.py tests/integration/test_memory_service.py -q`；单独记录真模型M-01证据。不需要向量库、Markdown双写或安装Hermes完整应用。

## A6：持久事件、周期跟进及去重

**Files:** Create backend agent_bridge/triggers.py、tests/integration/test_agent_followups.py；Modify scheduling/dispatcher.py、产生Plan/Alert/Action/timeline事实的必要入口、agent_bridge/repository.py/router.py。

**Consumes:** A4事实读取、A5记忆；既有业务调度/事件事务。
**Produces:** 页面关闭后可持续运行、事件合并不丢后继、静默无变化周期。

- [ ] 写事务回滚不遗留Agent触发、重复source_key不重复通知、RUNNING期间新事件有后继、用户消息不合并测试。
- [ ] 给Conversation增加followup配置/version/next_due、last_fingerprint；建立agent_triggers唯一source_key。业务事件写入只登记引用，不能在B0事务里调用模型或访问agent包。
- [ ] dispatcher增加轻量到期扫描；默认300秒、最小60秒；无变化推进锚点，不创建模型Run。积压事件按conversation合并，冻结水位；最小通知间隔60秒。
- [ ] 最终发布与消费水位同事务；运行中的新触发seq大于本次水位，后继处理。Agent自身消息不触发Agent，request_check只在产生新的业务结果时形成触发。

```python
assert unchanged_tick.model_run_count == 0
assert completed_run.consumed_through_seq == captured_watermark
assert await pending_trigger_count(conversation_id) == events_arrived_during_run
assert await user_message_count(conversation_id) == submitted_user_messages
```

- [ ] followup_enabled要求operator显式设置；暂停/完成/取消按设计§9分流建议与事实通知；Agent关闭时B0仍正常，重新开启只合并应处理积压。
- [ ] backend读取接口GET不补跑任务。后台输出持久Message及引用，不实现外部IM/邮件发送。

**Verify:** backend目录运行`..\.venv\Scripts\python.exe -m pytest tests/integration/test_agent_followups.py -q`；受控时钟加真实PG覆盖周期边界，实际进程场景在A8验证。

## A7：扩展接缝、产品读取与契约对齐

**Files:** Create agent/extensions.py、tests/unit/test_extensions.py、docs/api/agent-v1.openapi.json；Modify backend agent_bridge/router.py/schemas.py、api/schemas.py、docs/api/backend.openapi.json、services.openapi.json、implementation-status.json与契约校验工具。

**Consumes:** 前述DTO、会话和工具查询、结果引用。
**Produces:** 可用API、明确已实现/未实现边界、可替换模型/只读证据/技能接口。

- [ ] 将设计§10的用户入口全部实现并做权限、幂等、分页测试；不把所有用户会话按Mission直接混排返回。
- [ ] EvidenceProvider/SkillProvider未配置时返回空集合；加入测试实现证明有来源的片段和版本化技能可进入context；其required_tools必须是实际已授权工具子集。

```python
assert await empty_evidence.search('query', scope) == []
assert set(loaded_skill.required_tools) <= set(authorized_tool_names)
assert foreign_owner_conversation_response.status_code == 404
```

- [ ] ExperienceReader基于已完成Run摘要/引用读取；不搜索原始checkpoints，不显示私有思维链。工具执行摘要只显示工具名、状态、输入概要、引用和耗时。
- [ ] 更新旧planned AgentRun/Message/ProposedAction契约；注明首版Python包执行，外部AgentHTTP仍planned；新增路由标B2元数据，不能误算成已完成B0功能。
- [ ] 导出runtime并核对每个新增operationId和字段与当前实现一致；旧前端7 GET保持兼容。文档列清有效scope、空值、时间单位、错误以及模型功能探针适用版本。

**Verify:** agent运行test_extensions.py；backend运行相应API测试、`-m app.export_openapi`和现有validate_contracts.py。契约新增校验必须检查真实注册，不能只验证设计示例。

## A8：真实端到端验收与交接

**Files:** Create backend/tools/verify_agent.py、agent/tests/fixtures/agent-v1-cases.json、docs/reports/agent-v1-test-report.md、docs/api/agent-v1-process-result.json；Update模块README、PROJECT_CONTEXT、HANDOVER。

**Consumes:** 全部首版功能、专用测试库、用户授权的模型配置。
**Produces:** 分离确定性/真实进程/真模型的完整证据。

- [ ] 在受控本机端口启动自有API、业务worker、Agent worker与simulator，记录PID/参数。先检查端口归属；不能停止现有服务。不把验收数据写入测试报告以外的凭证配置。
- [ ] 跑A-01：真模型解释有效Plan、工具轨迹可查、建议卡片来自精确Plan；关闭客户端连接后仍完成。
- [ ] 跑M-01：保存→新会话应用→纠正→删除→重启，附memory version、消息/Run ID和实际输出。加入不同用户/店铺负例。
- [ ] 跑F-01：推进受控SC01，需求变化后自动跟进；固定观测窗口无变化时不反复调用模型。审批由验收客户端使用已有用户权限执行。
- [ ] 跑R-01：双Agent worker同会话竞争；强杀图执行进程；租约过期旧写；工具受理丢响应；记忆提交后崩溃；最终发布前崩溃；取消/澄清恢复与权限撤销。
- [ ] 停止Agent/模型连接，验证B0周期同步、规划及采购核对仍推进。SC01最后精确核对现金40000分、应收20000分、现货70、在途0、预留0，采购/到货账本各2条。

```python
assert final_state.cash == 40000
assert final_state.receivables == 20000
assert (final_state.inventory, final_state.inbound, final_state.reserved) == (70, 0, 0)
assert assistant_messages_per_run <= 1
assert duplicate_memory_revisions == 0
assert stale_owner_commits == 0
```

- [ ] 真模型核心情境各观察至少3次，保存模型实际标识、prompt/graph/tool目录版本、调用次数及usage；模型语义错误单独列出，不用确定性测试通过掩盖。
- [ ] 运行agent与backend/simulator所需完整回归、Ruff、迁移漂移、OpenAPI契约检查；只在专用测试库执行清理。
- [ ] 停止本脚本创建的服务，保留验收场景/日志；交接报告区分旧186/12记录和本次实际结果，不预填测试数。

## 3. 验收覆盖映射

| 需求 | 主交付包 | 核心失败断言 |
|---|---|---|
| 真模型和有限工具循环 | A3/A4/A8 | 不兼容工具/预算耗尽明确失败 |
| 持久Run与会话隔离 | A1/A2 | 不漏消息、不跨用户、同会话无并发写 |
| checkpoint租约保护 | A0/A2 | 旧writer无法保存状态或pending writes |
| 采购权限和精确方案 | A4 | 模型无法批准，卡片金额来自Plan |
| Hermes来源与实际复用 | A0/A5 | 不借名称冒充SDK集成，函数/许可可追溯 |
| 跨会话记忆、纠正和删除 | A5/A8 | 删除后checkpoint不复活旧记忆 |
| 持续跟进 | A6/A8 | 新事件保留后继，无变化不反复调用 |
| 可替换接入内容 | A3/A7 | 未装配能力不出现在工具列表 |
| B0独立运行 | A1/A8 | Agent断网不停止同步/核对 |
| 前端/API读取与恢复 | A7/A8 | 断开重连不依赖内存会话 |

## 4. 本轮计划完成后的工作边界

本轮仅新增研究、设计、计划与脱敏协议证据；没有安装Agent依赖、运行迁移、修改backend业务实现或提交Git。第一次实现建议从A0开始，先解决官方saver与现有租约的组合风险。

每包结束检查Git diff、实际验收与说明一致，再更新任务清单。若进行提交，只精确暂存本包文件；已有前端/日志等未提交改动须保留，不使用git add .吞入无关内容。更细的代码变更以最终采用版本的接口为准，不将调研时的main源码等同于已锁定发行包。
