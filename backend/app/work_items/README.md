# 事项入口与 Agent 接入

2026-09-09。本模块承接用户主动提出的一件事，保存对话、进度、问题、结果，并关联既有备货 Mission。它不判断意图、不调用模型、不实现预测/报价算法，也不授予采购权限。现有 `agent/` 与 `agent_bridge` 的 LangGraph、任务内工具和历史会话保持原实现。

## 用户行为与职责

| 用户行为 | 平台已实现 | Agent/AI 接入方仍需实现 |
|---|---|---|
| 从“交给我一件事”说目标 | 保存原话，建立贯穿页面的事项卡 | 理解意图、确定所需信息 |
| 回答追问或改变要求 | 原事项追加消息、版本递增，旧处理租约失效 | 根据完整上下文继续，识别改口与否定 |
| 查询、试算、预测或报价咨询 | 展示有类型的文本/表格结果、依据和假设，保存历史并下载 | 真实业务工具、预测模型、报价处理及结果正确性 |
| 接回原备货工作 | 关联已有 Mission；同一用户同一 Mission 只有一个事项卡，保留原始消息 | 查上下文并选择正确的已有工作；歧义时追问 |
| 请求建立备货委托 | 展示完整条件，用户点击后调用原 create_mission；不采购 | 提出可执行、符合用户目标的 MissionCreate |
| 处理失败、断线或刷新 | 显示阻塞/中断，保留结果与原提交，租约超时可恢复 | 可用的处理进程、重试与模型预算策略 |

“处理完成”与“备货完成”分开。普通咨询可 COMPLETED；已关联 Mission 的事项不得由处理回传标记 COMPLETED。备货状态、方案、采购和到货来自原业务接口。停止本轮处理只撤销当前处理租约，不停止备货调度、不撤单；原工作区仍提供备货暂停/结束等操作。

## 记录与状态

- `work_items`：身份、店铺、原事项标题、状态/版本、摘要、下一步、待补问题、最近结果、可选 Mission 关联/待接受条件、处理租约与时间。`canonical_id` 只用于同一用户、同一店铺的事项归并。
- `work_messages`：原消息、系统接续记录、助手交付结果及模拟标识。归并不复制/改写原消息；读取关联历史，旧事项链接解析到唯一卡片。
- 幂等继续使用既有 `command_receipts`；不新增经营账本，不把预测或助手摘要写到库存/现金表。
- 状态：RECEIVED → PROCESSING → WAITING_INPUT / RESULT_READY / BLOCKED / COMPLETED。用户补充会回到 RECEIVED；用户停止为 CANCELLED。已保存旧结果仍可回看，新增要求不会抹去历史。
- 所有新增记录使用业务库迁移 `0013_work_intake`，位于 `0012_agent_progress` 之后。既有 Mission 和 Agent 会话无需回填；首次打开原任务时按用户创建关联事项。迁移不改变其调度、方案和账目。

## 公开接口（用户身份）

| 方法与路径 | 作用 |
|---|---|
| POST `/api/v1/work-items` | `{store_id, content}` 新事项；必需 Idempotency-Key |
| GET `/api/v1/work-items?store_id=...&cursor=...&limit=30` | 只列当前用户在该店铺的规范事项，分页 |
| GET `/api/v1/work-items/{id}` | 事项、关联 Mission 与连续消息/历史结果；别名返回规范事项 |
| POST `/api/v1/work-items/{id}/messages` | `{content}` 追加要求，撤销旧处理租约；幂等 |
| POST `/api/v1/work-items/{id}/control` | `{expected_version, operation: cancel或retry}`；不会停止备货或采购 |
| POST `/api/v1/missions/{id}/work-item` | 接回原备货事项；同用户同 Mission 重复打开沿用同卡 |
| POST `/api/v1/work-items/{id}/mission` | 用户接受已显示的跟进条件；必须operator、版本一致、非模拟；原事务创建 Mission、绑定事项并保存回执 |

建立 Mission 和初次业务检查属于这一显式接受动作；采购继续通过原 `/plans/{id}/decision`，保持逐笔确认、版本/hash、资金、防重复、结果不明核实等护栏。临时数量限制、预测周期、现金底线变更仍由原业务能力或后续独立实现处理；本模块不新增相应算法。

正常身份响应 `/api/v1/me.capabilities` 声明work_intake与plan_revision，生产关闭OpenAPI文档不影响入口；仅兼容旧后端时回退文档探测。

前端同源代理仅开放公开路径，不代理 `/internal/`。用户的提交在发送前以原幂等键暂存在按身份/角色/店铺隔离的 sessionStorage，收到成功回执后删除；刷新可查询并重试原提交。消息本身持久保存在后端。未发送草稿不承诺跨设备恢复。

## Agent/AI 接入协议（服务身份）

配置 `WORK_PROCESSOR_ENABLED=true` 表示部署方已接入新的事项处理服务。默认false，与原 `AGENT_ENABLED` 独立，不会启动任何模型或处理进程。配置既有 `AUTH_TOKENS` 中的 service 身份，最小使用 operator + 指定 store_ids；不得把服务凭证交给前端。

1. GET `/internal/v1/work-items?store_id=...` 取得RECEIVED或租约过期的PROCESSING事项。有限批次取最早待处理项，后续再次读取；这不是创建新任务。
2. POST `/{id}/claim`，提交 `expected_version` 和可选 `lease_seconds`（30–300，默认120），沿用本次领取的Idempotency-Key。返回 `processing_token`、最新事项和全部连续消息。
3. GET `/{id}/context?mission_cursor=...`，取得同店铺真实catalog、dashboard、分页Mission及事项上下文。既有任务、资金/库存、需求假设和数据时点从这些结构读取；不能以历史助手文本当成最新账目。接入方继续负责调用其他获授权的业务或模型能力。
4. POST `/{id}/updates`，携带最新 `expected_version`、processing_token、Idempotency-Key及下列处理结果。每次成功回传递增版本，继续PROCESSING时续租120秒；接入方下一次回传使用新版本。
5. WAITING_INPUT、RESULT_READY、BLOCKED、COMPLETED会释放租约。用户回答后重新领取同一事项。模型超时无回传时租约到期，前端显示处理中断，处理进程可重新领取。

回传字段（精确类型见[运行时OpenAPI](../../../docs/api/backend.runtime.openapi.json)中的WorkUpdate）：

| 内容 | 字段与校验 |
|---|---|
| 正在工作 | status=PROCESSING，summary/next_step；不提供虚构工具执行明细 |
| 需要补充 | status=WAITING_INPUT，question必填，保留已知目标与上下文 |
| 交付结果 | status=RESULT_READY或COMPLETED，result必填；kind为answer/analysis/forecast/quotation/brief，包含title/content及可选columns/rows/assumptions/references |
| 无法处理 | status=BLOCKED，next_step必填，解释可行下一步；不伪报成功 |
| 接回已有备货 | link_mission_id；程序验证同店铺，已绑定事项不得换另一Mission。若已存在规范卡片，归并后返回规范事项，等待重新领取综合上下文，不继续应用旧结果 |
| 建议建立备货 | mission_request=既有MissionCreate，必须RESULT_READY；只保存待核对条件，不能同时link，也不能直接采购 |
| 模拟接入 | demonstration=true；界面/消息/结果均标记模拟，禁止用它建立真实Mission；production拒绝此类更新 |

结果引用限定为可核验的同店铺store/mission/plan/action标识。平台验证引用存在及归属；不声称验证外部预测质量、模型推理或文本数字正确性。表格仅作结果展示，不写业务事实。任意URL、文件上传、文档附件、正文流和动态工具UI不在本轮实现；后续在约定中扩展，不伪装成已接入。

## 并发、恢复与权限边界

- 店铺锁在前，与已有业务锁顺序一致。事项版本和短期处理令牌防止两个处理者、过期处理者、用户改口前的处理者覆盖新进展。
- 同一领取或回传重试沿用原幂等键；同键不同内容拒绝。领取回执不延长旧租约，过期须重新读取/领取。
- 事项与业务上下文GET复用既有REPEATABLE READ只读事务，避免混读不同提交。待处理列表过滤已撤权用户，防止无法领取的旧记录堵住有效事项。
- 每次服务领取、读取上下文及回传重新核对原用户仍有该店铺权限。公开读取还校验事项所有者；知道其他人的ID不获得访问权。
- 前端遇到撤权停止事项轮询；失效事项链接只影响该事项。原提交结果未知时，其他操作不能覆盖原请求，先沿原幂等键核实。
- 已交付结果的模拟标识随原结果保留，后续不带结果的进度/追问不会把它重新标为真实。已关联Mission的事项不能再提出另一份新委托。
- 用户可以在处理中补充。新消息立即保存并撤销原租约，旧回传409；已提交的业务动作不撤销。运行中直接改采购不是本模块提供的能力。
- 建立Mission的原事务同时写入关联与回执；丢响应重放不再建立。已有同SKU活动Mission时继续使用原后端冲突约束，由Agent重新定位/关联，不绕过唯一性另建。
- 卡片以事项和关联业务数据为准；新事项对话与此前Mission Agent对话有明确入口，不把旧Run挪进新的处理协议。原会话可在“此前的任务对话”访问。

## 验证与待接入

[验证记录](../../../docs/reports/work-intake-verification.md)区分真实PG/HTTP/前端与模拟处理响应。重点覆盖无任务输入、丢响应重放、多轮澄清、处理中改口、过期租约、结果恢复/下载、旧事项关联、权限和无采购副作用。

仍待同学接入：意图分类、LangGraph编排、真实模型/预测/报价工具、事实与结果语义核验、自主跟进策略和运行预算。本轮没有完成A-01、L-01或真实模型效果验收；原业务首版缺口继续保留。
