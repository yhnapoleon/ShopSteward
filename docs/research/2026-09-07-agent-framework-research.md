# Agent 框架定向调研：LangGraph、Hermes 与 ShopSteward

日期：2026-09-07。状态：调研完成，设计建议；尚未安装依赖、实现 Agent、运行模型或验证图恢复。

用户已确认首版包含真实模型对话、受限业务工具、跨会话记忆及后台跟进；采购审批继续由现有页面/API 承接；优先使用可配置的 OpenAI 风格 API。本文按这个范围开展定向技术调研，不将历史完整 P0 的所有学习能力一起纳入。

## 1. 结论与证据边界

建议采用 LangGraph StateGraph 作为唯一推理主图，Hermes 记忆条目操作逻辑经过小范围源码适配后接 PostgreSQL；专用 Agent worker 复用 backend JobRun。首版通过 Python 包适配接入，而不是同时维护 backend 队列和 Agent HTTP 服务队列。

已核对本地实际身份、Runner、JobRun、工厂、规划发布、旧 Agent 契约及历史学习设计。当前 Agent 依赖为空；`agent_followup` 已出现在 JobType 中，但未注册 handler。公共业务查询要求 User，现有 Service 专为来源事件等入口使用，不能直接作为 Agent 读写工具凭证。

本次联网读了官方 LangGraph 文档、PyPI、Hermes 官方文档与源码。没有运行 Hermes 全套应用，没有复核所有技能管理代码，没有实际安装验证候选依赖组合。所有“建议”属于项目设计推导，不能当成上游库已提供的完整功能。

## 2. LangGraph：采用什么

| 已核实能力 | 本项目用法 | 不能据此推断 |
|---|---|---|
| StateGraph 支持状态、节点、路由及 runtime context | 明确组织业务上下文、模型/工具循环、澄清、最终结果 | 图替代现有经营规则 |
| checkpointer 与 Store 分别面向线程执行状态和跨线程数据 | 检查点存短期进度；长期记忆通过独立 MemoryService | 有检查点就有合格长期记忆 |
| AsyncPostgresSaver 提供异步 PG 持久化 | 使用现有 PG 实例，独立 checkpoint schema | InMemorySaver 能经重启保存 |
| `durability="sync"` 在下一步骤前保存 checkpoint | 首版选择可靠恢复，暂不引入 beta DeltaChannel | 外部 HTTP 与 checkpoint 获得分布式原子性 |
| `interrupt()` / `Command(resume=...)` | 需要补充任务信息时暂停、恢复 | `resume=True` 是 ShopSteward 采购批准 |

来源：[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)、[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

中断节点恢复会重新从节点开头运行，因此写操作须有稳定业务键。生产执行不暴露任意 checkpoint 回放入口。模型调用仍可能在崩溃窗口重复产生费用；保证的是本项目可观察效果的去重，不是模型调用恰好一次。

官方 Postgres 包使用 psycopg，不能传入现有 asyncpg/SQLAlchemy session 代替连接。首次部署需显式 setup；手动连接使用 autocommit 和 dict_row。应用表迁移与上游 checkpoint setup 分开管理。[Postgres 包说明](https://pypi.org/project/langgraph-checkpoint-postgres/)

额外核对了 [AsyncPostgresSaver 源码](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/langgraph/checkpoint/postgres/aio.py)：`aput` 和 `aput_writes` 均使用它自己的连接/游标；库没有识别 ShopSteward JobRun 租约的逻辑。建议通过同一 psycopg 连接的外层短事务组合租约检查与 saver 写入。此判断基于当前 main 的源码阅读，锁定发行版后的事务回滚行为必须在第一阶段实验验证。

## 3. Hermes：实际是什么，如何复用

本次从官方提交页解析并读取了固定提交的 MemoryStore 和工具入口：

- 调研基线：`693641aa8b4359c602283bdbbc14041e03bc47bc`（提交页日期 2026-09-06）。
- [固定版本 MemoryStore](https://github.com/NousResearch/hermes-agent/blob/693641aa8b4359c602283bdbbc14041e03bc47bc/tools/memory_tool_store.py)。
- [固定版本 memory_tool](https://github.com/NousResearch/hermes-agent/blob/693641aa8b4359c602283bdbbc14041e03bc47bc/tools/memory_tool.py)。
- [提交记录](https://github.com/NousResearch/hermes-agent/commit/693641aa8b4359c602283bdbbc14041e03bc47bc)。

MemoryStore 的核心是有界、经过整理的条目：两个目标 user/memory，默认字符预算 1375/2200，支持添加、替换、删除、原子批量操作和去重。条目匹配存在歧义时拒绝；容量控制按最终结果判断。默认文件存储使用锁与原子替换，加载时冻结提示快照。该实现也依赖外部 threat_patterns、utils 及 memory_tool 的路径/锁配置。

`memory_tool.py` 还依赖 Hermes 配置、全局注册与写入门控。因此没有证据支持“安装一个独立 Hermes Memory SDK 就能无缝接 LangGraph”。

建议复用矩阵：

| 上游部分 | 采用方式 | 项目改动 |
|---|---|---|
| 去重、匹配、增删改、最终预算校验 | 修改后复用必要纯逻辑，记录函数来源及改动 | 明确 entry_id、版本、来源；写入落在项目事务 |
| user/memory 两类、有界注入 | 机制与语义保留 | 增加 principal/store 隔离；每次 Run 重新加载 |
| 文件锁、全局目录、原子文件写入 | 不作为首版权威存储 | PG 为唯一权威；没有实际消费者就不额外维护 Markdown 镜像 |
| 全局 memory 工具注册器与 write_approval | 不引入 | 本项目工具目录和权限检查负责 |
| threat_patterns | 先作为行为参考；若复制则单独记录来源与测试 | 不是权限边界，不能据正则未命中就信任记忆 |
| memory_manager 的 provider hooks | 参考其生命周期和故障隔离 | 不搬后台线程与主 Agent 对象 |
| session_search | 不直接复用 | 它搜索 Hermes 会话库；项目经历检索从本项目运行记录读取 |

官方文档将持久记忆和会话搜索分开；session_search 依赖 Hermes 的 SQLite/FTS5 会话存储，不能直接搜索 LangGraph checkpoint。[Hermes Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)

一个值得保留的来源差异：文档列举了已完成工作的记忆例子，但固定提交的 memory 工具描述进一步要求将任务进度、完成日志和流程移到会话/技能。ShopSteward 采用后者的职责分离：经营历史留账本和 timeline；经历留 Run/工具记录；长期记忆只存稳定偏好及非权威背景。

`agent/memory_manager.py` 的当前实现还带 provider 工具注入、后台同步、session 切换与压缩 hook。部分注入包装使用较强的记忆权威措辞；本项目不沿用，记忆始终是有来源的参考材料。[MemoryManager 源码](https://github.com/NousResearch/hermes-agent/blob/main/agent/memory_manager.py)

Hermes 主仓库 LICENSE 当前为 MIT。本项目若抽取源码，交付时须将固定版本许可证、来源清单和修改说明一起保存；本轮固定提交 LICENSE 的单独抓取失败，实施时必须补齐同一提交的归档，不能只附 main 链接。[当前 LICENSE](https://github.com/NousResearch/hermes-agent/blob/main/LICENSE)

## 4. 模型适配

首版只承诺 Chat Completions 的已验证子集。`ChatOpenAI` 可以配置 base_url 并绑定工具，但官方集成文档明确限定标准协议；第三方 reasoning 字段等可能需要专用适配。不能因为 `/models` 或普通对话成功就宣布工具调用兼容。[ChatOpenAI 集成](https://docs.langchain.com/oss/python/integrations/chat/openai)

能力验证至少覆盖：中文文本、单次工具请求、工具结果回填、非法参数、超时、usage 缺省；结构化响应与流式为单独能力。默认只发必要字段，工具串行；不默认发送 strict、parallel_tool_calls、response_format、temperature 等未验证选项。缺少 token usage 时记录 null，不能当零成本。

用户提供的 `openai.txt` 已以不输出内容的方式核对：只有一行 Key，没有 base_url 或模型。服务归属仍在澄清，尚未向任何服务发送该 Key。该信息不影响架构与计划交付；真实兼容性结果需等地址确认后取得。

## 5. 候选版本

| 包 | 本次 PyPI 可见版本 | 状态 |
|---|---|---|
| langgraph | 1.2.11（2026-08-11） | 第一阶段锁定实验候选 |
| langgraph-checkpoint-postgres | 3.1.2（2026-08-07） | 同上 |
| langchain-openai | 1.6.0（2026-08-19） | 同上 |
| psycopg[binary,pool] | 随上述组合解析并写 uv.lock | 尚未解析，不杜撰已兼容版本 |

来源：[LangGraph PyPI](https://pypi.org/project/langgraph/)、[Postgres PyPI](https://pypi.org/project/langgraph-checkpoint-postgres/)、[模型集成 PyPI](https://pypi.org/project/langchain-openai/)。这些是调研时点的版本快照，不是已通过本项目测试的依赖组合。

## 6. 本地兼容差距

| 实际入口 | 差距 | 计划处理 |
|---|---|---|
| `backend/app/scheduling/runner.py` | 最终发布受租约保护，run 中的外部写入并不自动受保护 | checkpoint/记忆/工具分别纳入写入控制 |
| `backend/app/bootstrap.py` | 4 个业务工厂；未注册 agent_followup | 按 worker profile 注册；业务 worker 不领取模型任务 |
| `backend/app/api/dependencies.py` | User 与来源 Service，缺 Agent 调用身份 | 增加绑定 Run 的短期工具凭证 |
| `backend/app/api/schemas.py` | JobType 已预留 agent_followup | 复用；扩展结果引用时同步契约 |
| `docs/api/services.openapi.json` | Agent HTTP 占位，LLM 仅文本；allowed_tools 固定枚举 | 标明首版包适配，更新模型工具子集和工具目录 |
| `docs/api/backend.openapi.json` | 消息无会话隔离；Run 没有 WAITING_INPUT；采购建议缺精确 Plan 引用 | 增加 conversation、澄清与取消，建议绑定现有 Plan |
| 旧技术研究 | SQLite、Hermes 文件镜像及旧 Mission 状态 | 当前 PG、实际 B0 状态优先；图等待状态不改 Mission 状态 |

## 7. 检索与停止依据

第一轮核对项目源码/历史契约并查官方能力；第二轮跟读持久化、恢复、模型兼容及 Hermes 具体文件；第三轮固定 Hermes commit、核对发行版本并检查 saver 连接机制。关键设计选择已有一手依据，不继续泛搜其他 Agent 框架。

未完成的实验已明确移入实施第一阶段：依赖解析、固定版本事务组合、真实模型协议测试。Hermes skills 两个固定源码链接抓取失败，本轮仅阅读官方技能说明，后续技能写入扩展必须另做源码核验。[Skills 官方说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

配套：[架构设计](../superpowers/specs/2026-09-07-agent-framework-design.md)、[实施计划](../superpowers/plans/2026-09-07-agent-framework.md)。
