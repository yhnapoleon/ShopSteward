# 前端对接说明（按板块）

## 0. 怎么用这份文档

- **改后端**（接口、字段、枚举值、状态码、错误码、返回给界面的中文）：先在 §2.0 按路径找到用到它的板块和文件，再读该板块的"依赖与解释"和"后端改动会影响"，最后按 §3 的顺序同步。
- **改前端**：在同一个 PR 里更新本文对应板块和 §2.0 索引；新增的后端依赖或绕行写进 §4。
- **代码基线**：jeffrey 本地提交 `8a7566c`（应急补货前端第一轮）+ 合并提交 `c79e101`（合并 main `11c84d2`，含 YH 的 #25）；合并后的调整与第二轮改动（2026-10-19，redesign §18.11、§18.12）已提交为 `7f849dd`，经 PR #26 合入 main（`348ea3d`）；YH 10-19 补齐后端并按后端调整前端（redesign §18.13）。本文只写代码现在的行为；与代码不符时以代码为准，并修正本文。
- **路径写法**：
  - `app/`、`server/`、`scripts/`、`tests/`、`nuxt.config.ts`、`playwright.config.ts` 都在 `frontend/` 下。
  - 短写的 `pages/…`、`components/…`、`composables/…`、`utils/…`、`types/…`、`surfaces/…`、`assets/…` 都在 `frontend/app/` 下；`useXxx` 在 `frontend/app/composables/`。
  - 只写文件名的 `.vue` 在 `frontend/app/components/`；`space/…`、`recovery/…` 是它的子目录（`frontend/app/components/space/`、`frontend/app/components/recovery/`）。
  - `docs/api/…` 指仓库根的 `docs/`；后端文件写全路径（`backend/…`）。"redesign"指 `frontend/docs/workspace-redesign-2026-10.md`。
- **接口写法**：一律写后端路径，浏览器实际请求的是 `/api/backend` + 该路径（§1.1）。

## 1. 全局对接机制

### 1.1 请求链路与白名单

页面全部在浏览器渲染（`nuxt.config.ts`：`ssr: false`）。浏览器只请求同源的 Nitro 服务，Nitro 带上凭证转发给后端（`runtimeConfig.backendUrl`，环境变量 `NUXT_BACKEND_URL`，默认 `http://127.0.0.1:8000`）。

| 浏览器请求 | 处理文件 | Nitro 调后端 | 说明 |
|---|---|---|---|
| `GET /api/session` | `server/api/session.get.ts` | `GET /api/v1/me`（10 s）；回应没有 `capabilities` 时再 `GET /openapi.json`（5 s，不带凭证） | 返回 `Session`（§1.2） |
| `POST /api/session` | `server/api/session.post.ts` | 用提交的凭证 `GET /api/v1/me` | 凭证长度不在 12–4096 → 400；验证失败 → 401；成功写 cookie `shopsteward-session`（HttpOnly、SameSite=strict、12 小时） |
| `GET /api/health` | `server/api/health.get.ts` | `GET /health/ready`（3 s，不带凭证） | 只返回 `{ backend: 'ok' \| 'unreachable' }`；超时、拒绝连接、503 都算 `unreachable` |
| `/api/backend/<后端路径>` | `server/api/backend/[...path].ts` | 白名单内的路径 | 见下 |

`server/api/backend/[...path].ts` 按顺序执行：

1. **白名单**：`server/utils/backend-routes.ts` 列出允许的 `[方法, 路径模板]`，路径参数 `{x}` 只匹配 `[A-Za-z0-9_-]+`。不在表内 → 404 `Unknown operation`。`/dev/…` 还要求 `NUXT_DEV_TOOLS=true`，否则同样 404。
2. **凭证**：cookie `shopsteward-session`；只有开发模式且从 `localhost`、`127.0.0.1`、`[::1]` 访问时，才回退到 `NUXT_BACKEND_TOKEN`。没有凭证 → 401 `请连接后端用户身份`。
3. **SSE**：`GET /api/v1/agent-runs/{run_id}/events/stream` 交给 `server/utils/agent-progress-stream.ts` 流式转发：转发 `Last-Event-ID` 与查询参数；10 s 内没有响应头即中止；后端非 2xx 时原样返回其 JSON 与状态；连接失败 → 502 `PROGRESS_UNAVAILABLE`。
4. **文件**：`server/utils/knowledge-transfer.ts` 处理
   - `POST /api/v1/stores/{store_id}/documents`、`POST /api/v1/documents/{document_id}/versions`：要求 `multipart/form-data`（否则 415）、`Idempotency-Key` 且不超过 128 字符（否则 400）、总大小不超过 20 MiB + 128 KiB（否则 413）；
   - `GET /api/v1/documents/{document_id}/versions/{version_id}/content`、`GET /api/v1/work-items/{item_id}/quotation-files/{file_id}/download`、`GET /api/v1/work-items/{item_id}/quotation-results/{result_id}/download`：二进制原样返回，带回 `content-type`、`content-disposition`、`x-request-id`。
   - 超时 60 s；失败 → 502 `BACKEND_UNAVAILABLE`。
5. **其余请求（JSON）**：非 GET 时校验 `Origin` 同源（否则 403）、要求 `Content-Type: application/json`（否则 415）、转发 `Idempotency-Key`、请求体不超过 256,000 字节（`POST /api/v1/work-items/{item_id}/quotation-files` 为 1,300,000 字节；否则 413）。转发超时 20 s、不重试；状态码与响应体原样返回，带回 `x-request-id`，加 `cache-control: no-store`。后端没有响应 → 502，响应体为 `{"error":{"code":"BACKEND_UNAVAILABLE","message":"后端没有返回结果；采购请求可能已经受理，请核实原动作。","retryable":true}}`。

白名单的来源与增改：

- `server/utils/backend-routes.ts` 与 `app/types/backend.d.ts` 一起由 `scripts/generate-api.mjs` 从 `docs/api/backend.runtime.openapi.json` 生成，收录全部 `get`/`post`/`patch` 操作（当前 100 个），排除 `/internal/` 开头的路径。文件头写着 "do not edit"；手改后 `api:check` 报 `API contract drift`。
- 浏览器要调用新接口：后端注册路由 → 导出 OpenAPI → `api:generate`（§3）。生成器和代理都只认 GET/POST/PATCH；后端新增 PUT/DELETE 时要同时改 `scripts/generate-api.mjs` 和 `server/api/backend/[...path].ts`。
- 新的文件上传或下载路径要加进 `server/utils/knowledge-transfer.ts` 的正则；新的流式接口要在 `server/api/backend/[...path].ts` 单独分流。路径参数里出现 `[A-Za-z0-9_-]` 以外的字符（例如 `.`、`:`）会被白名单拒绝。
- 白名单里有、前端代码不调用的操作列在 §2.0 末尾。

### 1.2 身份与能力开关

`useShop().init()` 先读 `GET /api/session`，结果放在 `useShop().s.session`（类型 `app/types/models.ts` 的 `Session`）。成功时还展开了 `/api/v1/me` 的原字段（`principal_id`、`roles`、`store_scope`、`capabilities`），其中 `store_scope` 和 `capabilities` 原值界面不用。

| 字段 | 取值来源（`server/api/session.get.ts`） | 在界面上控制什么 |
|---|---|---|
| `authenticated` | `/api/v1/me` 成功为 `true` | `false` 时页面只显示"先连接后端用户身份"卡或"服务暂时中断"卡 |
| `workIntake` | `capabilities` 含 `work_intake`；没有 `capabilities` 时看 OpenAPI 是否有 `/api/v1/work-items` | `useWorkItems` 是否读取事项列表；读成功后 `work.s.available = true`。为否时：今日改显示 `TaskCard`；"系统在盯"、持续跟进列表、记录里的事项卡都不显示；委托卡与 Agent 入口进 `?view=task`（§2.16）；报价入口按钮禁用；服务状态写"事项助手 · 未接入" |
| `planRevision` | `plan_revision`；没有 `capabilities` 时看 OpenAPI 是否有 `/api/v1/plans/{plan_id}/revision` | 能否确认非推荐数量（`useShop.prepareDecision` 调 revision；`space/PlanCard.vue`、`DecisionCard.vue` 的确认按钮与提示） |
| `recoveryCases` | `operations_cases`（没有 `capabilities` 时为否） | 应急补货的全部入口、事项页的 `RecoveryFlow` 卡、今日应急卡及其计数、旧任务页的"供应异常应对"面板 |
| `sourcing` | `sourcing`（同上） | 读取供应商资料、说明步"资料在档"、确认后自动寻源、"重新找货"、演示模式自动载入示例资料、旧面板的 `SourcingPanel` |
| `quantitySimulation` | `quantity_simulation`（同上） | 页头"先试算补货"按钮；新手指引第 4 步能否试算 |
| `agentEnabled` | **前端** Nitro 配置 `NUXT_AGENT_ENABLED`，与后端能力无关 | Agent 能否发送（`useAgentConversation().enabled`）、"Agent 未启用"文案（`agentDormant()`）、对话区默认标签、记忆面板只读、服务状态"Agent" |
| `devTools` | `NUXT_DEV_TOOLS=true` 且 `roles` 含 `admin` | 今日"创建示例店铺"、联调控制弹层的创建/推进、演示条的"过一天"和"新建示例店铺" |
| `backend` | 只在失败时出现：没有凭证 → 不给；没有响应、超时或 ≥500 → `unreachable`；401/403 等 → `ok` | `useBackendHealth` 的初始判断（§1.3） |
| `roles` | `/api/v1/me` 的 `roles`（`viewer`/`operator`/`approver`/`admin`） | 见下 |

后端 `/api/v1/me` 现在固定返回六项能力（`backend/app/api/router.py`）：`work_intake`、`plan_revision`、`operations_cases`、`quantity_simulation`、`work_result_export`、`sourcing`。前端不读 `work_result_export`。失败时返回的 `Session` 没有 `recoveryCases`、`sourcing` 两个字段，按否处理。

角色：`useShop().hasRole(r)` 在 `roles` 含 `r` 或 `admin` 时为真；文档中心另用 `roles` 含 `operator` 或 `admin` 判断可写（`useDocuments.ts canWrite`）。

- 需要 `operator`：建立委托（今日开始卡、`GoalDeck` 新建）；改跟进间隔、暂停/恢复主动跟进、重新检查；标记提醒已知晓；应急补货的一切写入（`useRecoveryCase.submit` 直接拦截）；登记到货；接受事项里的委托条件；改选非推荐数量（另需 `planRevision`）；预测刷新；学习操作；Agent 主动解读开关；载入示例供应商资料。
- 需要 `approver`：确认采购（方案卡、应急确认步）；结束委托；登记供应商回复；按对方数量成交；撤回店主发出的订单。部分回复后的"撤回整单，找别家补"同时要求 `operator` 和 `approver`。应急卡在当前身份缺少某一步所需的权限时，进度标"等审批"，右下写等有相应权限的人来做。
- 试算（`QuantitySimulationPanel.vue`）和记忆修改不检查角色，由后端决定。

### 1.3 健康探测与中断

`useBackendHealth(true)`（`pages/index.vue` 持有）把"后端连不上"和"身份无效"分开：

- 状态为 `unknown | ok | unreachable`。`Session.backend` 给初值；`authenticated` 为真或任何一次业务读取成功（`s.connected`）都置为 `ok`。
- 只在需要时每 5 s 请求一次 `/api/health`：会话未认证且状态不是 `ok`，或业务读取失败（`!s.connected && s.error`）。
- 从 `unreachable` 恢复为 `ok`：已认证且已选店时只做 `shop.refresh(true)`（保留店铺与委托）；否则重新 `init()`，并按 URL 里的 `mission`/`item` 重开原视图。
- 界面：已认证但读不到数据 → "服务暂时中断"卡，写明保留了哪个时间同步的数据、期间不能确认采购，带"立即重试"；未认证且连不上 → "每 5 秒自动重试，恢复后自动继续；不需要重新连接身份"。其余错误显示 `s.error` 与"刷新状态"。

服务状态（今日右栏，`space/ServiceStatus.vue` + `useServiceStatus.ts`）：

| 项 | 判断 |
|---|---|
| 业务接口 | `s.connected` / `s.loading` |
| 事项助手 | `workIntake` 为否 → 未接入；`GET /api/v1/work-items` 的 `processor_available` 为真 → 可以处理；否则"暂不可用，要求会先保存" |
| Agent | `agentEnabled` |
| 预测服务 | 每家店每次会话探测一次 `GET /api/v1/stores/{store_id}/forecast/model`：2xx 为"运行中"，失败为"未启动"；断线恢复后重测失败过的店 |

### 1.4 生成类型与 `api:check`

- `scripts/generate-api.mjs` 读 `docs/api/backend.runtime.openapi.json`，用 `openapi-typescript` 写 `app/types/backend.d.ts`，并写 `server/utils/backend-routes.ts`。`--check` 只比较不写，不同时抛 `API contract drift: <文件>`。
- OpenAPI 文件由后端导出：在 `backend/` 下用项目虚拟环境运行 `python -m app.export_openapi`（`backend/app/export_openapi.py`，默认输出 `../docs/api/backend.runtime.openapi.json`，不连数据库）。
- 组件用 `Schema<'名字'>`（`app/types/models.ts`）取后端类型；`PlanDocument = Plan | RecoveryPlan`，用 `utils/plans.ts isRecoveryPlan()`（`plan_kind === 'recovery_v1'`）区分。
- **下列字段在 OpenAPI 里是不定结构（`{ [key: string]: unknown }`）或不在契约里，前端按自己写的类型读，`api:check` 和 `typecheck` 都发现不了后端改动。** 改这些字段时，在本文和代码里按字段名搜索，逐处核对：

| 后端字段 | 前端的读法 |
|---|---|
| `CaseDetail.sourcing` | `app/types/recovery.ts` 的 `Sourcing`、`SupplierReview`、`OfferCard`；用于 `utils/recovery.ts flowState()`、`recovery/RecoveryCompare.vue`、`SourcingPanel.vue` |
| `CaseDetail.expert_analysis` | `recovery/RecoveryCompare.vue`、`RecoveryWorkspace.vue` 内联类型（`status`、`strategy`、`subtasks[].{subtask_id, role, status, claims[].{statement, support}, missing}`、`merged.conflicts`、`merged.clarification`） |
| `GET/POST /api/v1/stores/{store_id}/forecast*` 的 `forecast`、`model`、`history` | `app/types/forecast.ts`（OpenAPI 名为 `ForecastV6Current`、`ForecastV6Model`） |
| `GET /api/v1/stores/{store_id}/learning` 的 `policy`、`progress`、`assets` | `app/types/learning.ts` |
| `RunView.tools` | `utils/agent-progress.ts runTools()`（读 `invocation_id`、`tool`、`ok`、`references`） |
| `KnowledgeView.entries` | `useAgentKnowledge.ts readItems()`（读 `id`、`content`、`required_tools`） |
| `ContextInspection.config/frames/calls/manifests` | `ContextInspector.vue` |
| `HistoricalEvidence.reference`、`MessageView.references` | `AgentReferences.vue`、`AgentConversation.vue` |
| `QuoteRule.source` | `QuotationWorkspace.vue` 读 `confirmation`、`correction_content`、`work_id` |
| `WorkResult.surface`（契约里没有） | `surfaces/derive.ts resultSurface()`：有值时经 `surfaces/validate.ts` 校验后使用，否则由结果字段推导 |
| `GET /api/v1/operations-cases` 的翻页 | 按 `{ items }` 读，不看 `next_cursor` |

### 1.5 `utils/api.ts`：调用、错误与幂等

`api<T>(path, method = 'GET', body?, key?)` 请求 `/api/backend` + `path`：不重试，超时 25 s；非 GET 一律带 `Idempotency-Key`（传入的 `key`，否则新生成 UUID）。`query(params)` 拼查询串并去掉 `undefined`/`null`。

失败时抛 `ApiFailure(code, message, status, requestId)`：

- `code`：响应体的 `error.code`；没有时为 `CONNECTION_ERROR`。Nitro 自己报的错（404 `Unknown operation`、401 无凭证、403、413、415）没有 `error.code`，也落到 `CONNECTION_ERROR`，但 `status` 是真实状态码。
- `message`：先查 `utils/api.ts` 的 `messages` 表，再用后端 `error.message`（只是错误码本身、不成句时不用）；有错误码而没有可用的句子时写"暂时没能完成，稍后再试。"；没有错误码时再用 Nitro 的 `statusMessage`，最后是"连接中断，未能取得最新结果。"。
- `status`：HTTP 状态，没有响应时为 0。`requestId` 取响应体 `error.request_id`，界面不显示。`error.retryable`、`error.details` 不读。

`messages` 表用前端文案替换这些错误码的后端文案：`LEARNING_CONTEXT_CHANGED`、`LEARNING_QUALITY_REQUIRED`、`LEARNING_FORGOTTEN`、`STATE_VERSION_CONFLICT`、`PLAN_INPUT_STALE`、`PLAN_VERSION_CONFLICT`、`PLAN_ALREADY_DECIDED`、`PLAN_EXPIRED`、`DATA_STALE`、`ACTION_IN_PROGRESS`、`ACTION_NOT_WAITING`、`MISSION_NOT_ACTIVE`、`CASH_FLOOR_VIOLATION`、`AGENT_NOT_CONFIGURED`、`FORBIDDEN`、`UNAUTHENTICATED`、`NO_PURCHASE_PROPOSED`；订单写入的 `PARTIAL_SUPPLY_NOT_OFFERED`、`GOODS_QUANTITY_CONFLICT`、`ARRIVAL_NOT_EXPECTED`、`IDEMPOTENCY_KEY_REUSED`；备货委托与供应商资料的 `RESOURCE_NOT_FOUND`、`MISSION_ALREADY_EXISTS`、`INVALID_MISSION_TRANSITION`、`MISSION_TERMINAL`、`MISSION_NOT_EDITABLE`、`SCHEDULE_VERSION_CONFLICT`、`RECOVERY_CASE_REVISION_REQUIRED`、`SUPPLIER_CONNECTED`、`DOCUMENT_ID_REPEATED`；应急事项的 `CASE_ALREADY_OPEN`、`CASE_REFRESH_REQUIRED`、`NO_OTHER_SUPPLIERS`；`INVALID_STORED_DATA`（"这件事的方案正等待确认，刷新前先确认或拒绝它。"，§4 第 1 项）、`FORECAST_NOT_FOUND`；应急方案依据变化的 `MISSION_VERSION_CONFLICT`、`OFFER_VERSION_CONFLICT`、`INBOUND_VERSION_CONFLICT`、`FORECAST_VERSION_CONFLICT`、`RECOVERY_INTENT_STALE`（都写"…刚变了，重新比价后再采用。"一类的句子）。各板块另有错误码表：`utils/recovery.ts caseProblem()`、`useDocuments.ts documentError()`、`ForecastPanel.vue failures`、`useAgentKnowledge.ts reasons`。

状态码的通用解读（各 composable 一致）：

- 401/403（多数地方连同 404）：当前身份对这块数据失效 → 清空该块数据并提示重新连接（`useWorkItems` 的 `revoke()`、`useAgentConversation` 的 `revokeAccess()`、`useRecoveryCase` 的 `accessLost()` 等）。
- 其他 4xx：后端确定拒绝 → 丢弃待核实记录，重新读取该对象。
- 5xx、502、状态 0：结果未知，写入可能已经生效 → 保留待核实记录，提供"查询/重试原提交"，重放时沿用同一个 `Idempotency-Key`。

| 写入 | 待核实记录 | 重放入口 | 清除条件 |
|---|---|---|---|
| 采购确认 `POST /api/v1/plans/{plan_id}/decision` | sessionStorage `ss.approval`：`{ storeId, planId, body, key }`（`useShop.decide`，发送前写入） | "查询原确认结果" → `useShop.recoverApproval()`，同 body 同 key | 成功；4xx；刷新时出现 `plan_id` 相同的采购单 |
| 事项写入（新建、消息、控制、接受委托、报价三类、试算） | sessionStorage `ss.work.pending:<principal>:<roles>:<store>`（`useWorkItems.submit`） | "恢复原提交""查询并重试原提交""查询并重试原试算"；存在时拒绝别的事项写入 | 成功；4xx（401/403/404 时同时 `revoke()`） |
| 应急补货 Case 写入（create/analyze/revise/materialize/control） | sessionStorage `ss.recovery.pending:<principal>:<roles>:<store>:<mission>`（`useRecoveryCase.submit`） | 事项页应急卡"再试一次（沿用刚才的提交）"（`recovery/RecoveryUnconfirmed.vue` → `useRecoveryFlow.retry()`，§2.6"写入结果不明"）与旧面板"核实并重试原提交"（§2.16）；存在时拒绝别的 Case 写入 | 成功；4xx |
| 订单写入：登记回复 `POST /api/v1/actions/{action_id}/supplier-reply`、撤回 `…/withdrawal`、按对方数量成交 `…/partial-acceptance`、登记到货 `…/arrival` | sessionStorage `ss.order-writes`：按请求路径记 `{ storeId, actionId, path, body, key, mark }`，`mark` 是发出时订单的状态、回复时间与到货数（`useShop.orderWrite()`，发送前写入） | 再做同一操作：内容相同时沿用原 key 重发，后端按第一次的结果答复，不会重复入账；内容不同时报"上一次…的结果还没确认"，要先按原内容再提交一次 | 成功；4xx；刷新时订单的 `mark` 已变（写入已生效或被别的写入超过） |
| 文档上传、新版本、编辑、归档/恢复 | sessionStorage `ss.documents.<principal>.<store>`，含文件名、大小、SHA-256（`useDocuments.save`）；浏览器不能写 sessionStorage 时拒绝提交 | "核实原提交"；刷新后要重新选择同一文件（三项都要一致） | 成功；除 401/403/404/408/429 以外的 4xx |
| Agent 消息与补充回答 | 内存 `useState('agent-workspace').submission`，刷新即失 | "查询或重试原消息" | 成功；4xx |
| 学习操作 | 内存 `useLearning().pending` | "核实并重试" | 成功；4xx |
| 跟进间隔 `PATCH /api/v1/missions/{mission_id}/schedule` | 不记录；失败后立即 `GET /api/v1/missions/{mission_id}` 读回 | 读回也失败时写"保存结果尚未核实"，给"重新核对安排" | 读回成功 |
| 其余写入 | 不记录，每次新 key | — | — |

另外：`useShop` 的命令经 `command()` 串行，`s.busy` 非空时再发命令报"请等待当前操作完成"，`s.busy` 的文字直接显示在提示条里。`waitJob(job_run_id)` 每 500 ms 读一次 `GET /api/v1/job-runs/{job_run_id}`，最多 60 次；`FAILED`/`CANCELLED` 时抛 `last_error`，超时提示"后台仍在处理，请稍后刷新；不会重复创建任务。"。

### 1.6 刷新节奏与新鲜度

| 谁 | 节奏 | 读什么 |
|---|---|---|
| `pages/index.vue` → `useShop.pollEnvironment()` | 每 2.5 s（已认证、没有命令在执行） | `GET /api/v1/stores?limit=100`；`active_store` 变了就切店并提示"模拟器已切换经营环境…"，否则 `refresh()` |
| `useShop.refresh()` | 每次轮询、每个命令之后 | 并行：`dashboard`、`catalog`、`missions`（100）、`actions`（100）、`inbounds`（100）、`alerts`（100）、`ledger-entries`（30）；再读选中委托的 `GET /api/v1/plans/{plan_id}`（`plan_id` 取委托的 `current_plan_id`）与 `GET /api/v1/missions/{mission_id}/timeline?limit=30`；同时读供应商资料 `GET /api/v1/stores/{store_id}/supplier-documents`（有 `sourcing` 时，每店一次，不阻塞刷新；失败后从 5 s 起翻倍退避，最多 5 分钟），读完给没有名称的供应商登记名称（§1.7） |
| `useWorkItems(true)` | 每 2.5 s | 已加载的每一页 `GET /api/v1/work-items`（每页 30），加上选中事项 `GET /api/v1/work-items/{item_id}` |
| `useAgentConversation(true)` | 页面隐藏 20 s；SSE 在线 10 s；本轮进行中 2.5 s；其余 5 s；另开 SSE | 会话、消息、运行（§2.5） |
| `useRecoveryFlow` | 每 2 s 检查一次：寻源中、专家分析中、货已到齐等结算、或系统在做（到货步除外）时每次都读，否则每 6 s 读一次；卡片结束后停；页面确认弹窗确认了 Case 的方案后立即读一次 | `GET /api/v1/operations-cases/{case_id}` |
| `useOverview` | 12 s（页面可见时） | §2.12 |
| `ForecastPanel.vue` | 30 s；看板 `state_version` 变化时 | `GET /api/v1/stores/{store_id}/forecast?sku_id=` |
| `PresenterBar.vue` 过一天 | 推进后每 1.2 s，最多 90 s | `GET /api/v1/dashboard`，直到 `state_version` 变化 |
| `useBackendHealth` | 需要时每 5 s | `/api/health` |

过期响应一律丢弃：`useShop` 用 `requestSeq` 和 `storeVersion`；其他 composable 用 `epoch` 加作用域键（身份、角色、店铺、委托）。换店（`selectStore`）清空全部经营状态并从头读取；`pages/index.vue` 同时关闭弹层，若在 `task`/`work` 视图则回到今日。

能否确认采购 `useShop().canDecide`：已连接；没有待核实确认（`s.pending`）；门店内没有未决采购单（任一 `QUEUED`/`EXECUTING`/`UNKNOWN`，不分委托）；委托 `ACTIVE`；方案 `PENDING_APPROVAL` 且有 `proposed_purchase`；`dashboard.freshness.status === 'FRESH'`；方案 `state_version` 等于看板 `state.state_version`；未过 `expires_at`。

页面的 `issue`（`pages/index.vue`，按顺序取第一个）：`confirmation`（有待核实确认）→ `unknown`（未决采购单为 `UNKNOWN`）→ `offline`（已选店但读取失败）→ `stale`（`freshness.status` 不是 `FRESH`）→ `expired`（方案 `EXPIRED`）→ `changed`（方案待确认但 `state_version` 落后，且没有未决采购单）。当前方案属于进行中的应急补货（待确认或已过期的应急方案，或应急卡占用的方案，`restockOwnsPlan`）时不报 `expired`、`changed`，由应急卡自己说明；`stale` 照常报。`utils/glossary.ts firstSync()`：`freshness.status` 不是 `FRESH` 且 `last_sync_at` 为空，视为新店首次同步：用蓝色"正在首次同步"提示，不计入"需要你拍板"。

### 1.7 状态词在哪里翻译

| 文件 | 函数 | 作用 |
|---|---|---|
| `utils/glossary.ts` | `statusBadge(input)` | 事项状态、委托状态、方案状态、未决采购单、在途、`business.code` → `{ label, tone }`（下表） |
| | `orderStatus(action, inbound)` | 一笔采购单的状态词（下表） |
| | `alertName(type)` | `STOCKOUT_RISK` 缺货风险、`CASH_CONSTRAINT` 现金约束、`ACTION_EXCEPTION` 采购需核实、`DATA_STALE` 数据未更新；其他原样 |
| | `storeDisplayName()`、`supplierDisplayName()`、`rememberSupplierNames()` | 店铺名（演示模式按创建时点，否则 id 尾 8 位）；供应商名（传入的名称 → 本店已登记的名称 → `supplier_001` 写成"供应商 001" → 原 id）。登记的名称来自供应商资料与寻源记录（`useShop.refresh`、`useSupplierDirectory`、`useRecoveryPrompt`）；没有名称的供应商由 `useShop.nameSuppliers()` 按角色登记为"原供应商"（委托的默认供应商）或"已对接的供应商"，资料里有真名时替换，所以"供应商 001"只在名称还没读到时短暂出现 |
| `composables/useSpace.ts` | `workBadge()`、`needsOwner()`、`watchSummary()`、`awaitsOwnerArrival()`、`agentDormant()` | 列表里一件事项的徽章、是否需要店主、一行摘要 |
| `utils/workPresentation.ts` | `workPresentation(item)`、`newerWork()` | 事项卡的状态句、说明、按钮文字、颜色、排序优先级；列表与详情按 `version` 和 `business.observed_at` 合并 |
| `utils/presentation.ts` | `actionLabel(status, channel)`、`reasonLabel(code)`、`money()`、`number()`、`when()` | 采购记录弹层、跟进卡、时间线里的采购状态；方案候选的约束原因 |
| `utils/timeline.ts` | `describeEvent()`、`timelineItems()`、`groupTimeline()`、`timelineLines()` | 委托时间线（§2.4） |
| `utils/recovery.ts` | `flowState()`、`purchasesOf()`、`againDetail()`、`blockedReason()`、`caseProblem()` | 应急补货（§2.6） |
| `utils/agent.ts` | `describeTool(name)` | Agent 工具名 → 标题、完成语、类别、要高亮的卡片 |

`statusBadge` 规则（自上而下取第一个命中）：

| # | 条件 | 标签 | 色 |
|---|---|---|---|
| 1 | 确认结果待查，或未决采购单含 `UNKNOWN`，或 `business.code === 'UNKNOWN'` | 需要处理 | amber |
| 2 | 方案 `PENDING_APPROVAL` 且可确认 | 需要你拍板 | amber |
| 3 | 事项 `WAITING_INPUT` | 需要你补充 | amber |
| 4 | 店主发出的单在等回复（`channel === 'assisted'` 且 `EXECUTING`），或 `code === 'AWAITING_SUPPLIER'` | 待供应商确认 | amber |
| 5 | 采购单 `QUEUED`/`EXECUTING`，或 `code` 为二者之一 | 正在核实采购 | blue |
| 6 | 有在途且方案不是 `PENDING_APPROVAL` | 店主自发的单在途：货到后请登记；否则：等待到货 | blue |
| 7 | 事项 `PROCESSING` | 正在处理 | blue |
| 8 | 委托 `PAUSED` | 已暂停 | gray |
| 9 | 委托 `COMPLETED`/`CANCELLED`，或事项 `COMPLETED` | 已结束 | gray |
| 10 | 事项 `CANCELLED` | 已停止 | gray |
| 11 | 事项 `RESULT_READY` 且没有委托 | 结果已出 | green |
| 12 | 委托 `ACTIVE` | 持续跟进中 | green |
| 13 | 都不中 | `business.label`，没有则"状态待核对" | gray |

`workBadge(item)` 在 `statusBadge` 前后各加几条：处理超时（`PROCESSING` 且过了 `processing_expires_at`）→ 处理中断，等待恢复（amber）；没有 `business` 时 `BLOCKED` → 需要处理、`RECEIVED` → 已收到；`business.code === 'PENDING_APPROVAL'` 当作待确认方案（`can_confirm` 且未过 `valid_until` 才算可确认）；`IN_TRANSIT` 当作有在途；关联委托的事项只把 `WAITING_INPUT`/`PROCESSING` 两种事项状态传进去；最后若 `business.needs_attention` 为真而结果不是琥珀色，改为"需要处理"。

`orderStatus(action, inbound)`（返回的 `label` 是词表键，调用方再 `t()`；`space/OrdersCard.vue` 和简报拿它和"已到货"比较）：

| 条件 | 标签 | 色 |
|---|---|---|
| `assisted` + `QUEUED` | 正在生成订单信息 | blue |
| `assisted` + `EXECUTING` | 待供应商确认 | amber |
| `QUEUED`/`EXECUTING` | 正在核实采购 | blue |
| `UNKNOWN` | 结果待核实 | amber |
| `FAILED` | 采购未成功 | amber |
| `CANCELLED` | 已取消 | gray |
| `STALE` | 原方案失效 | gray |
| 到货 `arrival_status === 'RECEIVED'` | 已到货 | green |
| 到货 `PARTIALLY_RECEIVED` | 部分到货 | blue |
| 其余 `assisted` | 货到后请登记 | blue |
| 其余 | 等待到货 | blue |

`actionLabel(status, channel)`：`assisted` 时 `QUEUED` 正在生成订单信息、`EXECUTING` 待供应商确认、`SUCCEEDED` 供应商已确认；其余 `QUEUED` 等待提交、`EXECUTING` 正在提交、`SUCCEEDED` 采购已受理、`UNKNOWN` 结果待核实、`FAILED` 未成功、`STALE` 原方案失效、`CANCELLED` 已取消；未知值原样。`reasonLabel(code)` 认 `CASH_FLOOR_VIOLATION`、`TASK_QUANTITY_LIMIT`、`MINIMUM_ORDER_QUANTITY`、`PACK_SIZE_MISMATCH`、`ARRIVAL_WINDOW_MISSED`，未知值原样。

事项业务摘要 `WorkView.business`（`WorkBusinessState`）由 `backend/app/work_items/business.py classify()` 生成，`needs_attention = priority < 40`。后端会给的 `code`：`UNKNOWN`、`AWAITING_SUPPLIER`、`QUEUED`、`EXECUTING`、`COMPLETED`、`CANCELLED`、`PAUSED`、`DATA_STALE`、`PLAN_STALE`、`STORE_BUSY`、`PENDING_APPROVAL`、`IN_TRANSIT`、`FOLLOWING`。前端按值分支的只有 `UNKNOWN`、`AWAITING_SUPPLIER`、`QUEUED`、`EXECUTING`（`statusBadge`、今日的 `activeWorks`）和 `PENDING_APPROVAL`、`IN_TRANSIT`（`workBadge`）；其余靠 `needs_attention`、`can_confirm`、`priority`、`label`、`detail`、`action_label`、`tone`、`valid_until` 显示。`workPresentation()`：`can_confirm` 且过了 `valid_until` → "方案待重新核对"（优先级 15）；`priority ≥ 40` 且事项 `WAITING_INPUT` → 显示事项的问题（优先级 30）；其余直接用 `business` 的字段；关联委托却没有 `business` → "备货状态待核对"（35）。

### 1.8 中英文

- 代码里的界面文字写中文原文；`app/i18n/en.json` 以中文原文为键、英文为值（当前 2463 条）。`t(source, values)`（`app/i18n/index.ts`）：英文界面下按去掉多余空白后的原文查表；查不到且含汉字时，再用带 `{0}` 占位的键整句匹配（给后端生成的固定句式用，只匹配整句，不替换片段）；最后代入 `values`。中文界面直接代入 `values`。`joinText(parts, 分隔)` 在英文下用空格连接。`intlLocale()` 为 `zh-CN` 或 `en-SG`。
- 语言保存在 localStorage `shopsteward.locale.v1`，其他标签页通过 `storage` 事件同步（`app/plugins/locale.client.ts`）。
- `node scripts/check-i18n.mjs` 只扫描 `app/components/**` 与 `app/pages/**` 的 `.vue` **模板**：模板文字、属性值、表达式里含汉字的字符串字面量必须在 `app/i18n/en.json` 里，键值占位符必须一致。`<script>` 里和 `.ts`（composables、utils）里的中文不检查，要自己加进 `app/i18n/en.json`。
- 后端返回、界面经 `t()` 显示的中文同样靠 `app/i18n/en.json`：`business.label/detail/action_label`、后端错误 `message`、时间线 `summary` 的固定句式、试算结果的正文行与 `next_step`。后端改了这些中文，英文界面就显示中文原文。`backend/app/work_items/business.py` 里的中文目前都有英文（含 `AWAITING_SUPPLIER` 的说明与 `action_label`"处理订单"、店主登记到货时的在途说明），后端新增或改写时要同步 `app/i18n/en.json`。
- 不翻译：用户输入、模型生成的文字、文档与报价原文、商品名。`WorkIntake.vue` 的示例按钮和 `QuotationPanel.vue` 发出的事项内容是当前界面语言的文字；`space/ClarificationCard.vue` 发出的补充句固定用中文。

### 1.9 时间与金额

| 函数 | 时区与格式 | 用在 |
|---|---|---|
| `utils/presentation.ts when()` | 浏览器本地；月/日 时:分（24 小时）；空值"尚未取得" | 绝大多数时间，包括顶栏经营时点、同步条 |
| `utils/overview.ts utcTime()` | UTC，末尾加 " UTC" | 只在经营概览 |
| `utils/overview.ts salesRange()`、`utcDay()` | UTC 日历日，查询区间 `[from, to)` | 经营概览销售 |
| `utils/recovery.ts dayOf()` | 本地，月/日 | 应急补货的到货日、缺货起始日 |
| `ForecastPanel.vue stamp()` | 本地 `YYYY-MM-DD HH:mm` | 预测证据 |
| `SkillQualityCard.vue` | 固定 `toLocaleString('zh-CN')` | 质量报告有效期 |

同一个 `simulation_time`，顶栏和同步条按本地时区显示，经营概览按 UTC 显示。应急补货的日结算时刻按经营时钟推算（`settlements(clock)`：第 i 天为 `clock + i × 24 h − 1 s`，i = 1…7）。旧面板（§2.16）的"首日结算时间"输入按 UTC 解析。日期字段 `order_message.requested_delivery_date`、`supplier_reply.delivery_date` 在 `AssistedOrderCard.vue`、`SupplierReceipt.vue` 原样显示，在 `recovery/RecoveryOrder.vue` 经 `dayOf()` 显示。

金额都是整数"分"（`*_minor`）。`money()` 按 CNY 格式化（中文显示 ¥，英文显示 CNY 代码）；`utils/recovery.ts priceOf()` 用于单价（有分时保留两位）。报价结果的 `unit_price` 等是后端给的十进制字符串，前端拼 " CNY" 显示。

### 1.10 演示模式

`useDemoMode()`：`?demo=1` / `?demo=0` 或设置里的开关，存 localStorage `ss.demo.v1`，标签页之间同步。开启后：

- 店铺名写成"示例店铺 · {时点}"：时点取该店账本 `INIT` 条目的 `simulation_time`（或 `occurred_at`），记在 `ss.store-created.v1`（`StoreSummary` 没有创建时间）；没有记录的店用 `simulation_time`。
- 顶栏按钮写"演示 · 合成数据"（关闭时"联调控制 · 合成数据"）。
- 显示演示条 `PresenterBar.vue`（§2.1）。
- 应急补货说明步：没有资料时自动 `POST /api/v1/stores/{store_id}/supplier-documents/sample`；自动载入失败时才出现"载入示例资料"链接。非演示模式不载入示例资料，也没有这个链接。
- 预测面板标题下的商品名后加"示例店铺"。

业务规则、经营时钟和数据不因开关改变；"过一天"调用的是开发推进接口。

### 1.11 浏览器存储

| 键 | 存储 | 内容 |
|---|---|---|
| `ss.store` | localStorage | 上次选中的店铺；打开页面时回到这家，除非之后又建了新的经营环境 |
| `ss.store.environment` | localStorage | 选店时的最新经营环境（`active_store`），用来判断之后是否建了新环境 |
| `ss.scenarios` | localStorage | 本浏览器创建的场景：店铺 id → 场景 run id（推进只能用这些） |
| `ss.demo.v1`、`ss.store-created.v1` | localStorage | 演示模式开关；示例店铺的创建时点 |
| `shopsteward.locale.v1` | localStorage | 语言 |
| `shopsteward.onboarding.v1:<principal>` | localStorage | 新手指引进度 |
| `ss.approval`、`ss.work.pending:*`、`ss.recovery.pending:*`、`ss.order-writes`、`ss.documents.*` | sessionStorage | 待核实写入（§1.5） |
| `ss.recovery.excluded:<case_id>` | sessionStorage | 应急补货排除的供应商列表（JSON 数组；旧版本存的单个 id 也认；§2.6） |

凭证只在 HttpOnly cookie 里，不进浏览器存储。

## 2. 按板块

### 2.0 接口 → 前端位置索引

| 接口 | 调用位置 | 板块 |
|---|---|---|
| `GET /api/v1/stores` | `useShop.init/pollEnvironment/createScenario` | 2.1 |
| `GET /api/v1/dashboard` | `useShop.refresh`；`useOverview`；`PresenterBar.vue` | 全局、2.12、2.1 |
| `GET /api/v1/catalog`、`/missions`、`/actions`、`/alerts` | `useShop.refresh` | 全局 |
| `POST /api/v1/missions` | `useShop.startMission`（今日开始卡 → `GoalDeck.vue`） | 2.2 |
| `GET /api/v1/missions/{mission_id}` | `useShop.refresh`（要打开的委托不在列表的前 100 条里时）；`pages/index.vue` 跟进间隔读回 | 2.5、2.15 |
| `POST /api/v1/missions/{mission_id}/control` | `useShop.control` | 2.3、2.5、2.15 |
| `PATCH /api/v1/missions/{mission_id}/schedule` | `pages/index.vue saveSchedule()` | 2.15 |
| `POST /api/v1/missions/{mission_id}/checks` | `useShop.requestCheck` | 2.2、2.3、2.5 |
| `GET /api/v1/missions/{mission_id}/plans` | `space/ChangeCard.vue`（`limit=2`）、`space/TimelineCard.vue`（`limit=100`）、`TaskWorkspace.vue`（两种） | 2.5、2.16 |
| `GET /api/v1/missions/{mission_id}/timeline` | `useShop.refresh/moreTimeline`；`useDecisionRecords` | 2.4、2.5 |
| `POST /api/v1/missions/{mission_id}/work-item` | `useWorkItems.fromMission`（`pages/index.vue openTask()`） | 2.1、2.2、2.5 |
| `GET/POST /api/v1/missions/{mission_id}/conversations` | `useAgentConversation` | 2.5 |
| `GET /api/v1/plans/{plan_id}` | `useShop.refresh`；`useRecoveryFlow`（Case 的方案） | 2.5、2.6 |
| `POST /api/v1/plans/{plan_id}/revision` | `useShop.prepareDecision` | 2.5 |
| `POST /api/v1/plans/{plan_id}/decision` | `useShop.decide/recoverApproval` | 2.5、2.6 |
| `POST /api/v1/actions/{action_id}/supplier-reply`、`/withdrawal`、`/partial-acceptance`、`/arrival` | `useShop.recordSupplierReply/withdrawOrder/acceptPartialSupply/recordArrival`，都经 `orderWrite()`（§1.5）（`AssistedOrderCard.vue`、`ArrivalCard.vue`、`recovery/RecoveryOrder.vue`、`recovery/RecoveryReceive.vue`、`recovery/RecoveryPurchases.vue`） | 2.5、2.6 |
| `GET /api/v1/inbounds` | `useShop.refresh`；`useOverview` | 全局、2.12 |
| `POST /api/v1/alerts/{alert_id}/acknowledgement` | `useShop.acknowledge`（提醒弹层） | 2.2 |
| `GET /api/v1/ledger-entries` | `useShop.refresh`（30 条）；`useOverview`（全量） | 2.4、2.12 |
| `GET /api/v1/sales/summary`、`GET /api/v1/sales` | `useOverview`、`BusinessOverview.vue` | 2.12 |
| `GET /api/v1/job-runs/{job_run_id}` | `useShop.waitJob` | 2.1、2.2 |
| `POST /dev/v1/scenarios`、`POST /dev/v1/scenarios/{run_id}/advance` | `useShop.createScenario/advance` | 2.1 |
| `GET/POST /api/v1/work-items` | `useWorkItems.list/send`；`QuotationPanel.vue` | 2.2–2.4、2.8 |
| `GET /api/v1/work-items/{item_id}` | `useWorkItems.load` | 2.5 |
| `POST /api/v1/work-items/{item_id}/messages` | `useWorkItems.send`（`WorkConversation.vue`、`space/ClarificationCard.vue`、结果里的快捷回答） | 2.5 |
| `POST /api/v1/work-items/{item_id}/control` | `useWorkItems.control` | 2.5 |
| `POST /api/v1/work-items/{item_id}/mission` | `useWorkItems.acceptMission` | 2.5、2.7 |
| `…/work-items/{item_id}/quotation-files`、`/quotation-results`、`/quotation-rule` 及两个 `download` | `QuotationWorkspace.vue`、`QuotationUpload.vue` | 2.8 |
| `GET /api/v1/work-items/{item_id}/results/{result_id}` | `WorkResult.vue`（保存结果） | 2.5、2.7 |
| `POST /api/v1/stores/{store_id}/simulations` | `QuantitySimulationPanel.vue` | 2.7 |
| `GET/POST /api/v1/operations-cases`、`GET …/{case_id}`、`POST …/{case_id}/analyze`、`/revise`、`/materialize`、`/control`、`/source` | `useRecoveryCase`、`useRecoveryPrompt`、`useRecoveryFlow`、`RecoveryWorkspace.vue` | 2.6、2.2、2.16 |
| `GET /api/v1/stores/{store_id}/supplier-documents`、`POST …/sample` | `useShop.refresh`（经 `fetchDirectory`）、`useSupplierDirectory`、`SourcingPanel.vue` | 全局、2.6、2.16 |
| `GET /api/v1/stores/{store_id}/forecast` | `ForecastPanel.vue`；`useRecoveryFlow.open()`；`useRecoveryPrompt`（每店每商品一次） | 2.10、2.6、2.2 |
| `GET /api/v1/stores/{store_id}/forecast/model` | `ForecastPanel.vue`；`useServiceStatus` | 2.10、2.2 |
| `POST /api/v1/stores/{store_id}/forecast/refresh` | `ForecastPanel.vue` | 2.10 |
| `GET/POST /api/v1/stores/{store_id}/agent-knowledge` | `useAgentKnowledge` | 2.9 |
| `GET/POST /api/v1/conversations/{conversation_id}/messages`、`PATCH …/followup` | `useAgentConversation` | 2.5 |
| `GET /api/v1/agent-runs/{run_id}`、`POST …/resume`、`POST …/cancel`、`GET …/events/stream` | `useAgentConversation` | 2.5 |
| `GET /api/v1/agent-runs/{run_id}/evidence` | `AgentReferences.vue` | 2.5 |
| `GET /api/v1/agent-runs/{run_id}/context` | `ContextInspector.vue` | 2.13 |
| `GET/POST /api/v1/stores/{store_id}/documents`、`GET/PATCH /api/v1/documents/{document_id}`、`GET/POST …/versions`、`POST …/control`、`GET …/versions/{version_id}/content` | `useDocuments`、`DocumentCenter.vue` | 2.11 |
| `GET /api/v1/documents/{document_id}/versions/{version_id}`（及 `/content`） | `AgentReferences.vue`（核对后下载历史原件） | 2.5 |
| `GET /api/v1/stores/{store_id}/learning`、`PATCH …/policy`、`POST …/assets/{asset_id}/evaluations`、`/transitions`、`POST …/forget` | `useLearning` | 2.13 |
| `GET /api/v1/text-bundles` | `TextBundleLineage.vue` | 2.13 |

在白名单里、前端代码不调用：`GET /api/v1/actions/{action_id}`、`GET /api/v1/agent-runs/{run_id}/events`（非流式）、`GET /api/v1/operations-cases/{case_id}/events`、`POST /api/v1/stores/{store_id}/supplier-documents`、`GET /api/v1/monitoring/status`、文档索引与发布（`POST …/versions/{version_id}/index-jobs`、`GET …/index-jobs/{request_id}`、`POST …/index-jobs/{request_id}/retry`、`POST …/publications`）、学习应用（`GET …/learning/applications`、`POST …/applications/{application_id}/feedback`、`GET …/learning/assets/{asset_id}`）。`GET /api/v1/me` 与 `/health/*` 由 Nitro 直接调后端，经白名单的那一份不用。

### 2.1 顶栏与导航

**用户看到/能做**
- 顶栏：品牌、三项导航（今日、持续跟进、经营记录；今日带"需要你拍板"计数）、有选中委托时的 Agent 入口、记忆入口、设置、店铺按钮（打开联调控制弹层）。手机：底部三项导航、浮动设置与 Agent 入口。
- 二级栏（经营概览、文档中心以外的视图）：面包屑、"演示 · 合成数据"或"联调控制 · 合成数据"按钮（打开联调控制）、经营时点、设置。
- 联调控制弹层：切换可访问的店铺、返回当前经营环境；有 `devTools` 时"创建新的 SC-01 场景""推进下一个经营事件"；"学习与经验"链接；"更换后端用户身份"。连接身份弹层：输入后端凭证。
- 演示条（演示模式、桌面宽度）：过一天、新建示例店铺、切换店铺、经营概览、经营时点。提示条：`s.notice`（4 秒后消失）或 `s.busy` 的进行中文字。

**组件与状态**：`pages/index.vue`（`view`、`navigate()`、`openTask()`、`connect()`、`decisionCount`，弹层 `controls`/`connection`）、`PresenterBar.vue`、`MemoryEntry.vue`（§2.9）、`composables/useShop.ts`（`init`、`pollEnvironment`、`selectStore`、`createScenario`、`advance`、`waitJob`）、`useDemoMode.ts`、`useSpace.ts agentDormant()`、`useAgentConversation.ts status`。路由参数：`view`（`today`、`following`、`journal`、`overview`、`documents`、`task`、`work`、`learning`，其他值按 `today`）、`store`（首次加载优先选这家）、`mission`（task 视图）、`item`（work 视图）、`panel`（`agent` 时打开对话区）、`demo`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/session`（Nitro） | 首次加载、重连后 | `Session` |
| POST | `/api/session`（Nitro） | 连接身份 | `{ token }` |
| GET | `/api/v1/stores?limit=100` | 店铺列表；每 2.5 s 发现新环境 | `items[].store_id`、`items[].simulation_time`、`active_store` |
| POST | `/dev/v1/scenarios` | 创建示例店铺 | `{ scenario: 'SC01' }` → `job_run_id` |
| POST | `/dev/v1/scenarios/{run_id}/advance` | 推进一个经营事件、过一天 | `{ steps: 1 }` → `job_run_id` |
| GET | `/api/v1/job-runs/{job_run_id}` | 等后台任务 | `status`、`last_error`、`result.references[]`（`type` 为 `store`、`scenario`） |
| POST | `/api/v1/missions/{mission_id}/work-item` | Agent 入口（`work.s.available` 时） | `{}` → `WorkDetail.item.id`，然后进 `?view=work&item=…&panel=agent` |
| GET | `/api/v1/dashboard?store_id=` | 过一天后等状态版本 | `state.state_version` |

**依赖与解释**
- 店铺选项：非演示写"当前环境/历史场景"（`store_id` 是否等于 `active_store.store_id`）+ id 尾 8 位 + `simulation_time`；`active_store` 不在 `items` 里时补到列表最前。`active_store` 变化即自动 `selectStore()`。
- 创建：从任务结果的 `references` 取 `type: 'store'` 与 `type: 'scenario'` 的 id，缺一个就报"初始化回执缺少店铺或场景引用"；场景 id 记进 `ss.scenarios`。推进只对有记录的店可用（否则"此场景没有本浏览器的控制记录"）。
- 计数 `decisionCount` = 需要店主的事项数 + 1（委托卡可确认，或有计入的 `issue`）+ 1（应急卡显示时）（§2.2）。
- Agent 入口文案：`agentDormant()`（`agentEnabled` 为否且本委托没有运行和消息）→"Agent 未启用"；本轮进行中或同步出错 → `useAgentConversation().status`；否则"Agent 工作区"。
- 过一天：推进成功后轮询看板直到 `state_version` 变化（最长 90 s），再按新的账本条目写一句：`GOODS_RECEIVED` → 在库 +N；`SALE_RECORDED` → 售出 N 件、待结算 +¥；`DEMAND_REVISED` → 需求前 → 后（前值取推进前看板的 `remaining_demand`，后值取看板，缺时用 `remaining_demand_after`）；`PURCHASE_ACCEPTED` → 采购已受理；其他 → 经营数据已更新。推进失败时，`last_error` 匹配 `Worker handler did not complete|后台任务未完成` 就改写为"这一步没有推进…"。

**后端改动会影响**
- `StoreList`（`items`、`active_store`）与 `StoreSummary.simulation_time`：店铺切换、演示店名、发现新环境。
- `/dev/v1/scenarios` 的请求体与 `ScenarioAccepted.job_run_id`；`JobRun.status` 取值（`SUCCEEDED`/`FAILED`/`CANCELLED`）与 `result.references` 的类型名：`createScenario`、`advance`、`waitJob`。
- 推进失败的 `last_error` 文字：演示条的失败说明。
- `LedgerEntryView.effect_type`、`changes.*`、`remaining_demand_after`：过一天的结果句。

**已知限制或待后端配合**
- 店铺列表只读第一页 100 条。
- `StoreSummary` 没有 `scenario_run_id`、`created_at`：只能推进本浏览器创建的场景；示例店名的时点来自账本并只记在本浏览器（§4）。
- `JobRun.error_code` 在契约里，前端不读。待核实：后端是否为"没有可推进的事件"等情况填写可区分的码（前端代码看 `composables/useShop.ts waitJob()`、`components/PresenterBar.vue failure()`）。

### 2.2 今日页

**用户看到/能做**
- 页头：标题、"先试算补货"（`quantitySimulation` 且已选店）、"交给我一件事"（打开 `GoalDeck`）。
- "需要你拍板"（带计数）：需要店主的事项卡；应急补货提醒卡；当前委托没有对应事项时的委托卡；新店首次同步卡或"需要处理"卡；都没有时一行"现在没有需要你拍板的事。"。
- "系统在盯"：其余进行中的事项，一项一行；"查看更早事项"。
- 开始：事项助手可用、没有委托也没有事项时直接显示一句话交代（`WorkIntake`），助手不可用时折叠；没有店铺时"创建示例店铺"卡；有店无委托时"开始备货跟进"卡（打开 `GoalDeck`）。
- 下方：已结束的委托（折叠）、"N 项经营提醒，查看依据"（提醒弹层：标记已知晓、找别家补）、资料与简报（文档中心、整理一份供应商报价、本次经营简报）、七日预测（§2.10）。
- 右栏：事实条、"店铺此刻"（可用现金、底线刻度、在库/采购在途/待结算、数据时间）、"本次经营范围"、紧凑同步条、服务状态（§1.3）。

**组件与状态**：`pages/index.vue`（`activeWorks`、`decideWorks`、`watchWorks`、`taskCardShown`、`issue`、`attention`、`decisionCount`、`todayStarted`、`restockable()`、`restockFrom()`、`briefing()`）；`WorkCard.vue`、`space/WatchList.vue`、`space/WorkRow.vue`、`TaskCard.vue`、`useTaskPresentation.ts`、`recovery/RecoveryPrompt.vue` + `useRecoveryPrompt.ts`、`WorkIntake.vue`、`GoalDeck.vue`、`BusinessFacts.vue`、`space/SyncStrip.vue`、`space/ServiceStatus.vue`；`useSpace.ts`（`needsOwner`、`workBadge`、`watchSummary`）。

**调用的接口**（另有 §1.6 的全局读取）

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/work-items?store_id=&limit=30&cursor=` | 事项列表 | `items[]`（`WorkView`）、`next_cursor`、`processor_available` |
| POST | `/api/v1/work-items` | 交给我一件事 | `{ store_id, content }` → `WorkDetail`，随后打开该事项 |
| POST | `/api/v1/missions` | `GoalDeck`"按以上条件开始" | `{ store_id, sku_id, objective, policy: { cash_floor_minor: 30000, candidate_quantities: [0, 20, 40, 80], supplier_id }, check_interval_seconds: 30 }`；同商品已有 `ACTIVE`/`PAUSED` 委托时不新建，改为打开它 |
| POST | `/api/v1/missions/{mission_id}/work-item` | 打开委托卡、已结束的委托 | `{}` → `WorkDetail` |
| GET | `/api/v1/operations-cases?store_id=` | 应急卡判断有无进行中的应急补货（今日页每次挂载读一次） | `items[]`（`CaseDetail`） |
| POST | `/api/v1/alerts/{alert_id}/acknowledgement` | 标记已知晓 | `{}` |
| POST | `/api/v1/missions/{mission_id}/checks`，再 `GET /api/v1/job-runs/{job_run_id}` | `issue = expired` 时"重新检查" | `{}` → `job_run_id` |
| POST | `/api/v1/plans/{plan_id}/decision` | `issue = confirmation` 时"查询原确认结果" | 原请求体、原 `Idempotency-Key` |

**依赖与解释**
- 进行中事项 `activeWorks`：`business.needs_attention`；或 `business.code` 为 `QUEUED`/`EXECUTING`；或状态为 `RECEIVED`/`PROCESSING`/`WAITING_INPUT`/`BLOCKED`；或关联委托未结束（没有委托时事项未结束）。按 `workPresentation().priority` 升序。
- 分栏：`needsOwner(item)`（`business.needs_attention` 或 `business.can_confirm`，或状态 `WAITING_INPUT`/`BLOCKED`）进"需要你拍板"，其余进"系统在盯"。
- 行内摘要 `watchSummary()`：有委托时，时间取最早一笔在途的 `expected_arrival_at`（没有到货时间写"到货时间待供应商确认"）、暂停、或 `schedule.next_run_at`；"最近变化"只对 `useShop` 当前选中的委托计算（时间线里非例行的用户动作、采购、提醒，与账本 `GOODS_RECEIVED` 按采购单 id 匹配的到货比新旧）。没有委托时写"最近更新"与 `workPresentation()` 的说明。徽章 `workBadge(item, now, awaitsOwnerArrival())`（§1.7）。
- 委托卡 `TaskCard`：只在当前委托没有对应事项时显示；状态来自 `useTaskPresentation()`；可确认时显示建议数量、支出、采购后现金、预计到货。
- "需要处理"卡按 `issue`：`confirmation` → 查询原确认结果；`expired` → 重新检查；其余 → 刷新原记录。首次同步（`firstSync`）显示蓝色卡。
- 应急卡 `RecoveryPrompt`：需要 `recoveryCases`、`operator`、`work.s.available`，`utils/recovery.ts recoveryTrigger()` 给出原因，且店里没有这项委托的未结束 Case（与 §2.6 同一个 `flowState().ended` 判断）。标题是"{原因}：不补的话 7 天缺 N 件"：缺口用 `projectWithout()` 推演不补货的七天，需求与说明步相同（`demandFrom()`，有可用日预测时用日预测；预测由 `GET /api/v1/stores/{store_id}/forecast?sku_id=` 每店每商品读一次），推演不了时用 `trigger.gap`；标签与标题同词（如"现金不够""常规方案买不了"）。读 Case 列表时也登记寻源读出的供应商名称。点"找别家补"把请求交给 `useRecoveryLaunch` 并打开事项页。
- 提醒弹层：列出非 `RESOLVED` 的提醒（标题按 `type`，正文 `summary`，`last_seen_at`，`ACKNOWLEDGED` 写"已知晓，尚未解除"）；`OPEN` 的可标记已知晓（`operator`）；`STOCKOUT_RISK`/`CASH_CONSTRAINT` 且委托 `ACTIVE` 时可"找别家补"（次按钮；原因 `stockout`/`cash`，缺口取 `facts.shortage_qty`）。链接上的计数只数 `OPEN`。
- 经营简报：浏览器里用已读取的数据拼成文本（看板、库存、本委托的采购单与到货、待确认方案、事项与 Agent 的待补充问题、最近 8 行时间线），可保存为 txt，不调接口。
- 右栏底线刻度用 `mission.policy.cash_floor_minor`，没有委托时按 30000 分；有未决采购单时写"采购正在核实"。

**后端改动会影响**
- `WorkView`/`WorkBusinessState` 的字段与 `code` 取值、`WorkList.processor_available`：分栏、排序、徽章、文案（§1.7）。
- 建委托的默认条件写死在前端：`useShop.startMission()`（底线 30000、候选 `[0, 20, 40, 80]`、间隔 30 s、目标文字）、`GoalDeck.vue`（显示 30000 与 30 s）、开始卡"建议现金底线 ¥300"。后端改默认值时三处一起改。
- `Alert.type/status/facts.shortage_qty/mission_id`：提醒弹层与应急入口。
- `Action.status/channel/created_at/supplier_reply.outcome/purchase_snapshot.supplier_id`、`InboundItem.remaining_quantity/is_overdue/expected_arrival_at`、`Plan.candidates[].shortage_qty`、`Plan.proposed_purchase`：应急卡的触发判断与行内摘要。
- `Dashboard.last_check_at`、`freshness`：简报、首次同步判断。

**已知限制或待后端配合**
- "系统在盯"的最近变化只覆盖当前选中的委托；到货只看最近 30 条账本（委托时间线没有到货事件，§4）。
- 应急卡的触发原因与缺口由前端推断（§4）。
- 简报只覆盖已读取的 30 条时间线。

### 2.3 持续跟进页

**用户看到/能做**：全部事项（需要店主的排前，已结束的折叠）；当前委托没有对应事项时显示"我在跟进"卡：正在等什么、最近检查、下一次检查、预计到货（逾期标注）；暂停/恢复跟进、查看采购与到货记录、查看委托、重新检查。下方资料与简报、预测，右栏同今日。

**组件与状态**：`space/FollowingList.vue`（`isEnded`：不需要店主且委托或事项已结束）、`space/WorkRow.vue`、`FollowUpCard.vue`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/work-items` | 列表（同 §2.2） | |
| POST | `/api/v1/missions/{mission_id}/control` | 暂停（经暂停弹层）、恢复 | `{ operation: 'pause' \| 'resume', expected_mission_version }` |
| POST | `/api/v1/missions/{mission_id}/checks` | 重新检查 | `{}` → `job_run_id`，再 `waitJob` |

**依赖与解释**："正在等"依次看：未决采购单 → `actionLabel(status, channel)`；委托暂停；可确认；在途件数；方案 `REJECTED` → "出现新事实后再评估，当前取舍保持"；其余"下一次经营变化，活动未自动结束"。最近检查取 `dashboard.last_check_at`；下一次检查取 `mission.schedule.next_run_at`（非 `ACTIVE` 写"已暂停或结束"）；预计到货列出 `remaining_quantity > 0` 的在途与 `is_overdue`。

**后端改动会影响**：`Mission.status/mission_version/schedule.next_run_at`；`MissionControl.operation` 取值；`Dashboard.last_check_at`；`Plan.status` 的 `REJECTED`；`InboundItem` 字段。

**已知限制或待后端配合**：跟进卡只对 `useShop` 当前选中的一个委托。

### 2.4 经营记录

**用户看到/能做**：全部事项卡；三个标签——"经营变化"（当前委托时间线，例行检查折叠，可加载更早）、"我的决定"（只看用户动作，可加载更早）、"经营账本"（最近 30 条账本）。

**组件与状态**：`pages/index.vue`（`recordFilter`、`recordRows`）、`useDecisionRecords.ts`、`utils/timeline.ts`、`WorkCard.vue`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/missions/{mission_id}/timeline?limit=30&cursor=` | 经营变化；"加载更早记录"（`useShop.moreTimeline`） | `items[].{type, summary, actor_type, references, created_at}`、`next_cursor` |
| GET | 同上 | 我的决定：逐页读，直到找到 10 条 `actor_type === 'USER'`、没有下一页或这一轮读满 10 页 | 同上 |
| GET | `/api/v1/ledger-entries?store_id=&limit=30` | 经营账本（用全局读取的那份） | `effect_type`、`changes.{cash_delta_minor, on_hand_delta, in_transit_delta, receivables_delta_minor}`、`opening_state.cash_minor`、`simulation_time`/`occurred_at` |

**依赖与解释**
- 账本类型：`INIT` 场景初始化、`PURCHASE_ACCEPTED` 采购已受理、`GOODS_RECEIVED` 到货已核实、`SALE_RECORDED` 销售已记录、`DEMAND_REVISED` 需求已修订。
- 时间线翻译 `describeEvent()`：按 `type` 分支，再用正则读 `summary`；读不出时原样显示。

| `type` | 前端认得的 `summary` | 显示 |
|---|---|---|
| `MISSION_CREATED` | 任意 | 建立备货委托 |
| `MISSION_CONTROLLED` | `pause`、`resume`、`complete`、`cancel` | 已暂停主动跟进、恢复主动跟进、结束委托、取消委托 |
| `PLAN_CREATED`、`PLAN_REVISED` | `推荐采购{n}件；预计支出{分}分，采购后可用现金{分}分，剩余缺口{n}件。`；`当前候选均不满足采购约束，未提出采购。` | 新方案（或"方案已修订"）：建议补 n 件 · 支出 · 采购后现金 · 缺口；不补货且没有缺口的算例行 |
| `PLAN_DECIDED` | `approve`、`reject` | 你确认了采购、你选择本轮不采购 |
| `CHECK_REQUESTED` | `{原因}（任务…）`；原因为 `Manual check` 时不显示 | 你要求重新检查 |
| `CHECK_COMPLETED` | `检查{STATUS}：{结果}（任务…）`；结果认 `Candidate comparison saved`、`Existing valid plan reused`（例行）、`Mission inactive or an action is pending`、`Recovery plan awaits explicit approval`、`Recovery purchase is unresolved`、`PLAN_INPUT_EXPIRED`、`Inputs changed; a follow-up check was requested`、`Previously rejected intent suppressed`，以及 `INCONCLUSIVE` 时的原因 `MISSION_NOT_FOUND`、`MISSION_INACTIVE_OR_ACTION_PENDING`、`DATA_STALE`、`FORECAST_UNAVAILABLE`、`INPUT_UNAVAILABLE`、`OFFER_EXPIRED`、`INBOUND_STATE_MISMATCH`、`INVALID_FORECAST_OR_OFFER`；`STATUS` 只定颜色（`HEALTHY` 绿，`ANOMALY`/`INCONCLUSIVE`/`SKIPPED` 灰） | 检查完成：…；其他结果写"检查完成：{原文}" |
| `ALERT_OPENED`、`ALERT_ESCALATED` | `{TYPE}：{说明}` | 发现{提醒名}：{说明} |
| `ALERT_RESOLVED` | `{TYPE}：…` | {提醒名}已解除（例行） |
| `ALERT_ACKNOWLEDGED` | `已知晓{TYPE}；…` | 你已知晓{提醒名} |
| `ACTION_EXECUTING`、`ACTION_SUCCEEDED` | 任意 | 采购单已发出，资金已预留；供应商已受理采购 |
| `ACTION_UNKNOWN`、`ACTION_FAILED`、`ACTION_CANCELLED`、`ACTION_STALE` | 原因码 `SUPPLIER_REJECTED`、`SUPPLIER_PENDING`、`RECEIPT_CONFLICT`、`INVALID_SOURCE_RESPONSE`，或其他文字 | 采购结果待核实、采购未成功、采购已取消、原方案失效，并附原因 |

- 合并与折叠：结果为 `Candidate comparison saved` 的检查，与它之后 5 s 内、4 条以内、引用同一 `plan`（`references[type='plan']`）的方案条目合成一行（"由检查生成"）；连续的例行条目、连续同标题的系统条目各折叠成一行；用户动作（`actor_type === 'USER'`）不折叠。简报和事项页时间线卡用同一套翻译。

**后端改动会影响**：时间线 `type` 新增或改名、`summary` 句式（含中文标点和单位"分"）、`actor_type`、`references` 结构；账本 `effect_type` 与 `changes` 字段名。改句式时同步 `utils/timeline.ts` 的正则和 `app/i18n/en.json` 里对应的模板键。

**已知限制或待后端配合**
- 经营账本标签只显示最近 30 条，没有加载更多（`useShop` 存了 `ledgerCursor` 但没有使用）；两个时间线标签只对当前选中的委托。
- 时间线没有结构化参数，只能解析固定句式（§4）。`backend/app/planning/jobs.py` 写出的检查结果与 `backend/app/planning/snapshot.py` 的 `prepared.reason` 目前都已登记（见上表）；后端新增的结果没登记时显示为"检查完成：{原文}"。

### 2.5 事项工作区（`?view=work&item=…&store=…[&panel=agent]`）

进入方式：`pages/index.vue openWork(id)` → `useWorkItems.select(id)` 读事项，事项有 `mission_id` 时 `useShop.selectMission()` 切到那个委托，再写 URL。`openTask(missionId)` 在事项可用时先 `POST /api/v1/missions/{mission_id}/work-item` 取得事项。

**用户看到/能做**（左栏自上而下，事项关联委托时；没有委托的事项只有同步条（有试算或委托条件时）、事项内容、页脚和事项对话）

| 部分 | 组件 | 内容与操作 |
|---|---|---|
| 页头与状态徽章 | `space/SpaceHeader.vue`、`useSpace().badgeFor()` | 返回今日；眉标"备货委托 · 商品名"或"我的事项"；标题 `item.title`；徽章；"应急补货"入口（§2.6）；委托详情、暂停/继续主动跟进、结束（`approver`） |
| 事实摘要 | `space/SpaceWorkspace.vue` | 可用现金（断线时"上次现金"）、在库/在途、查看来源 |
| 应急补货卡 | `recovery/RecoveryFlow.vue` | §2.6 |
| 同步条 | `space/SyncStrip.vue` | 经营时点、数据同步时间、"已同步/后台正在同步/连接中断，显示上次数据" |
| 到货登记 | `ArrivalCard.vue` | 店主自己发出、供应商已确认、还有未到数量的订单（进行中的应急补货持有的采购除外，由应急卡登记）：标签"货到后请登记"，标题"{供应商} N 件"，预计到货与到货进度，填本次到货件数后"登记到货"；没有操作权限时写"等有操作权限的人登记到货" |
| 需要处理 | `space/IssueCard.vue` | 有 `issue` 且委托未结束时；查询原确认结果、重新检查（`expired`、`changed`）或刷新；应急补货进行中（`quiet`）按钮降为次按钮 |
| 方案变化 | `space/ChangeCard.vue` | 方案 vN → vN+1 · 原因；建议补货与剩余需求的前后值、已执行采购、这次只补缺口 |
| Agent 结果提示 | `space/SpaceWorkspace.vue` | 页面打开期间 Agent 新给出的试算/修订结果；"查看结果"跳到对话区 |
| 方案位 | `AssistedOrderCard.vue`、常规方案一行、`space/PlanCard.vue`、`space/OutcomeCard.vue` | 有 `issue` 时不显示。依次为：店主待发的订单（复制订单信息、粘贴回复、撤回；应急补货进行中按钮降为次按钮）；应急补货进行中时的常规方案一行；可确认的方案（选数量、比较全部候选、查看依据、核对采购）；都没有时写委托在等什么 |
| 采购与到货 | `space/OrdersCard.vue` | 每笔采购单（新的在上）：件数·金额·供应商·状态·预计到货（逾期标注）·到货进度；部分成交（`SUCCEEDED` 且 `receipt.quantity < quantity`）时件数与金额取回执，供应商后注明"订单 n 件"；展开看编号、提交时间、供应商回执、原因；最新一笔 `FAILED` 时"找别家补" |
| 经营事实 | `space/FactsCard.vue` | 可用现金、在库、采购在途、待结算、同步时间 |
| 跟进安排 | `FollowUpCard.vue` | 同 §2.3 |
| 事项内容 | `space/WorkContent.vue` | 报价（§2.8）、澄清卡、进展说明、结果（`WorkResult.vue`；关联委托时折叠为"这次讨论的结果"）、"开始持续跟进这项备货"（委托条件） |
| 时间线 | `space/TimelineCard.vue` | 最近 6 行（§2.4 的翻译）、更早记录、历次方案与决定、保存经营简报 |
| 页脚 | `space/SpaceWorkspace.vue` | 停止本轮处理（`RECEIVED`/`PROCESSING`/`WAITING_INPUT`）；重新处理这件事（`BLOCKED`/`CANCELLED` 或处理超时）；结束这项委托（`approver`，没有未结采购单、Agent 不在运行） |
| 对话区 | `space/ConversationPanel.vue` | "Agent 对话"（`AgentWorkspace.vue`：运行状态、工具过程、业务成果、上下文记录、`AgentConversation.vue`）与"事项对话"（`WorkConversation.vue` + `QuotationUpload.vue`）；两者都保持挂载 |
| 弹层 | `pages/index.vue` | `approval` 核对这笔采购、`compare` 比较补货候选、`evidence` 当前选择的依据、`receipt` 采购与到货记录、`mission`、`pause`、`complete`、`facts`、`brief`、`alerts` |

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/work-items/{item_id}` | 读事项（每 2.5 s） | `item`（`WorkView`）、`messages[]`；404 → "无法读取这件事" |
| POST | `/api/v1/missions/{mission_id}/work-item` | 从委托进入 | `{}` → `WorkDetail` |
| POST | `/api/v1/work-items/{item_id}/messages` | 事项对话、澄清卡、结果快捷回答 | `{ content }` → `WorkDetail` |
| POST | `/api/v1/work-items/{item_id}/control` | 停止、重新处理 | `{ operation: 'cancel' \| 'retry', expected_version }` |
| POST | `/api/v1/work-items/{item_id}/mission` | 按事项给的条件开始跟进 | `{ expected_version }`；条件来自 `item.mission_request` |
| GET | `/api/v1/work-items/{item_id}/results/{result_id}` | 保存结果（txt/csv/json） | `WorkResultExport`；路径取 `result.provenance.work_id/result_id` |
| GET | `/api/v1/plans/{plan_id}` | 当前方案（全局读取） | `Plan` 或 `RecoveryPlan` |
| GET | `/api/v1/missions/{mission_id}/plans?limit=2` | 方案变化卡找前一版 | `items[].{plan_version, state_version, proposed_purchase.quantity, candidates[], input_snapshot.forecast.remaining_demand, input_snapshot.task_constraints.max_purchase_qty}` |
| GET | `/api/v1/missions/{mission_id}/plans?limit=100&cursor=` | 历次方案与决定（展开时） | `items[].{status, plan_version, proposed_purchase, created_at}`、`next_cursor` |
| POST | `/api/v1/plans/{plan_id}/revision` | 选了非推荐、非 0 的数量后核对 | `{ expected_mission_version, max_purchase_qty }`（所选大于推荐时传 `null`）→ 新 `Plan` |
| POST | `/api/v1/plans/{plan_id}/decision` | 确认弹窗提交 | `{ decision: 'approve' \| 'reject', expected_plan_version, expected_state_version, proposal_hash }`（不传 `channel`）→ 202 `DecisionApproved` 或 200 `DecisionRejected` |
| POST | `/api/v1/missions/{mission_id}/control` | 暂停、继续、结束 | `{ operation, expected_mission_version }` |
| POST | `/api/v1/missions/{mission_id}/checks` | 重新检查 | `{}` |
| POST | `/api/v1/actions/{action_id}/supplier-reply` | 登记供应商回复 | `{ text }` → `Action`（含 `supplier_reply`） |
| POST | `/api/v1/actions/{action_id}/withdrawal` | 撤回订单 | `{}` → `Action` |
| POST | `/api/v1/actions/{action_id}/partial-acceptance` | 按对方数量成交（需要 `approver`） | `{}`，必须带幂等键 → `Action` |
| POST | `/api/v1/actions/{action_id}/arrival` | 登记到货 | `{ quantity }`（1 至未到数量）→ `Action` |
| GET | `/api/v1/missions/{mission_id}/conversations?limit=100&after=` | 找默认 Agent 会话 | `items[].{is_default, active_run_id, followup_enabled, followup_version}`、`next_cursor` |
| POST | `/api/v1/missions/{mission_id}/conversations` | 第一次发送前建会话 | `{ is_default: true, title: '活动备货' }`；成功前沿用同一 key |
| GET | `/api/v1/conversations/{conversation_id}/messages?limit=100&after_seq=` | 增量读消息 | `items[].{seq, role, content, run_id, references}`、`next_after_seq` |
| POST | `/api/v1/conversations/{conversation_id}/messages` | 发给 Agent | `{ content }` → `MessageAccepted { message_id, agent_run_id }` |
| POST | `/api/v1/agent-runs/{run_id}/resume` | 回答 Agent 的提问 | `{ content, interrupt_id }` → `ResumeAccepted` |
| GET | `/api/v1/agent-runs/{run_id}` | 运行快照 | `status`、`question`、`interrupt_id`、`error_code`、`trigger`、`graph_version`、`input_through_seq`、`progress_seq`、`tools`、`activity`、`outcomes`、`created_at`、`finished_at` |
| GET | `/api/v1/agent-runs/{run_id}/events/stream?after_seq=` | 实时进度（SSE） | 事件 `progress`、`sync`、`access_revoked`、`reset` |
| POST | `/api/v1/agent-runs/{run_id}/cancel` | 停止本轮回答 | `{}` → `RunView` |
| PATCH | `/api/v1/conversations/{conversation_id}/followup` | Agent 主动解读开关（`operator`） | `{ enabled, interval_seconds: 300, expected_version }` |
| GET | `/api/v1/agent-runs/{run_id}/evidence?id&version_id&generation_id&chunk_id&metadata_revision&content_sha256` | 打开当时原文片段 | `HistoricalEvidence`：`title`、`version_no`、`text`、`truncated`、`reference` |
| GET | `/api/v1/documents/{document_id}/versions/{version_id}`，再 `…/content` | 下载历史原件 | 核对 `id`、`document_id`、`content_sha256 === reference.original_sha256`、`size_bytes` 与下载内容的 SHA-256；下载后再读一次版本 |
| GET | `/api/v1/agent-runs/{run_id}/context` | 上下文记录 | §2.13 |

**依赖与解释**
- **页头徽章** `useSpace().badgeFor(issue)`：关联委托且委托已读到时用 `statusBadge`（委托状态、有采购建议时的方案状态、`canDecide`、本委托未结采购单、`stock.in_transit`、待核实确认、店主待回复订单、店主待登记到货、`business`）；委托未读到时用 `workBadge`；有 `issue`（首次同步除外）、委托未结束而徽章不是琥珀色时，改为"需要处理"。
- **方案卡** `space/PlanCard.vue`：常规方案只给推荐数量、20、40、0 四个选项，且只收约束原因为空或只有 `TASK_QUANTITY_LIMIT` 的候选；应急方案只给采纳的那一个和 0。确认按钮需要 `approver`；改选非推荐、非 0 数量另需 `operator` 和 `planRevision`。显示 `input_snapshot.forecast.remaining_demand/horizon_end`、`eligible_inbound_qty`、`state.stocks[].on_hand`、`offer.supplier_id/unit_price_minor`、`policy.cash_floor_minor`，以及候选的 `shortage_qty/spend_minor/cash_after_minor`。
- **确认流程**：`prepareDecision()` 检查 `canDecide`；数量变了先调 revision，刷新后新方案的 `proposed_purchase.quantity` 必须等于所选，否则报"新方案的数量已变化，请重新查看并选择。"；应急方案不允许改数量。弹窗用 `structuredClone` 冻结方案快照。提交前写 `ss.approval`；4xx 清除并显示原因；5xx、502、断线时保留记录并关闭弹窗，页面转成"确认结果尚未取得"。冲突类错误码的文字见 `utils/api.ts`。
- **方案变化卡**：前一版取 `plan_version - 1`；原因取两版 `state_version` 之间、同商品的账本条目（`DEMAND_REVISED` 需求修订、`GOODS_RECEIVED` 到货、`SALE_RECORDED` 销售、`PURCHASE_ACCEPTED` 采购受理），没有时比较 `task_constraints.max_purchase_qty`（"你调整了采购数量"），再没有写"依据更新"；建议数量与剩余需求都没变时只写一行。"这次只补缺口"取新方案 0 件候选的 `shortage_qty`。
- **采购与到货**：状态词 `orderStatus()`；回执 `receipt.status`（`ACCEPTED` 已受理、`REJECTED` 已拒绝、`PENDING` 尚未答复）与 `receipt.recorded_at`；原因 `last_error`；编号 `external_order_id`，没有时用 `id`；到货进度来自同 `action_id` 的 `InboundItem`；只对 `QUEUED`/`EXECUTING`/`SUCCEEDED`/`UNKNOWN` 显示到货信息。
- **店主发单** `AssistedOrderCard.vue`：`useShop().awaitingSupplier` = 门店里第一笔未决采购单是 `channel === 'assisted'` 且 `EXECUTING`。订单信息读 `order_message`（按界面语言取 `text.zh` 或 `text.en`、`reference`、`supplier_id`、`quantity`、`unit_price_minor`、`total_minor`、`requested_delivery_date`）。回执 `SupplierReceipt.vue` 读 `supplier_reply`（`outcome`：`confirmed`/`declined`/`needs_attention`；`differences[]`；`quotes{字段: 原话}`；`read_by`：`model`/`rules`；`text`；数量、单价、金额、交期、供应商单号）。回复只给一部分（`utils/recovery.ts partialReply()`：`supplier_reply.outcome === 'partial'` 且回复数量小于订单数量）时，标题"{供应商}只能给 x 件，订单是 n 件"，上方一行后果"只付 ¥…，余下 ¥… 释放；还缺 m 件。"，主按钮"按对方数量成交（x 件）"（`useShop.acceptPartialSupply` → `POST /api/v1/actions/{action_id}/partial-acceptance`），文字链接"登记新回复"；有 `recoveryCases`、`operator` 与 `approver`、没有进行中的应急补货时另给文字链接"撤回整单，找别家补 n 件"（先撤回，再以原因 `partial` 发起应急补货并排除这家），否则为"撤回这笔订单"。应急补货进行中（`quiet`）主按钮降为次按钮。登记回复、撤回、成交都经 `orderWrite()`，回音丢失后可安全重试（§1.5）。
- **到货登记** `ArrivalCard.vue`：`useShop().arrivalsToRecord` = 当前委托里 `assisted`、`SUCCEEDED`、到货 `remaining_quantity > 0` 的订单；`awaitingArrival` 再去掉进行中的应急补货持有的采购（`useRecoveryLaunch().holds()`：应急卡进行中时登记它的全部采购 `owned().actionIds`，并在登记会结案时先说明），到货卡只列 `awaitingArrival`；页头徽章的"货到后请登记"按 `arrivalsToRecord` 算。应急补货进行中、或页面上有可确认的方案时（`quiet`），"登记到货"降为次按钮。
- **方案位让给应急卡**：应急补货进行中（`useRecoveryLaunch().inProgress()`）且没有别的决定（另一份可确认的常规方案、另一笔店主待回复订单）时，方案位整个不显示；有可确认的常规方案时收成一行"常规方案：建议补 N 件 · ¥"加文字链接"核对 N 件采购"。店主待回复的订单若是应急卡正在显示的那笔、它的任一采购，或由它的方案刚生成的订单（`plan_id` 相同，确认后 Case 还没重读时），算作应急卡自己的，不占方案位。
- **事项内容**：`WAITING_INPUT` 且有 `question` → 澄清卡；关联委托且为 `RECEIVED`/`PROCESSING`/`BLOCKED` 或处理超时 → 进展说明（`question`/`summary`/`next_step`/`updated_at`）；没有委托时，没有试算结果或状态不是 `RESULT_READY` → 进展说明。`WorkResult` 在 `result.kind !== 'quotation'` 时显示，块由 `surfaces/derive.ts` 推导（§2.7）；"下一步"块只能打开现有弹层或视图（`surfaces/types.ts NEXT_STEP_TARGETS`），快捷回答走事项消息。委托条件卡读 `item.mission_request.objective/policy.cash_floor_minor/check_interval_seconds`；`demonstration`、试算已过时（`calculation.input.state.state_version` 不等于当前、过了 `valid_until` 或数据不新鲜）、非 `operator` 时禁用。
- **澄清卡** `space/ClarificationCard.vue`：按问题文字里的关键词决定快捷字段——含"预算/金额/现金/多少钱/资金"给金额；含"日期/到货/哪天/哪几天/几号/什么时候/何时/时间"给日期区间；含"数量/多少件/几件/件数"给数量区间；含"供应商"给供应商。填写后拼成一句中文"补充：预算 X 元；日期 …；数量 …；供应商 …。"作为事项消息发出；没有命中时引导到对话里回答。
- **事项对话**：消息 `role`（`user` 你、`system` 事项进展、`assistant` 助手或试算结果）、`demonstration`、`result`；`item.processor_available` 为否时写"助手暂不可用…"，保存成功后提示"已保存。助手启用后会处理…"。
- **Agent 对话**：会话按 `is_default` 找，没有就用第一个；当前运行取 `active_run_id`，否则取最近一条带 `run_id` 的消息。`agentEnabled` 为否或委托已结束时不能发送；本轮进行中且不是 `WAITING_INPUT` 时不能再发。SSE 只在运行为 `QUEUED`/`RUNNING`、且快照带数字 `progress_seq` 和数组 `activity` 时连接；`progress` 事件经 `utils/agent-progress.ts applyProgressEvent()` 校验（`schema_version === 1`、`run_id` 相同、`seq` 连续、类型为 `run.*`/`tool.*`、负载字段齐全），断档或不合法就改为轮询并重连（1.5 s 起翻倍，最多 15 s）；`access_revoked` 清空并提示重新连接。运行结束、或 `revise_plan`/`request_check` 工具成功时刷新经营数据。工具列表合并 `tools` 与 `activity`（`runTools()`），名称经 `describeTool()`；页面打开期间完成的工具让对应卡片高亮约 1.1 s（`facts` → `#space-facts`、`plan` → `#space-plan`、`mission` → `#space-mission`、`history` → `#space-history`、`receipt` → `#space-receipt`，没有采购卡时打开采购记录弹层）。业务成果 `outcomes[]`（`kind`：`evaluation`/`revision`；`availability`；`before`/`after` 为 `PlanComparison`）由 `AgentOutcome.vue` 显示，`after.state_version` 或 `after.mission_version` 与当前不同时标为历史结果。消息里 `type === 'forecast'` 的引用可跳到今日的预测面板（要求 `store_id`、`sku_id` 与当前一致）。`graph_version === 'agent-context-v1'` 的运行显示"查看上下文记录"。默认标签：没有委托 → 事项对话；有委托 → Agent 对话，`agentDormant()` 时改为事项对话；`panel=agent` 强制 Agent。

**后端改动会影响**
- `WorkView`：`status` 取值、`version`、`question`、`summary`、`next_step`、`result`、`mission_id`、`mission_request`、`demonstration`、`processor_available`、`processing_expires_at`、`mission`、`business`。
- `Plan`/`RecoveryPlan`：`status`、`plan_version`、`state_version`、`expires_at`、`proposal_hash`、`proposed_purchase.*`、`candidates[].{quantity, shortage_qty, spend_minor, cash_after_minor, rejection_reasons}`、`input_snapshot.{offer, policy, forecast, state, eligible_inbound_qty, task_constraints}`、`plan_kind`、`selected_candidate_id`。
- `PlanDecision`、`PlanRevisionRequest` 的字段与冲突错误码；新的 409 码要在 `utils/api.ts` 加文案。
- `Action`：`status`、`channel`、`order_message.*`、`supplier_reply.*`、`receipt.*`、`last_error`、`external_order_id`、`purchase_snapshot.*`；`InboundItem` 字段。
- Agent：`ConversationView`、`MessageView`、`RunView` 字段，SSE 事件名与 `AgentEvent` 结构，工具名（`utils/agent.ts` 的表；`MemoryPanel.vue` 另有 `process_quotation`、`get_forecast`），`BusinessOutcome`、`PlanComparison`。
- 候选数量：后端改了 `candidate_quantities`，方案卡仍只列推荐、20、40、0。
- 后端 `question` 的措辞决定澄清卡出现哪些快捷字段。

**已知限制或待后端配合**
- 委托当前方案是待确认的应急方案时，事项列表与详情会 503（§4 第 1 项），事项页可能只剩一句错误"这件事的方案正等待确认，刷新前先确认或拒绝它。"。
- 结束委托的前提之一是 `mission.current_action_id` 为空（弹层）或本委托没有未结采购单（页脚）。
- `useShop` 一次只持有一个委托的方案、时间线和 Agent 会话；打开另一件事项会切换委托。

### 2.6 应急补货（恢复事项）

对用户叫"应急补货"；代码和接口里是恢复事项（operations case，`CaseDetail`）。事项页的卡片 `recovery/RecoveryFlow.vue` 只在委托已读到且有 `recoveryCases` 时挂载；`?view=task` 的旧面板见 §2.16。前端不保存进度，阶段每次都从 Case、它的方案和它的全部采购推导。

**组件与状态**：`recovery/RecoveryFlow.vue`（容器，`provide(recoveryFlowKey)`）、`recovery/RecoveryBrief.vue`、`recovery/RecoveryCompare.vue`、`recovery/RecoveryConfirm.vue`、`recovery/RecoveryOrder.vue`、`recovery/RecoveryReceive.vue`、`recovery/RecoveryOutcome.vue`、`recovery/RecoveryUnconfirmed.vue`（写入结果不明）、`recovery/RecoveryPurchases.vue`（本次已买到、未到齐的采购行与卡内登记到货）、`recovery/RecoveryDays.vue`（七天条）、`recovery/RecoveryPrompt.vue`（今日卡）、`space/FlowProgress.vue`（进度条）；`composables/useRecoveryFlow.ts`（流程动作与轮询）、`useRecoveryCase.ts`（Case 读写与待核实记录）、`useRecoveryLaunch.ts`（入口请求、进行中标记、应急卡占用的方案、订单与全部采购）、`useRecoveryPrompt.ts`、`useSupplierDirectory.ts`（供应商资料与名称登记）；`utils/recovery.ts`；`types/recovery.ts`；样式 `assets/css/recovery.css`。

**入口来源**（都调用 `useRecoveryLaunch().request()`；事项页的卡在挂载或请求变化时 `take()` 它；该委托已有进行中的应急补货时只滚到卡片处）

| 入口 | 位置 | 条件 | 请求 |
|---|---|---|---|
| 页头"应急补货" | `space/SpaceHeader.vue` | `recoveryCases`、`operator`、委托 `ACTIVE`、没有进行中的应急补货 | `reason: 'manual'`（说明步再用 `recoveryTrigger()` 补出原因） |
| 今日"需要你拍板"的应急卡 | `recovery/RecoveryPrompt.vue` | §2.2 | `reason` 来自 `recoveryTrigger()`；拒单时 `exclude` 为该供应商；`gap` |
| 提醒弹层"找别家补" | `pages/index.vue restockable()` | `recoveryCases`、`work.s.available`、`operator`、提醒未解除、`STOCKOUT_RISK`/`CASH_CONSTRAINT`、委托 `ACTIVE` | `reason: 'stockout' \| 'cash'`，`gap: facts.shortage_qty` |
| 采购与到货"找别家补" | `space/OrdersCard.vue` | 最新一笔采购单 `FAILED`、委托 `ACTIVE`、`recoveryCases`、`operator`、没有进行中的 | `declined`（`supplier_reply.outcome === 'declined'`，排除该供应商）或 `failed` |
| 订单卡"撤回整单，找别家补 N 件" | `AssistedOrderCard.vue` | 部分回复、`recoveryCases`、`operator` 与 `approver`、没有进行中的 | 先撤回订单，再 `reason: 'partial'` 并排除该供应商 |

`recoveryTrigger()` 按顺序判断：本委托最新一笔采购单 `FAILED` → `declined` 或 `failed`；最新一笔仍未决 → 不触发；有逾期在途（`remaining_quantity > 0` 且 `is_overdue`）→ `late`；常规方案待确认、没有采购建议而 0 件候选有缺口 → `infeasible`；有采购建议但所选数量的候选仍有缺口 → `stockout`；有未解除的 `CASH_CONSTRAINT` → `cash`。

**进度条：阶段怎样从数据推导**（`utils/recovery.ts flowState()`。输入：Case `d`；Case 的订单 `a`（`caseAction()`：先按 `d.action_id`、再按 `plan_id` 在 `useShop().s.actions` 里找，所以确认后 Case 还没重读时也能找到）与它的到货；Case 的全部采购（`purchasesOf()`：Case 的 `purchases[]` 加上店铺列表里已有而 Case 还没带上的那笔，状态取较新的一份、到货取较大值；"当前这笔"只认当前版本的采购）；Case 证据中 `kind === 'inbound_order'`、且不是本次采购的原订单到货；当前身份的 `approver`/`operator`；发单方式 `channel`）

| 顺序 | 条件 | 阶段 · 谁在做 |
|---|---|---|
| 0 | 说明步打开，还没有 Case | 说明情况 · 等你 |
| 1 | Case 为 `RESOLVED`（后端在全部采购到货时自己结算，带 `outcome`） | 结果（结束）；`outcome.path === 'waiting'` 为等原订单变体 |
| 2 | Case 有订单（`d.action_id` 或已找到 `a`）；订单状态取当前这笔采购的、否则 `a.status`、否则由 `d.execution_status` 推出；为 `SUCCEEDED` 且全部成交，或 Case 已终止 | 所有已成交的采购都到齐（没有采购记录时看 `a` 的到货，读不到再看 `d.execution_status === 'RECEIVED'`）→ 未终止时登记到货 · 系统在做（"货已到齐，正在结算结果"，等后端置 `RESOLVED`），已终止时结果（结束）；否则 → 登记到货，还有店主发的单没到齐为"等你"，否则"系统在做"，已终止时收成摘要。`a.channel === 'assisted'` 为店主发单变体，否则为系统下单变体；订单还没读到时按 `channel` |
| 3 | 同上，但当前这笔只成交了一部分（成交数小于订单数）、Case 未终止且在那之后没有新版本 | 找货比价 · 等你（原因 `short`）；Case 已有新版本时继续往下判断 |
| 4 | 订单为 `QUEUED`/`EXECUTING`/`UNKNOWN` | 发单并登记回复（系统下单变体为"系统下单"）：店主发单且 `EXECUTING` 为"等你"，否则"系统在做" |
| 5 | 订单为 `FAILED`/`CANCELLED`/`STALE`：Case 已终止 → 结果（结束）；在那之后没有新版本（`(d.plan_revision ?? d.current_revision) >= d.current_revision`）→ 找货比价 · 等你，原因 `withdrawn`（`CANCELLED`）、`recheck`（`STALE`）、`declined`（回复拒单）或 `failed`；否则继续往下判断 | 见左 |
| 6 | Case 为 `CANCELLED`/`CLOSED` | 结果（结束） |
| 7 | 当前版本的方案已 `APPROVED`，订单还没读到 | 下单 · 系统在做 |
| 8 | Case 为 `MONITORING` 且方案不是 `PENDING_APPROVAL` | 等原订单变体的到货步：本次已有成交的采购时按它们判断（还有店主发的单没到齐为"等你"，否则"系统在做"）；否则有原订单 → 等原订单到货 · 系统在做（到齐后等后端结算）；没有原订单 → 决定这次不补 · 等你（后端一直保持 `MONITORING`、`routine_paused`，直到店主结束） |
| 9 | 有 `d.plan_id` 且 `d.plan_revision === d.current_revision` | `plan_status` 为 `PENDING_APPROVAL` → 采用并确认 · 等你；为 `REJECTED` → 找货比价 · 等你（原因 `rejected`）；为 `EXPIRED`/`SUPERSEDED` → 找货比价 · 等你（`RECHECK_REQUIRED` 时原因 `recheck`，否则 `expired`） |
| 10 | `sourcing.status === 'running'` | 找货比价 · 系统在做 |
| 11 | `OPTIONS_READY` 且有 `proposal` | 找货比价 · 等你（`d.stale` 时原因 `stale`） |
| 12 | `NEEDS_INPUT`/`BLOCKED` | 找货比价 · 等你（原因 `input`） |
| 13 | `RECHECK_REQUIRED` | 找货比价 · 等你（原因 `recheck`，副句取 `recheck_reason`） |
| 14 | 其余（建了或改了但没有分析成） | 找货比价 · 等你（原因 `pending`） |

"等你"的这一步当前身份没有所需权限时改为"等审批"（`other`）：确认与登记回复看 `approver`，登记到货与"这次不补"看 `operator`。

步骤（`flowSteps()`）：店主发单为 说明情况 → 找货比价 → 采用并确认 → 发单并登记回复 → 登记到货 → 结果；系统下单把第 4、5 步换成"系统下单""等待到货"；等原订单为五步（第 3、4 步"决定等原订单""等原订单到货"）；没有原订单时等待就是不补，四步（第 3 步"决定这次不补"，停在这一步直到店主结束）。前端自己的调用超过 300 ms 时，"谁在做"显示"系统在做"；写入结果不明时为"等你"。结束（`ended`）后卡片收成一行结果，可展开。

**各步骤的数据与接口**

| 步骤 | 组件 | 读 | 写 |
|---|---|---|---|
| 说明情况（发起与预填） | `recovery/RecoveryBrief.vue` | 看板 `simulation_time`、`available_cash_minor`；委托 `policy.cash_floor_minor`；`stock.on_hand/remaining_demand`；在途；当前方案 `input_snapshot.forecast`；`GET /api/v1/stores/{store_id}/forecast?sku_id=`；`GET /api/v1/stores/{store_id}/supplier-documents` | `POST /api/v1/operations-cases`，成功后立即 `POST …/{case_id}/analyze`；有可读资料且有 `sourcing` 时再 `POST …/{case_id}/source` |
| 找货比价 | `recovery/RecoveryCompare.vue` | `GET /api/v1/operations-cases/{case_id}`：`proposal`、`sourcing`、`expert_analysis`、`missing_inputs`、`stale`、`purchases[]` | 重新比价：`POST …/revise` 后 `POST …/analyze`；重新找货：`POST …/source`；等原订单/这次不补：`POST …/control`（`adopt_waiting`）；结束：`POST …/control`（`cancel`）；采用：`POST …/materialize`。"换一家"之后的采用与等待先重新比价 |
| 采用并确认 | `recovery/RecoveryConfirm.vue` | Case 的方案：与当前方案同 id 时用 `useShop().plan`，否则 `GET /api/v1/plans/{plan_id}`；发单方式 `channelFor()` | 页面确认弹窗 `POST /api/v1/plans/{plan_id}/decision`（§2.5） |
| 发单并登记回复 | `recovery/RecoveryOrder.vue` | 采购单的 `order_message`、`supplier_reply`、`receipt`、`amount_minor` | `POST /api/v1/actions/{action_id}/supplier-reply`；`POST …/partial-acceptance`（按对方数量成交）；`POST …/withdrawal`；撤回整单找别家时撤回后 `POST …/revise` 与 `analyze` |
| 登记到货 | `recovery/RecoveryReceive.vue`、`recovery/RecoveryPurchases.vue` | 到货 `remaining_quantity/received_quantity/ordered_quantity/expected_arrival_at/is_overdue`、回复的 `delivery_date`、`purchase_snapshot.expected_arrival_at`；Case 的 `purchases[]` | `POST /api/v1/actions/{action_id}/arrival { quantity }`（当前这笔，或本次任一笔店主发的采购）；这次不补：`POST …/control`（`cancel`） |
| 结果 | `recovery/RecoveryOutcome.vue` | `outcome`、`purchases[]`；手动结束时方案候选、当前订单与到货 | — |

请求体：
- 建 Case：`{ mission_id, objective, budget_minor, max_purchase_qty: null, supplier_ids, daily_demand? }`。`supplier_ids`（`useRecoveryFlow suppliersFor()`）：同商品的在档报价去掉排除的供应商，按单价、供应商 id 排序取前三；没有报价，或没有排除且不超过三家时传 `null`（由后端比较全部）。需求用已启用的日预测时不传 `daily_demand`（后端自己读预测），否则传七天 `[{ settlement_at, demand_qty }]`。
- 分析 `{ expected_revision }`；修订 `{ expected_revision, daily_demand?, supplier_ids? }`；寻源 `{ expected_revision, district: '滨江区' }`（`useSupplierDirectory.ts SAMPLE_DISTRICT`）；控制 `{ expected_revision, operation }`。
- 采用：`{ expected_revision, proposal_id, candidate_id, expected_mission_version: current_mission_version, expected_state_version: current_state_version, expected_current_plan_id: current_plan_id, proposal_hash }`。

**发起与预填**：问题句 `objectiveFor(reason, projection, supplier)`，在"修改"里可改写，提交为 `objective`。预算 = 可用现金 − 现金底线（不小于 0；在"修改"里可改，最多两位小数，不超过 1,000,000,000 分）。需求 `demandFrom()`：预测 `usable_for_planning` 且有 7 天 `daily_predictions` 与 `predicted_quantity` 时，按后端的取整规则（`allocateDaily()`）分到 7 天（分段控件第一项写"按预测"）；否则把方案的 `remaining_demand` 按 `horizon_start`–`horizon_end` 折成 7 天均摊，再否则用 `stock.remaining_demand` 均摊（写"按估算"）；分段的另一项是"每天 N 件"。七天推演 `projectWithout()` 用求解器的日结规则：原订单按 `expected_arrival_at` 计入当天，已逾期的不计；七天条只在推演仍有缺口时显示。首日结算 = 经营时钟 + 24 h − 1 s，只在"修改"里显示。推演七天不缺货时主按钮是"关闭"（`data-recovery-close`），比价降为文字链接"仍要比价"（`data-recovery-start`）；有缺口时左下的"关闭"关掉说明，回到原来的 Case。

**寻源与示例资料**：资料来自 `GET /api/v1/stores/{store_id}/supplier-documents`（`useShop.refresh` 读店铺数据时就读一次），`connected === true` 的供应商不读；名称登记到 `utils/glossary.ts rememberSupplierNames()`，寻源结果的 `sourcing.suppliers[].name` 也登记。没有资料时，只在演示模式下自动调用 `POST …/supplier-documents/sample { sku_id, district: '滨江区' }`，失败后才出现"载入示例资料"链接；非演示模式不载入。寻源中标题"正在读 N 家供应商的资料"，逐家显示（读完前是灰色占位条）：`sourcing.reviews[]` 的 `card.status`（`offer`/`no_offer`）、`card.reason`（`SKU_NOT_COVERED`、`STORE_NOT_SERVED`、`SUPPLY_WITHDRAWN`）、`card.offer.{unit_price_minor, minimum_order_quantity, pack_size, lead_time_days}`、`card.citations[].{field, quote}`；缺口取 `sourcing.request.shortfall_qty/short_from`；`sourcing.missing[]` 的码经 `caseProblem()` 显示。寻源从 `running` 变为其他状态后刷新经营数据（新报价进 `catalog`）。

**比价与采用**：`comparison(proposal)` 按供应商归并候选：每家一行显示它的最佳候选（依次比 `lost_qty`、`spend_minor`、`end_stock`、`quantity`），选中那家的可行（`feasible && executable`）数量按最佳档前后各一档列成数量档（每档带金额与缺货，推荐的那一档另标）；`quantity === 0` 的候选是"等原订单"（没有原订单时"这次不补"）；推荐取 `recommended_candidate_id`，"推荐"标在它的供应商上；全部不可行的供应商在选项下方写 `rejection_reasons` 经 `blockedReason()` 的原因；读不出报价的供应商写读取原因。排除的供应商（见下文"重新比价"）不出现，推荐按剩下的选项重算（`withoutSuppliers()`），全都排除时标题写"没有别的供应商可比"。标题与副句由候选数字确定生成（"{供应商}补 N 件最合适" / "7 天缺货 a → b 件 · 花 ¥…"；没有缺口或买了也赶不上时用 `conclusion()` 的一句）；"为什么这样比"折叠显示 `expert_analysis.subtasks[].claims[].statement`，中文界面只显示含汉字的条目，条目里的供应商 id 换成名称。主按钮"用{供应商}补 N 件"：`materialize` → 刷新 → 当前方案就是 Case 的方案且 `canDecide` 时直接打开确认弹窗（需要 `approver`，否则停在确认步）；调用期间选项不收起，主按钮显示"正在采用…"。"换一家"之后再采用时先 `revise` + `analyze`（第一次采用已让委托版本加一），再采用新比较里同一家同数量的候选，没有就请店主重选；`materialize` 遇 `PLAN_VERSION_CONFLICT`、而 Case 重读后候选仍在且未过期时再试一次。`SOURCING_MODEL_NOT_CONFIGURED`、`SUPPLIER_DOCUMENTS_REQUIRED`、`NO_SHORTFALL` 用普通提示，其余失败用琥珀色。

**确认**：标题"核对后确认：用{供应商}补 N 件"，副句"N 件 × 单价 · 预计 M/D 到"（`proposed_purchase.{quantity, unit_price_minor, expected_arrival_at, supplier_id}`）；三格：本次支出 `total_minor`、采购后现金（所选候选的 `cash_after_minor`，下注 `input_snapshot.policy.cash_floor_minor`）、预计缺货（0 件候选的 `shortage_qty` → 所选候选的 `shortage_qty`，7 天合计）。主按钮"核对 N 件采购"旁写由谁发单，按 `useRecoveryFlow.channelFor()`：资料或寻源读出的供应商（它的报价只能由寻源登记，后端一律走 `assisted`）写"确认后由你把订单发给{供应商}"；其他供应商按会话的 `purchase_channel`（`GET /api/v1/me`），`assisted` 同上，`simulator` 写"确认后系统直接下单"；会话没有该字段时看之前给它下过的订单的 `channel`，仍推不出时不写。没有 `approver` 时不放按钮，右下状态字"等有审批权限的人确认"，进度"等审批"。暂时不能确认时只写当前成立的一条原因（`unavailableReason`：待核实的确认、断线、数据未同步、门店有未决采购单、方案已过期、委托暂停或结束、方案还在读取、状态版本变化）。"换一家"回到比较，比较里有"不换了，回去确认"（`canReturnToConfirm`）。弹窗确认成功后 `useShop` 记下 `s.decided`，卡片立即重读 Case。

**店主发单与登记回复**：订单与回执字段同 §2.5。标题"把订单发给{供应商}，收到回复后贴回来"，副句"N 件 × 单价 · 合计 · 希望 M/D 送达"；回复前显示订单消息与"复制"，有回复后收成一行"订单已发"（可展开）加"复制"；`UNKNOWN` 时标题"采购结果还没有核实"，并提示确认前不要另下一单；`needs_attention` 时标题写回复还不能确认这笔订单。回复 `outcome === 'partial'`（`partialOf()` / `partialReply()`：回复数量小于订单数量）时：标题"{供应商}只能给 x 件，订单是 n 件"，副句"订单 n 件 · 对方给 x 件"，回复框收在"登记新回复"后面（展开后提交按钮"登记回复"为次按钮），主按钮上方一行后果"只付 ¥…，余下 ¥… 释放；还缺 m 件，之后可以找别家补。"，主按钮"按对方数量成交（x 件）"→ `useRecoveryFlow.acceptPartial()` → `POST /api/v1/actions/{action_id}/partial-acceptance`（`useShop.acceptPartialSupply`，需要 `approver`）→ 重读 Case，进入原因 `short`：标题"{供应商}只确认了 x 件"，副句"已按 x 件成交 · 还缺 m 件"，主按钮"缺的找别家补上"（`again()`：排除这家后 `revise` + `analyze`，在同一个 Case 里再采用一家；后端允许已部分成交的 Case 再采用）。文字链接"撤回整单，找别家补 n 件"（`withdrawAndSwitch()`：撤回 → 记下排除 → 重读 Case → 用重排的 `daily_demand` 与新的 `supplier_ids` 修订 → 分析）。不是部分回复时，撤回用文字链接"撤回这笔订单…"再确认。登记回复、成交与撤回需要 `approver`，没有时右下写"等有审批权限的人登记回复"。

**登记到货**：店主发单可分次登记，数量为 1 至未到数量（需要 `operator`，没有时写"等有操作权限的人登记到货"）；系统下单与等原订单只显示状态；等原订单时可"改主意，找别家补"（`again()`）。本次应急补货里已买到、未到齐的其他采购由 `recovery/RecoveryPurchases.vue` 列成一行"{供应商} N 件 · M/D 到"，在找货比价、确认、发单、到货各步都显示（确认、发单、到货三步不列当前这笔）；店主发的单带文字链接"登记到货"（`useRecoveryFlow.recordArrival()` → `POST /api/v1/actions/{action_id}/arrival`）。缺口还没决定时登记不会结案（后端 `lifecycle.gap_open()`），所以登记前不另作说明。结算要等所有已成交的采购到齐（`settling`）：全部到齐写"货已到齐，正在结算结果"，等后端置 `RESOLVED`；当前这笔到齐、另一笔没登记写"还有一笔货没登记"；部分成交后选了等待写"等已买到的货到齐"。没有原订单、本次也没买到货时选"这次不补"，后端当场结算，卡片直接到结果；万一读到停在 `MONITORING` 的这种 Case（旧数据）：标题"这次不补"，副句"没有在途的原订单。结束后，系统恢复每天的补货建议。"（`routine_paused` 时；否则只有第一句），主按钮"结束这次应急补货"（`control cancel`）。应急补货进行中，卡片持有它的方案、正在显示的订单和全部采购（`useRecoveryLaunch().own()` 的 `planId`、`actionId`、`actionIds`），页面到货卡不再列这些采购（§2.5）。

**结果**：Case 为 `RESOLVED` 时用后端的 `outcome`（`path`、`planned_qty`、`purchased_qty`、`received_qty`、`spend_minor`、`lost_qty_before`、`lost_qty_after`、`action_ids`，以及每笔的 `purchases[]`；各笔的供应商与成交数取 `purchases[]` 中对应的 `supplier_id`、`accepted_qty`）：购买路径"应急补货完成 · {供应商} x 件已到货 · 预计缺货 a → b 件 · 花了 ¥…"；两笔以上采购时写"补到 x 件（{供应商} 10 + {供应商} 30）"（后端 `planned_qty` 是所有订单之和，不当作订单量）；只有一笔且只成交一部分时写"{供应商}确认的 x 件已到货（订单 n 件）"；等待路径"已等到原订单 · 原订单 x 件已到"（没有原订单时"应急补货已结束 · 这次不补"）。展开后三格：预计缺货（"7 天合计（预计）"）、花了、到货 x/n。店主手动结束（`CANCELLED`，没有 `outcome`）时只按当前这笔订单显示买了什么、是否在途。缺货数是后端按同一套七天推演的值，写"预计"。

**写入结果不明**：Case 写入遇 5xx 或断线时，`useRecoveryCase` 把这次提交（路径、请求体、幂等键、步骤）留在 `pending` 和 sessionStorage `ss.recovery.pending:<身份:角色:店铺:委托>`。回音确实丢失后（请求在途时不算），卡片换成 `recovery/RecoveryUnconfirmed.vue`：标题"{步骤}的结果还没确认"（建立这次应急补货 / 比价 / 重新比价 / 采用这份报价 / 找货 / 结束这次应急补货 / 就等原订单 / 这次不补），副句"没有收到回音，这一步可能已经生效。再试一次会沿用刚才的提交，不会重复。"，进度标"等你"，唯一主按钮"再试一次（沿用刚才的提交）"：`useRecoveryFlow.retry()` → `useRecoveryCase.retry()` 用**原幂等键**重发，后端对重复的键返回第一次的结果；成功后按原步骤继续（建 Case → 关闭说明并寻源；采用 → 刷新并打开确认弹窗；建、修订、复查后照常分析）；再次没有回音时副句改为"这次还是没有收到回音，稍后再试。"。4xx 视为明确答复，清掉 `pending` 并重读 Case。期间卡片停止轮询，其他 Case 写入与新的应急补货入口都不可用；刷新页面后从 sessionStorage 恢复，仍可重试。

**失效与重新比价**（找货比价阶段的原因 `again`；卡片写一个标题加一句副句）

| 原因 | 标题 | 副句 | 主按钮 |
|---|---|---|---|
| `declined` | {供应商}拒单了 | 预留的 ¥… 已退回 · 还缺 n 件（n 为那笔订单的件数） | 不找{供应商}，重新比价（排除后修订） |
| `withdrawn` | 给{供应商}的订单已撤回 | 同上 | 同上 |
| `failed` | 这笔采购没有成功 | 同上 | 重新比价 |
| `short` | {供应商}只确认了 x 件 | 已按 x 件成交 · 还缺 m 件 | 缺的找别家补上（排除后修订） |
| `rejected` | 你没有采用这份应急方案 | 结束这次应急补货后，系统才恢复每天的补货建议 | 重新比价；文字链接"结束这次应急补货" |
| `expired`，或 `recheck` 且 `recheck_reason === 'PLAN_EXPIRED'` | 应急方案已过期 | 重新比价后再确认 | 重新比价 |
| `recheck`（其他原因） | 比价结果需要更新 | `recovery.ts recheckReason(d.recheck_reason)`：`OPTIONS_EXPIRED`、`BUSINESS_STATE_CHANGED`、`MISSION_CHANGED`、`SOURCE_STALE`、`PURCHASE_FAILED`、`PURCHASE_CANCELLED`、`PURCHASE_STALE` 各有一句（订单 `STALE` 而没有 `recheck_reason` 时按 `PURCHASE_STALE`）；其他写"比价结果需要更新。" | 重新比价 |
| `stale` | 比价结果需要更新 | `proposal.expires_at` 已过时"比价结果已超过有效期。"，否则"比价之后经营数据有变化，比价结果不再成立。" | 重新比价 |
| `input` | 比价缺少条件 | `missing_inputs[0]` 经 `caseProblem()` | 重新比价 |
| `pending` | 还没有比价结果 | 不写（原因在下方的失败提示里） | 重新比价 |
| （所有报价都因 `OFFER_EXPIRED` 不可行且能寻源） | — | — | 重新找货 |

比价进行中（建 Case、重新比价、寻源、分析）标题写"正在建立这次应急补货""正在重新比价""正在读 N 家供应商的资料"或"正在比价"，右下是状态字，不放按钮。

重新比价 `again()`：按当前经营时钟重排 Case 自带的 `daily_demand`（Case 没有自带需求、而缺的是日预测时，按委托的需求假设逐日补上），拒单、撤回、部分成交或失败时把当前这家记入排除，然后 `revise` + `analyze`。排除的供应商（`excludedIds`）有两类：Case 采购记录里 `FAILED`、`CANCELLED` 或只成交一部分的供应商；sessionStorage `ss.recovery.excluded:<case_id>` 列表里的供应商（从入口带来的、店主选了"不找…"的）。修订时 `supplier_ids` 去掉它们，最多取最便宜的三家。Case 的 id、版本或寻源状态变化后，若 Case 为 `OPTIONS_READY`、不在寻源中，而 `supplier_ids` 包含被排除的供应商（寻源会把读出的供应商都放回来），自动再修订一次把它们去掉。

**提醒入口**：见入口表"提醒弹层"一行。

**依赖与解释**
- `CaseDetail`：`status`、`current_revision`、`plan_id`、`plan_status`、`plan_revision`、`action_id`、`execution_status`、`proposal.{id, proposal_hash, candidates[], recommended_candidate_id}`、`stale`、`missing_inputs`、`evidence[].{kind, id}`、`daily_demand`、`supplier_ids`、`excluded_supplier_ids`、`current_mission_version`、`current_state_version`、`current_plan_id`、`sourcing`、`expert_analysis`、`mission_id`、`store_id`、`purchases[].{action_id, supplier_id, status, planned_qty, accepted_qty, received_qty}`、`outcome`、`recheck_reason`、`routine_paused`、`proposal.expires_at`。
- `RecoveryCandidate`：`id`、`supplier_id`、`quantity`、`spend_minor`、`cash_after_minor`、`shortage_qty`、`lost_qty`、`end_stock`、`feasible`、`executable`、`rejection_reasons`、`daily[].{settlement_at, demand_qty, proposed_arrivals, lost_qty}`。
- 错误码文案 `caseProblem()`：`CASE_REVISION_CONFLICT`、`CASE_TERMINAL`、`PROPOSAL_STALE`、`PROPOSAL_HASH_CONFLICT`、`PROPOSAL_INVALID`、`PROPOSAL_REQUIRED`、`PLAN_EXPIRED`、`OFFER_EXPIRED`、`OFFER_UNAVAILABLE`、`EMERGENCY_PURCHASE_ALREADY_ACCEPTED`、`CANDIDATE_NOT_EXECUTABLE`、`SOURCING_MODEL_NOT_CONFIGURED`、`SUPPLIER_DOCUMENTS_REQUIRED`、`NO_SHORTFALL`、`SOURCING_IN_PROGRESS`、`SOURCING_INTERRUPTED`、`SOURCING_UNAVAILABLE`、`CASE_INPUT_CHANGED`、`DAILY_DEMAND_REQUIRED`、`RECOVERY_INPUT_INVALID`、`OFFER_SELECTION_REQUIRED`、`FORECAST_UNAVAILABLE`、`BUSINESS_TIME_REQUIRED`、`INBOUND_STATE_MISMATCH`、`SEARCH_SPACE_EXCEEDED`、`MISSION_NOT_ACTIVE`、`DATA_STALE`、`ACTION_IN_PROGRESS`、`PLAN_VERSION_CONFLICT`、`STATE_VERSION_CONFLICT`（"经营数据刚变了，重新比价后再采用。"）；未列出的用 `utils/api.ts` 给出的句子（§1.5）。候选约束 `blockedReason()`：`BUDGET_EXCEEDED`、`CASH_FLOOR_VIOLATION`、`OFFER_EXPIRED`、`MINIMUM_ORDER_QUANTITY`、`PACK_SIZE_MISMATCH`、`ARRIVAL_WINDOW_MISSED`、`ACTION_IN_PROGRESS`、`EMERGENCY_PURCHASE_ALREADY_ACCEPTED`、`TASK_QUANTITY_LIMIT`、`OFFER_SCOPE_MISMATCH`、`UNVERIFIED_EXECUTION_INPUT`、`MONEY_OVERFLOW`。
- 寻源遇 `CASE_REVISION_CONFLICT` 重读 Case；其他 Case 写入的 4xx 都重读 Case。

**后端改动会影响**
- Case 状态集合与阶段推导（`flowState()`），尤其 `MONITORING`、`OPTIONS_READY`、`NEEDS_INPUT`、`BLOCKED`、`RECHECK_REQUIRED` 与终止集合；`plan_revision` 与 `current_revision` 的关系；`action_id` 指向哪一笔。
- `sourcing`、`expert_analysis` 的内部结构（不在契约里，§1.4）。
- 求解器的日结规则与取整：`projectWithout()`、`allocateDaily()`、`settlements()` 复刻了它，`tests/support/recovery-mock.ts` 也复刻了一份。
- 求解器一次最多比较三份报价（前端按此截取 `supplier_ids`）；寻源区固定 `滨江区`。
- 新错误码、新约束码：`caseProblem()`、`blockedReason()` 与 `app/i18n/en.json`。
- `Action.channel` 的决定规则（`backend/app/execution/repository.py`：寻源登记的报价一律 `assisted`，否则取请求体 `channel` 或配置 `purchase_channel`）。

**已知限制或待后端配合**
- 卡片不显示 `useRecoveryCase` 的同步错误（读 Case 失败的 `syncError`）；写入结果不明见上文"写入结果不明"。
- 只读 `GET /api/v1/operations-cases` 的第一页（后端默认 20 条，按创建时间倒序），再按委托筛选；同一委托有多件 Case 时只显示最新一件未结束的（排除 `CLOSED`、`CANCELLED`、`RESOLVED`，都结束了才显示最新一件）。
- 确认前接口不下发发单方式；前端只对资料或寻源读出的供应商、或之前下过单的供应商推得出（`channelFor()`），推不出时确认步不作说明，进度条在下单前按"店主发单"的步骤显示，下单后按 `Action.channel` 换成实际的变体。
- 从入口带来、或店主选了"不找…"的排除只记在本浏览器的 sessionStorage；从采购记录推出的排除在任何浏览器都生效。
- 事项持有期间（已采用方案或选择等待，`routine_paused`）常规检查一律跳过，事项页不会再出现可确认的常规方案；常规方案收成一行只发生在采用之前。
- 按对方数量成交后先登记那几件到货，后端不会结案（§4 第 23 项，YH 10-19 修复）；卡片仍把这几件的登记收在自己里面。
- 店主手动结束、且有多笔采购时，结果只写当前这一笔。
- 原订单判定依赖 `GET /api/v1/inbounds?limit=100`，在途单很多时可能截掉原订单。
- 其余后端依赖见 §4；YH 10-19 修好了 503、店主发单超时、"这次不补"、排除、相对日期、确认前的发单方式、多件 Case、需重新分析时的 analyze、结算件数，仍缺应急补货建议（第 10 项）和英文错误原句（第 11 项）。

### 2.7 先试算补货

**用户看到/能做**：弹层"先试算补货"：当前可用现金、所选商品现货与在途、经营时点；选商品与供应商报价、现金至少保留（元）、比较数量（2–20 个不同整数，含 0，每个不超过 1,000,000）、可选"用我自己的需求假设"（剩余需求 0–1,000,000 件，期间 1–90 天）；"比较并保存结果"。结果出现在事项页（没有委托的事项）：推荐候选的代价、说明、候选表（推荐行高亮）、依据；"调整条件再试算"；事项带 `mission_request` 时"开始持续跟进这项备货"；保存 txt、CSV、原始 JSON。

入口：页头"先试算补货"（`quantitySimulation`）；事项结果里的"调整条件再试算"或"下一步"块的 `simulation`；新手指引第 4 步。

**组件与状态**：`QuantitySimulationPanel.vue`（`pages/index.vue` 的 `dialog === 'simulation'`）、`WorkResult.vue`、`surfaces/derive.ts`、`surfaces/catalog.ts`、`components/surfaces/*`、`utils/workResultExport.ts`、`space/WorkContent.vue`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| POST | `/api/v1/stores/{store_id}/simulations` | 比较并保存 | `{ expected_state_version, sku_id, supplier_id, cash_floor_minor, candidate_quantities, remaining_demand, horizon_days, work_item_id, expected_work_version }` → 201 `WorkDetail`；在事项页从已有试算再试算时带 `work_item_id` 与 `expected_work_version` |
| GET | `/api/v1/work-items/{item_id}` | 打开结果 | `item.result.calculation`（`QuantitySimulation`） |
| GET | `/api/v1/work-items/{item_id}/results/{result_id}` | 保存结果 | `WorkResultExport` |
| POST | `/api/v1/work-items/{item_id}/mission` | 按条件开始跟进 | `{ expected_version }` |

**依赖与解释**
- 基线是打开弹层时的 `dashboard.state`；看板 `state_version` 变了必须"刷新试算基线"才能提交。提交经 `useWorkItems.submit`，结果未知时按钮变为"查询并重试原试算"。
- 结果块：推荐候选（`calculation.recommended_candidate_id`）的 `quantity`、`spend_minor`、`cash_after_minor`、`shortage_qty`；`result.content` 逐行经 `t()`；`result.columns/rows` 成表（列名与单元格经 `t()`）；`assumptions`、`references`、`provenance.limitations` 进依据折叠。另显示 `calculation.input.product_name`、`input.policy.cash_floor_minor`、`input.remaining_demand`；`calculation.input.state.state_version` 不等于当前或过了 `calculation.valid_until` 时提示结果已过时。

**后端改动会影响**：`QuantitySimulationRequest`、`QuantitySimulation`、`QuantitySimulationInput` 字段；试算结果的中文正文行、列名与 `next_step`（英文界面靠 `app/i18n/en.json` 整行翻译）；`ResultProvenance` 的 `work_id`、`result_id`、`generated_at`、`data_as_of`、`limitations`；`WorkResultExport`（`utils/workResultExport.ts` 由它生成 txt/csv/json）。

**已知限制或待后端配合**：只支持单商品、指定一家供应商的数量与现金底线比较；弹层不检查角色。

### 2.8 报价整理

**用户看到/能做**："资料与简报 → 整理一份供应商报价"或 `GoalDeck`"我想先整理报价"打开弹层，"开始报价事项"新建事项并进入事项页。事项对话输入区里的"添加报价 CSV"：选本地 UTF-8 CSV（不超过 200 KB）、三份示例、下载格式模板。事项内容"报价原件与结果"：选原件、下载原件、SHA-256、结果版本、缺失项、结果表（单件价、起订量折合件数、原报价、来源）、所用规则；"补充或纠正这份资料"（资料行、字段、正确值、整理顺序）与"仅更新本次结果""更新并记住整理顺序"；已保存的规则与"撤回要求"；下载此版本 CSV。

**组件与状态**：`QuotationPanel.vue`、`QuotationUpload.vue`、`QuotationWorkspace.vue`、`utils/quotations.ts`（模板与示例 CSV、`downloadFile()`）、`utils/quotationApi.ts`（类型别名）、`useWorkItems.quotation()`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| POST | `/api/v1/work-items` | 开始报价事项 | `{ store_id, content: t('帮我整理供应商报价') }` |
| POST | `/api/v1/work-items/{item_id}/quotation-files` | 上传 CSV | `{ filename, content, expected_work_version }`（代理上限 1,300,000 字节） |
| GET | `/api/v1/work-items/{item_id}/quotation-files` | 原件列表 | `items[].{id, filename, sha256, created_at}` |
| GET | `/api/v1/work-items/{item_id}/quotation-results` | 结果版本 | `items[].{id, file_id, version, sort_by, rows[], issues[], rule, corrections[], created_at}` |
| POST | `/api/v1/work-items/{item_id}/quotation-results` | 计算或纠正 | `{ file_id, base_result_id, corrections: [{ record, field, value }], sort_by: 'unit_price' \| 'source', persist_rule, expected_rule_version, correction_content, expected_work_version }` |
| GET | `/api/v1/work-items/{item_id}/quotation-rule` | 已保存规则 | `{ version, rule: { version, sort_by, source } \| null }` |
| POST | `/api/v1/work-items/{item_id}/quotation-rule` | 撤回长期规则 | `{ expected_rule_version, operation: 'remove', correction_content, expected_work_version }` |
| GET | `…/quotation-files/{file_id}/download`、`…/quotation-results/{result_id}/download` | 下载（`<a href="/api/backend/…" download>`，经文件传输） | 二进制 |

**依赖与解释**：写入都经 `useWorkItems.submit`（`quotation: true`）：成功后不读写入的响应体，改为重读事项和列表；报价区在事项 `version`/`updated_at` 变化时重读三份数据。显示条件：有原件，或 `item.result.kind === 'quotation'`。字段下拉固定为中文列名 `商品`、`报价金额`、`币种`、`计价单位`、`每包装件数`、`最低订购量`、`MOQ单位`、`来源`，`field` 原样发出。结果行读 `record`、`product`、`unit_price`（`null` 写"暂不能计算"）、`basis`、`moq`、`moq_unit`、`moq_pieces`、`price`、`currency`、`unit`、`pack`、`source`。"沿用整理规则 vN"：结果带 `rule` 且 `sort_by` 相同；`rule.source.work_id` 是别的事项时可跳过去。

**后端改动会影响**：以上请求体与结果字段；CSV 列名（`utils/quotations.ts` 写死中英文两套表头）；`QuoteRule.source` 的内部字段（不在契约里）；前端 200 KB 校验与代理上限。

**已知限制或待后端配合**：只接受 `.csv` 且能按 UTF-8 严格解码的文件。

### 2.9 记忆

**用户看到/能做**：顶栏的记忆图标或设置里"记忆 · 打开"打开抽屉"系统记住了什么"：关于你、经营笔记、技能（按"备货委托""报价整理""其他事项"分组，显示适用事项与依赖工具；结构化规则写成一句话）；纠正、删除、停用。Agent 运行中新写入记忆时，图标出现圆点，对话区出现"Agent 更新了 N 条记忆 · 查看记忆"。

**组件与状态**：`MemoryEntry.vue`、`MemoryPanel.vue`（持有 `useAgentKnowledge(true)`）、`useAgentKnowledge.ts`、`space/ConversationPanel.vue`（回执行）。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/stores/{store_id}/agent-knowledge` | 打开抽屉时读 | `items[].{kind: USER \| NOTES \| SKILL, task_type, version, entries[]}` |
| POST | `/api/v1/stores/{store_id}/agent-knowledge` | 纠正、删除、停用 | `{ kind, expected_version（该 scope 不存在时为 0）, operation: 'replace' \| 'remove', entry_id, content?, task_type?（仅 SKILL）, required_tools? }` |

**依赖与解释**：记忆按"身份 + 店铺"隔离。`agentEnabled` 为否，或写入返回 503 / `AGENT_NOT_CONFIGURED` 时只读。`VERSION_CONFLICT`、`MEMORY_ENTRY_NOT_FOUND`、`BACKEND_UNAVAILABLE`、`CONNECTION_ERROR` 之后重读；`EMPTY_KNOWLEDGE`、`MEMORY_CHANGE_REJECTED`、`SKILL_BUDGET_EXCEEDED` 有中文说明。新记忆的判断：当前 Agent 运行里 `memory_edit` 工具成功的调用（`runTools()`），首次读取时已经存在的不算。`schema: 'quotation-sort-v1'` 的技能写成"整理报价时按单件价/来源排序"。任务类型 `replenishment`、`quotation` 有中文名，其他为"其他事项"。

**后端改动会影响**：`KnowledgeView.entries` 的结构（不在契约里）、`kind` 与 `task_type` 取值、错误码、工具名、`quotation-sort-v1` 的格式。

**已知限制或待后端配合**：后端不提供每条记忆的时间与来源，面板只显示每类的版本（§4）。

### 2.10 七日预测

**用户看到/能做**：今日与持续跟进页的"七日需求预测"面板（经营记录页不显示）：状态（已有预测/预测已失效/暂无预测）与原因句、七日合计与原始合计、来源、逐日曲线、期间、有效期、假设与可追溯证据；`operator` 可选参考系列和输入来源（模型推演 `historical_demo`，或导入本店销售历史 `observed`，后者可"作为规划依据"），运行或重新运行。Agent 消息里的预测引用可跳到这里核对。

**组件与状态**：`ForecastPanel.vue`、`types/forecast.ts`、`useState('forecast-reference')`（由 `AgentConversation.vue` 写入）。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/stores/{store_id}/forecast?sku_id=` | 当前预测（30 s 一次、状态版本变化时） | `status: READY \| STALE \| UNAVAILABLE`、`reason`（取冒号前的码）、`mode`、`usable_for_planning`、`activate_for_planning`、`forecast.{forecast_id, model_version, daily_predictions[], predicted_quantity, total_quantity_raw, horizon_start, horizon_end, generated_at, valid_until, assumptions}`、`history[]`、`model` |
| GET | `/api/v1/stores/{store_id}/forecast/model` | 模型信息 | `supported_series[]`、`minimum_history_days`、`recommended_history_days`、`limitations` |
| POST | `/api/v1/stores/{store_id}/forecast/refresh` | 运行预测 | 重用：`{ sku_id, activate_for_planning }`；首次：`{ sku_id, series_id, mode, activate_for_planning, history?, observation_end_date? }`；`observed` 时 `history` 为 84–374 天连续的 `{ date, sold_quantity, complete: true }`，`observation_end_date` 等于最后一天 |

**依赖与解释**：响应的 `store_id`/`sku_id`（含 `forecast` 内的）必须与当前一致，否则按错误处理。原因码表 `reasons`：`HISTORICAL_DEMO_ONLY`、`FORECAST_INPUT_NOT_IMPORTED`、`FORECAST_V6_DISABLED`、`FORECAST_BINDING_INVALID`、`FORECAST_SCOPE_MISMATCH`、`FORECAST_EVIDENCE_INVALID`、`FORECAST_EXPIRED`、`STORE_STATE_CHANGED`、`STORE_SIMULATION_TIME_UNAVAILABLE`、`FORECAST_HORIZON_FUTURE`、`FORECAST_HORIZON_ELAPSED`、`PLANNING_REQUIRES_FIRST_FORECAST_DAY_UTC_MIDNIGHT`；错误码表 `failures`：`FORECAST_UNAVAILABLE`、`FORECAST_INVALID_EVIDENCE`、`FORECAST_INPUT_REQUIRED`、`FORECAST_INPUT_CHANGED`。应急补货说明步也读同一个接口取日预测（§2.6）。

**后端改动会影响**：以上字段（OpenAPI 里 `forecast`、`model`、`history` 为不定结构，§1.4）、`reason` 的"码: 说明"格式、原因码与错误码。

**已知限制或待后端配合**：参考系列与销售历史用代码和 JSON 文本输入。

### 2.11 文档中心（`?view=documents`）

**用户看到/能做**：店铺资料列表（搜索标题；按分类、状态（使用中/已归档）、商品、供应商筛选；分页加载）；详情（分类、可见范围、上传者、关联商品与供应商、版本列表：版本号、文件名、大小、时间、有效期、SHA-256、下载原件）；`operator`/`admin` 可上传资料、上传新版本、编辑信息、归档/恢复；未确认的提交显示"还有一笔资料提交待核实"。

**组件与状态**：`DocumentCenter.vue`（`pages/index.vue` 以 `storeId:principal_id:roles` 为 key 懒加载）、`useDocuments.ts`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/stores/{store_id}/documents?q&category&status&sku_id&supplier_id&cursor&limit=20` | 列表 | `items[]`（`Document`）、`next_cursor` |
| GET | `/api/v1/documents/{document_id}` | 详情 | `title`、`category`、`visibility`、`owner_principal_id`、`status`、`sku_ids`、`supplier_ids`、`metadata_version`、`latest_version_id`、`created_at`、`updated_at` |
| GET | `/api/v1/documents/{document_id}/versions?limit=20&cursor` | 版本（可读时才请求） | `items[].{id, document_id, version_no, original_name, size_bytes, content_sha256, valid_from, valid_until, created_at}` |
| POST | `/api/v1/stores/{store_id}/documents` | 上传（multipart） | `file` + `metadata`（JSON：`title, category, visibility, sku_ids, supplier_ids, valid_from, valid_until`） |
| POST | `/api/v1/documents/{document_id}/versions` | 新版本（multipart） | `file` + `metadata`（`expected_metadata_version, valid_from, valid_until`） |
| PATCH | `/api/v1/documents/{document_id}` | 编辑信息 | `{ title, category, visibility, sku_ids, supplier_ids, expected_metadata_version }` |
| POST | `/api/v1/documents/{document_id}/control` | 归档、恢复 | `{ operation: 'archive' \| 'restore', expected_metadata_version }` |
| GET | `/api/v1/documents/{document_id}/versions/{version_id}/content` | 下载原件 | 二进制（`fetch`，65 s） |

**依赖与解释**：可读 = `status === 'active'` 且（`visibility === 'store'` 或自己上传）；可管理 = 可写且满足同样的归属条件。分类中文名见 `documentCategories`（`general`、`supplier_terms`、`product`、`sop`、`campaign`、`review`），其他值原样。前端校验扩展名 pdf/docx/xlsx/csv/md/txt、非空、不超过 20 MiB。成功后总是重读列表与详情。错误码表 `documentError()`：`METADATA_VERSION_CONFLICT`、`DOCUMENT_ARCHIVED`、`INVALID_DOCUMENT_STATE`、`RESOURCE_NOT_FOUND`、`FORBIDDEN`、`UNAUTHENTICATED`、`ORIGINAL_UNAVAILABLE`、`IDEMPOTENCY_KEY_REUSED`、`VALIDATION_ERROR`、`INVALID_UPLOAD`、`UPLOAD_TOO_LARGE`、`BACKEND_UNAVAILABLE`，以及 413。列表或详情遇 401/403/404 时清空。待核实提交见 §1.5。

**后端改动会影响**：`Document`、`Version` 字段；`status`、`visibility` 取值；multipart 字段名 `file`、`metadata`；错误码；上传上限（前端与 `server/utils/knowledge-transfer.ts` 都写死 20 MiB）。

**已知限制或待后端配合**：不显示 `indexing_status`、`publications` 等索引与发布字段，也不调用索引与发布接口。

### 2.12 经营概览（`?view=overview`）

**用户看到/能做**：只读：现金与采购预留、现金余额变化图（按事件顺序）、库存（可切商品；在库/在途）、采购到货（待到/已到，逾期在前）、销售（近 7 日、近 30 日或不超过 90 天的自定义区间；销量或金额；按日柱图；明细分页）、数据与来源（各部分的读取时点与新鲜度）。没有确认采购的动作。

**组件与状态**：`BusinessOverview.vue`、`useOverview.ts`、`utils/overview.ts`、`OverviewChart.client.vue`（ECharts，进入概览时才加载）。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/dashboard?store_id=` | 现状 | `state.*`、`freshness.*` |
| GET | `/api/v1/sales/summary?store_id&from&to` | 区间汇总 | `from`、`to`、`record_count`、`buckets[].{from, to, recorded_quantity, recorded_sales_amount_minor}`、`context` |
| GET | `/api/v1/inbounds?store_id&limit=100&cursor` | 全部到货（最多 20 页） | `items[]`、`context`、`next_cursor` |
| GET | `/api/v1/ledger-entries?store_id&limit=100&cursor` | 全部账本（最多 20 页） | `items[]`、`context`、`next_cursor` |
| GET | `/api/v1/sales?store_id&from&to&limit=30&cursor` | 销售明细 | `items[].{event_id, quantity, unit_price_minor, sales_amount_minor, simulation_time}`、`context` |

**依赖与解释**：分页读取时每页都核对 `ReadContext`（`store_id`、`state_version`、`source_sequence`、`simulation_time`）一致，不一致报"读取期间经营数据发生变化，请刷新。"；与看板不一致时就地提示"读取时点不同，请刷新核对"。读满 20 页仍有下一页时标为不完整，不画现金图。现金图 `cashHistory()`：账本完整、只有一条 `INIT` 且带 `opening_state.cash_minor`、按 `state_version` 累加 `changes.cash_delta_minor` 后等于看板 `cash_minor` 时才画。销售区间以 `simulation_time` 的 UTC 日为终点，`to` 不含。12 s 刷新一次，全局看板的 `state_version` 变化时立刻刷新。

**后端改动会影响**：`ReadContext` 字段、分页游标、`SaleSummary`、`SaleBucket`、`SaleRecord`、`LedgerEntryView`（`effect_type === 'INIT'`、`opening_state`、`changes.cash_delta_minor`、`state_version`）、`InboundItem.arrival_status/is_overdue/expected_arrival_at`。

**已知限制或待后端配合**：时间按 UTC 显示，与其他页面的本地时间不同（§1.9）。

### 2.13 学习与经验 / 上下文记录

**用户看到/能做**：`?view=learning`（联调控制弹层"学习与经验"进入）：学习方式（关闭学习、整理候选由我选择启用；后端已是 `assist` 时多一项）、累计次数与首个检查点；每项经验的各版本（标题、摘要、来源数、操作步骤、异常处理、质量卡）；检查质量、启用此版本、按有限证据启用（二次确认）、暂停使用、忘记这项经验（二次确认）；底部"提示词版本与自进化"。Agent 区的"查看上下文记录"：冻结模型、接口、配置版本、每次模型调用与用量、任务约束（附原话）、每次上下文选取（采用与省略的来源、token 估算）。

**组件与状态**：`LearningWorkspace.vue`、`useLearning.ts`、`types/learning.ts`、`SkillQualityCard.vue`、`TextBundleLineage.vue`、`ContextInspector.vue`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/stores/{store_id}/learning` | 学习总览 | `enabled`、`policy.{version, mode, enabled_at}`、`progress.{eligible_episodes, first_checkpoint, …}`、`assets[].{id, version, active_revision, revisions[]}`；`LEARNING_DISABLED` → "当前环境尚未开启经验学习" |
| PATCH | `/api/v1/stores/{store_id}/learning/policy` | 学习方式 | `{ mode, expected_version }` |
| POST | `/api/v1/stores/{store_id}/learning/assets/{asset_id}/evaluations` | 检查质量 | `{ expected_version, revision }` |
| POST | `/api/v1/stores/{store_id}/learning/assets/{asset_id}/transitions` | 启用、暂停 | `{ expected_version, revision, action: 'activate' \| 'suspend', evaluation_id, accept_limited_evidence }` |
| POST | `/api/v1/stores/{store_id}/learning/forget` | 忘记 | `{ expected_version: policy.version, asset_id }` |
| GET | `/api/v1/text-bundles` | 提示词版本 | `items[].{bundle_id, revision, parent_revision, origin, stage, task_model, reflection_model, metric_calls, enabled_for[], changes[].{component, before, after}, content_hash}` |
| GET | `/api/v1/agent-runs/{run_id}/context` | 上下文记录（展开时） | `config.profile.{model_id, api_mode, profile_id, version}`、`calls[].{call_index, role, status, usage_status, usage.total_tokens, error_code, returned_model}`、`frames[].{validation_status, source_message_ids, constraints[], unresolved}`、`manifests[].{selected_source_ids, omitted[].{source_id, reason}, token_budget}` |

**依赖与解释**：版本状态中文名：`DRAFT`、`VALIDATING`、`SHADOW`、`ACTIVE`、`SUSPENDED`、`REJECTED`、`SUPERSEDED`、`ARCHIVED`、`REVOKED`。"启用此版本"要求 `quality_decision.status === 'pass'`；`limited_evidence` 时另给"按有限证据启用"。质量卡读 `quality.checks` 的 `H1`–`H6`、`quality.scores` 与 `dimension_reviews` 的 `S1`–`S6`、`independent_cases`、`expires_at`、`latest_check.decision.status`；结论词 `pass`、`fail`、`insufficient_evidence`、`unknown`。提示词版本名 `case-experts`、`supplier-review`；用途 `case_explanation`、`sourcing_explanation`、`supplier_review`；阶段 `explain`、`read`；`origin === 'gepa'` 时写演化来源。上下文记录：省略原因 `admission`、`budget`、`permission`、`stale`、`source_unavailable`；调用状态 `reserved`、`succeeded`、`complete`、`failed`、`unknown`、`cancelled`；只在运行 `graph_version === 'agent-context-v1'` 时出现；401/403/404 时清空。

**后端改动会影响**：学习接口的整个返回结构（OpenAPI 为不定结构，前端按 `types/learning.ts` 读）、状态与动作取值、错误码（`utils/api.ts` 有 `LEARNING_*` 文案）；`TextBundleEntry` 的字段与 id；`ContextInspection` 的内部结构。

**已知限制或待后端配合**：只有 `operator` 能操作；`assist` 模式只在后端已处于该模式时可见；学习应用的列表与反馈接口未接入。

### 2.14 新手指引

**用户看到/能做**：首次进今日时出现可跳过的六步：认识用途 → 核对店铺（店铺按钮）→ 查看库存现金（事实区）→ 补货试算（"先试算补货"，必须亲自提交成功）→ 区分保存、委托与采购（结果区）→ 从经营记录重新打开结果（记录里对应的事项卡）。可暂停、继续、跳过试算、复用已有试算；设置里可重播。

**组件与状态**：`OnboardingGuide.vue`、`useOnboarding.ts`、`pages/index.vue`（`showTour`、`tourTarget`、`tourAction()`、`showGuidedResult()`）；锚点 `data-onboarding="store|facts|simulation|result|journal"` 与 `data-work-id`。

**调用的接口**：没有自己的接口。用到的数据：`tourReady`（已选店、已连接、有看板、库存与目录）；`tourCanSimulate`（`quantitySimulation`、`operator`、事项可用且未失效）；已有试算 = 当前店里带 `result.calculation` 的事项；打开结果走 `GET /api/v1/work-items/{item_id}`，读不到、不属于当前店或没有试算时提示重新试算；AI 咨询入口要求 `processor_available`。

**依赖与解释**：进度按身份存 localStorage `shopsteward.onboarding.v1:<principal>`（状态、步骤、店铺、结果事项 id 等）；刷新后进行中的变为暂停；换店时标记 `storeChanged`。

**后端改动会影响**：`WorkView.result.calculation` 是否存在与 `store_id`；试算接口（§2.7）；`quantity_simulation` 能力。

**已知限制或待后端配合**：进度不跨浏览器。

### 2.15 设置

**用户看到/能做**：语言（简体中文/English，选即生效）；重新查看新手指引；记忆入口；跟进安排：业务检查间隔（5 秒、15 秒、30 秒、1/5/15/30/60 分钟及当前值，选即保存）、暂停主动跟进；演示模式开关。

**组件与状态**：`pages/index.vue`（`dialog === 'settings'`、`saveSchedule()`、`verifySchedule()`、`applySchedule()`）、`app/i18n/index.ts setLocale()`、`useDemoMode.ts`、`MemoryEntry.vue`。

**调用的接口**

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| PATCH | `/api/v1/missions/{mission_id}/schedule` | 改检查间隔（`operator`） | `{ interval_seconds（5–3600 的整数）, enabled（沿用当前值）, expected_schedule_version }` → `Schedule` |
| GET | `/api/v1/missions/{mission_id}` | 失败后读回、"重新核对安排" | `schedule.{interval_seconds, enabled, version, next_run_at}` |
| POST | `/api/v1/missions/{mission_id}/control` | 暂停（经暂停弹层） | `{ operation: 'pause', expected_mission_version }` |

**依赖与解释**：只采用 `version` 不小于当前值的回执；保存失败时立即读回，读回也失败则锁住选择并写"保存结果尚未核实"，等用户"重新核对安排"。语言与演示模式只存在本浏览器。

**后端改动会影响**：`ScheduleUpdate`、`Schedule` 字段与间隔上下限（前端写死 5–3600 与选项列表）。

**已知限制或待后端配合**：只对当前选中的委托生效；没有委托时显示"尚未建立经营委托。"。

### 2.16 旧任务工作区（`?view=task&mission=…`，兼容入口）

**何时出现**：事项不可用（`work.s.available` 为否，例如 `workIntake` 关闭或事项列表从未读成功）时，委托卡、Agent 入口、已结束的委托都进这里；也可以直接用 URL 打开。

**用户看到/能做**：`TaskWorkspace.vue`：委托标题与操作、"供应异常应对"旧面板（`RecoveryWorkspace.vue` + `SourcingPanel.vue`，有 `recoveryCases` 时）、事实摘要、方案变化回执、`ArrivalCard`、需要处理、`AssistedOrderCard`、`DecisionCard`、结果、`FollowUpCard`、历次方案、`AgentWorkspace`。委托读不到时 `pages/index.vue` 显示"这项任务暂时不可用"；有待核实确认时显示"查询原确认结果"。

**调用的接口**：委托、方案、采购单、Agent 接口同 §2.5（含 `GET /api/v1/missions/{mission_id}/plans` 的 `limit=2` 与 `limit=100`），另有旧面板的 Case 接口：

| 方法 | 路径 | 用途 | 关键请求/响应字段 |
|---|---|---|---|
| GET | `/api/v1/operations-cases?store_id=`、`GET …/{case_id}` | 展开时读；展开期间 5 s 轮询，寻源中 2 s | 同 §2.6 |
| POST | `/api/v1/operations-cases`，再 `…/analyze` | 开始分析 | `{ mission_id, objective, budget_minor, max_purchase_qty（可空）, supplier_ids（勾选，最多 3 家；不勾且在档超过三家时要求选择）, daily_demand?（七个逗号分隔的整数 + 首日结算时间（UTC），逐日 +24 h） }` |
| POST | `…/revise`，再 `…/analyze` | 按新要求重新分析 | 同上，加 `expected_revision` |
| POST | `…/control` | 重新核对最新依据（`refresh`，随后分析）、采用等待方案（`adopt_waiting`）、开启/停止自动跟进（`enable_followup`/`disable_followup`）、结束（`cancel`） | `{ expected_revision, operation }` |
| POST | `…/materialize` | 生成待确认方案 | 同 §2.6 |
| POST | `…/source` | 开始寻源 | `{ expected_revision, district }`（区可改） |
| GET/POST | `/api/v1/stores/{store_id}/supplier-documents`、`…/sample` | 资料、示例资料 | `{ sku_id, district }` |

**依赖与解释**：旧面板直接显示 Case `status` 的中文名（`OPEN`、`ANALYZING`、`NEEDS_INPUT`、`OPTIONS_READY`、`MONITORING`、`RECHECK_REQUIRED`、`BLOCKED`、`RESOLVED`、`CLOSED`、`CANCELLED`）、全部候选与逐日表、`evidence[].status`（`verified_source`、`user_assumption`、`unresolved`）、专家分析（`strategy`：`fixed`、`single`、`static_multi`、`adaptive_multi`；角色 `evidence`、`impact`、`options`、`single`、`fixed`；未采信的分歧）、寻源的每次阅读（`attempts[].{attempt, model, opened, problems, reasons}`；问题码 `invalid_card`、`wrong_supplier`、`asked_user`、`reviewer_failed`、`uncited:<字段>`；`left_out`）。有"核实并重试原提交"（`useRecoveryCase.retry()`）。

**后端改动会影响**：同 §2.6，另加专家分析与寻源阅读记录的内部结构、`CaseEvidence.status`。

**已知限制或待后端配合**：旧面板与事项页应急卡共用 `useRecoveryCase` 的待核实记录键。旧页上的部分回复按钮（`AssistedOrderCard.vue`）会先撤回订单再请求应急补货，但旧页没有 `RecoveryFlow` 接收这个请求，说明步要到事项页才打开。

## 3. 后端改动时的同步清单

按顺序做：

1. **导出契约**：后端改了路由或 schema，在 `backend/` 下用项目虚拟环境运行 `python -m app.export_openapi`，更新 `docs/api/backend.runtime.openapi.json`。
2. **生成**：`corepack pnpm --filter @shopsteward/frontend api:generate`，更新 `app/types/backend.d.ts` 与 `server/utils/backend-routes.ts`，不要手改；之后 `api:check` 应输出 "Backend types and public route allowlist are current."。
3. **类型检查**：`corepack pnpm --filter @shopsteward/frontend typecheck`。§1.4 表里的不定结构字段不会报错，按字段名在本文和代码里搜索，逐处核对。
4. **代理与白名单**：新方法与路径进了 `server/utils/backend-routes.ts`；路径参数仍只含 `[A-Za-z0-9_-]`；新的文件上传或下载加进 `server/utils/knowledge-transfer.ts`；新的流式接口在 `server/api/backend/[...path].ts` 分流；请求体可能超过 256,000 字节时调整上限；PUT/DELETE 要改生成脚本与代理（§1.1）。
5. **身份与能力**：新增或改名能力时同步 `backend/app/api/router.py` 的 `capabilities`、`server/api/session.get.ts`、`app/types/models.ts` 的 `Session`，以及用到该开关的板块（§1.2）。
6. **状态、词表与推导**：枚举、业务码、错误码、句式变化时检查 `utils/glossary.ts`、`composables/useSpace.ts`、`utils/workPresentation.ts`、`utils/presentation.ts`、`utils/timeline.ts`、`utils/recovery.ts`（`flowState`、`recoveryTrigger`、`blockedReason`、`caseProblem`）、`utils/agent.ts`（工具名）、`utils/api.ts`（错误码文案），以及各组件里的映射表：`ForecastPanel.vue`、`useDocuments.ts`、`useAgentKnowledge.ts`、`MemoryPanel.vue`、`recovery/RecoveryCompare.vue`、`SourcingPanel.vue`、`RecoveryWorkspace.vue`、`LearningWorkspace.vue`、`SkillQualityCard.vue`、`ContextInspector.vue`、`TextBundleLineage.vue`、`space/TimelineCard.vue`（方案状态）、`space/OrdersCard.vue`（回执状态）、`SupplierReceipt.vue`（回复结果）、`pages/index.vue`（账本类型、提醒标题）。前端写死的默认值也要跟着改：建委托条件（§2.2）、方案卡选项（§2.5）、跟进间隔（§2.15）、寻源区（§2.6）。
7. **中英文**：新增或改动的中文界面文字加进 `app/i18n/en.json`；后端返回、经 `t()` 显示的中文（业务摘要、错误消息、时间线句式、试算正文）也要有对应条目；在 `frontend/` 下运行 `node scripts/check-i18n.mjs`（只查模板）。
8. **用例与模拟数据**：改了接口形状，就同步对应模拟的响应。

   | 板块 | 模拟与数据 | 用例 |
   |---|---|---|
   | 全局读取 | `tests/fixtures/overview.json`、`tests/fixtures/overview-pending.json`（键：`dashboard`、`catalog`、`missions`、`actions`、`inbounds`、`ledger-entries`、`alerts`、`sales`、`plan`、`timeline`） | 多数受控用例共用 |
   | 应急补货 | `tests/support/recovery-mock.ts`（有状态模拟，复刻求解器规则） | `tests/recovery-flow.spec.ts`；旧面板 `tests/recovery.spec.ts`；真实走查 `tests/support/sourcing_demo_browser.mjs`、`tests/support/recovery_browser.mjs` |
   | 事项与工作区 | 各 spec 内联 `page.route('**/api/**')` | `tests/work-intake.spec.ts`、`tests/task-workspace.spec.ts`、`tests/work-priorities.spec.ts`（纯函数）；真实 `tests/support/work_browser.mjs` |
   | 中英文 | `tests/support/i18n-fixture.ts` | `tests/i18n.spec.ts`、`tests/i18n-integrity.spec.ts`、`tests/settings-visual.spec.ts`；真实 `tests/support/i18n_business_browser.mjs` |
   | Agent | 各 spec 内联 | `tests/agent-progress.spec.ts`（纯函数）、`tests/agent-scope.spec.ts`、`tests/agent.spec.ts`（`AGENT_E2E=true`）；真实 `tests/support/progress_browser.mjs`、`tests/support/outcomes_browser.mjs` |
   | 文档、预测、概览、学习、新手指引 | 各 spec 内联 | `tests/documents.spec.ts`（另有 `tests/documents-transport.spec.ts` + `tests/support/documents_backend.py`，`DOCUMENTS_REAL=true`）、`tests/forecast.spec.ts`、`tests/overview.spec.ts`、`tests/learning.spec.ts`、`tests/onboarding.spec.ts` |
   | 真实全链 | — | `tests/business.spec.ts`、`tests/environment.spec.ts`（`ENVIRONMENT_E2E=true`）；试算 `tests/support/quantity_browser.mjs`；报价 `tests/support/quotation_browser.mjs` |

   单跑一个文件：在 `frontend/` 下 `node node_modules/@playwright/test/cli.js test tests/<文件>`（`playwright.config.ts` 只允许 loopback 地址）。
9. **构建**：`corepack pnpm --filter @shopsteward/frontend build`。
10. **本文**：更新受影响板块的接口表、依赖字段和限制，以及 §2.0 索引；有新的绕行或缺口时更新 §4。

## 4. 已知后端依赖与缺口

"核对"一列：**代码** = 后端现状已对照 `backend/` 代码或契约；**文档** = 后端现状取自 redesign 对应条目，本文只核对了前端的做法。

| # | 后端现状 | 核对 | 前端目前的做法 | 前端代码 |
|---|---|---|---|---|
| 1 | 已由 YH 10-19 修复：`backend/app/work_items/business.py classify()` 按方案种类读当前方案（`parse_plan`），应急方案按自己的有效期（从采用起算）、状态版本、委托版本、所选报价、预测版本与 `recovery_hash` 判断能否确认；待确认期间事项列表、详情、发消息、事项处理者都正常 | 代码 | `INVALID_STORED_DATA` 的中文保留（"这件事的方案正等待确认，刷新前先确认或拒绝它。"），正常情况下不再出现 | `utils/api.ts` |
| 2 | 已由 #25 修复：全部到货时 `backend/app/operations_cases/lifecycle.py settle()` 把 Case 置 `RESOLVED` 并写 `outcome`（店主登记到货与系统到货都会触发）；等原订单的 Case 在原订单到齐时同样结算 | 代码 | 结果以 `RESOLVED` + `outcome` 为准；所有已成交的采购都到齐、但还没读到 `RESOLVED` 时写"货已到齐，正在结算结果" | `utils/recovery.ts flowState()`、`outcomeOf()`、`recovery/RecoveryOutcome.vue` |
| 3 | 已由 #25 修复：Case 持有委托（已采用方案或选择等待）时例行检查一律跳过（`EMERGENCY_HOLDS`），应急方案不再被常规方案替换；方案过期或状态变化时 Case 转 `RECHECK_REQUIRED` 并带 `recheck_reason`；"等原订单"被尊重 | 代码 | 按 `recheck_reason` 写原因并给"重新比价"；常规方案收成一行只在采用之前出现 | `flowState()`、`recheckReason()`、`recovery/RecoveryCompare.vue` |
| 4 | 已由 #25 修复：有效期 `RECOVERY_TTL_SECONDS`（默认 1800 秒），采用后从采用时刻起算 | 代码 | 过期或 `stale` 时主按钮"重新比价"，按当前时钟重排需求再分析 | `useRecoveryFlow.again()` |
| 5 | 已由 #25 支持部分成交：回复 `outcome: 'partial'`；`POST /api/v1/actions/{action_id}/partial-acceptance`（`approver`，幂等键）按回复数量成交并释放余额；`CaseDetail.purchases[]` 记录各笔；部分成交后同一 Case 可再采用一家 | 代码 | 主按钮"按对方数量成交"，成交后"缺的找别家补上"；撤回整单降为文字链接；已成交的那部分在应急卡里登记到货 | `useRecoveryFlow.acceptPartial()`、`recovery/RecoveryOrder.vue`、`recovery/RecoveryPurchases.vue`、`AssistedOrderCard.vue` |
| 6 | 已由 YH 10-19 修复：经营时钟过了订单希望送达的时间（`purchase_snapshot.expected_arrival_at`）仍没有回复时，业务码为 `SUPPLIER_OVERDUE`（"供应商逾期未回复"，优先级 5，需要处理）；之前是 `AWAITING_SUPPLIER`（优先级 30） | 代码 | 状态徽章"供应商逾期未回复"（琥珀色），排在"待供应商确认"之前；可撤回 | `utils/glossary.ts statusBadge()` |
| 7 | 已由 YH 10-19 修复：订单撤回、被拒、失败或作废（`FAILED`/`CANCELLED`/`STALE`）后，`CaseDetail.action_id` 为空，`execution_status` 仍写它怎么结束的，订单留在 `purchases[]`；`plan_revision` 取方案 `recovery_intent.revision` | 代码 | `flowState()` 在没有当前订单时读 `execution_status`；`purchasesOf()` 合并采购记录，"当前这笔"只认当前版本的采购 | `purchasesOf()`、`flowState()`、`caseAction()` |
| 8 | 已由 YH 10-19 修复：寻源（`backend/app/sourcing/run.py start()`）与比较（`backend/app/operations_cases/processor.py`）都不放这件事排除的供应商：在这件事里拒单、失败、撤回、只供一部分的，加上建事项或修订时给的 `excluded_supplier_ids`（之后的版本沿用）；全部排除时寻源返回 `NO_OTHER_SUPPLIERS`；`CaseDetail.excluded_supplier_ids` 给出当前排除了谁，`sourcing.excluded` 记下那次寻源没读谁 | 代码 | 从入口带来的"不找…"随建事项发给后端（`excluded_supplier_ids`）；`excludedIds` 合并后端的列表、采购记录推出的和 sessionStorage 里的；比较里去掉它们并重算推荐；寻源后再修订一次的补救留作兜底，正常不再触发 | `useRecoveryFlow.ts`（`excludedIds`、`begin()` 与对应 `watch`）、`withoutSuppliers()` |
| 9 | 已由 YH 10-19 修复：情景需求仍以 `DailyDemand.settlement_at` 提交，后端按"第 1–7 天"读，分析时按当时经营时钟落定日期（`processor.py capture_snapshot()`），建事项后时钟往前走不再变成"需要补充" | 代码 | 每次建 Case 或修订仍按当前经营时钟生成七个结算时刻（与后端落定一致） | `settlements()`、`useRecoveryFlow.dated()/redated()` |
| 10 | 事项业务摘要不带应急补货建议（`WorkBusinessState` 没有相应字段；§18.7 第 11 项） | 契约 | 前端按方案、提醒、采购单与在途推断原因，并按求解器规则推演缺口 | `recoveryTrigger()`、`projectWithout()`、`demandFrom()` |
| 11 | Case 错误信息仍是英文，例如 `CASE_REVISION_CONFLICT` 的 "The Case has newer inputs; refresh before continuing"；YH 10-19 新增的错误码 `CASE_ALREADY_OPEN`、`CASE_REFRESH_REQUIRED`、`NO_OTHER_SUPPLIERS` 已同步到前端 | 代码 | 按错误码换成中文（含上述三个，以及备货委托、供应商资料类的 `MISSION_ALREADY_EXISTS`、`INVALID_MISSION_TRANSITION`、`MISSION_TERMINAL`、`MISSION_NOT_EDITABLE`、`SCHEDULE_VERSION_CONFLICT`、`RECOVERY_CASE_REVISION_REQUIRED`、`RESOURCE_NOT_FOUND`、`SUPPLIER_CONNECTED`、`DOCUMENT_ID_REPEATED`）；未登记的码显示后端原句，后端只给编码时写"暂时没能完成，稍后再试。" | `caseProblem()`、`utils/api.ts` |
| 12 | 已由 YH 10-19 修复：`GET /api/v1/me` 带 `purchase_channel`（部署的 `PURCHASE_CHANNEL`）；`backend/app/execution/repository.py` 在批准时决定 `channel`：寻源登记的报价一律 `assisted`，其余取请求体 `channel` 或 `purchase_channel` | 代码 | `channelFor()`：资料或寻源读出的供应商写"确认后由你把订单发给{供应商}"；其余按会话的 `purchase_channel`（`assisted` 同上，`simulator` 写"确认后系统直接下单"）；会话没有该字段时才按之前给它下过的订单推，推不出时不作说明；下单后以 `Action.channel` 为准（§2.6） | `useRecoveryFlow.channelFor()`、`recovery/RecoveryConfirm.vue`、`utils/recovery.ts flowState()`、`types/models.ts Session` |
| 13 | 时间线条目没有结构化参数，只有 `summary` 字符串（§16 第 2 项） | 契约 | 正则解析固定句式，读不出时原样显示（§2.4 列出了未登记的检查结果） | `utils/timeline.ts` |
| 14 | 委托时间线没有到货事件（§17.6 第 9 项） | 文档 | "最近变化"从店铺账本按采购单 id 匹配 `GOODS_RECEIVED`，只覆盖最近 30 条账本 | `useSpace.ts latestChange()` |
| 15 | 账本 `DEMAND_REVISED` 的四项变化为 0，只带 `remaining_demand_after`（§16 第 3 项） | 文档；字段为契约 | 演示条用推进前后的看板 `remaining_demand` 说明需求变化 | `PresenterBar.vue describe()` |
| 16 | 记忆条目没有时间与来源（`KnowledgeView` 只有每类的 `version`；§16 第 1 项、§17.6 第 8 项） | 契约 | 只显示每类记忆的版本 | `MemoryPanel.vue` |
| 17 | 事项结果没有 `surface` 字段（§16 第 5 项） | 契约 | 前端已能校验并使用 `result.surface`；目前全部由结果字段推导 | `surfaces/derive.ts`、`surfaces/validate.ts` |
| 18 | 店铺列表没有 `created_at`、`scenario_run_id`（§17.6 第 6 项） | 契约 | 示例店名的时点取开账账本、只记在本浏览器；只能推进本浏览器创建的场景 | `useDemoMode.ts`、`useShop.ts`（`ss.scenarios`） |
| 19 | 后台任务失败没有可区分的原因（§17.6 第 7 项）。`JobRun.error_code` 已在契约里，后端是否为推进失败填写可区分的码：待核实 | 文档 | 演示条按 `last_error` 文字推断原因 | `PresenterBar.vue failure()`、`useShop.waitJob()` |
| 20 | `job_runs` 表缺索引或保留策略，看板读取变慢（§17.6 第 10 项） | 文档 | 无绕行 | — |
| 21 | 没有表示"Agent 可用"的后端能力 | 代码 | 由前端环境变量 `NUXT_AGENT_ENABLED` 决定；记忆写入遇 503 / `AGENT_NOT_CONFIGURED` 转为只读 | `server/utils/backend.ts`、`useAgentKnowledge.edit()` |
| 22 | 已由 YH 10-19 修复：没有在途原订单时选择等待（"这次不补"），`control adopt_waiting` 当场结算：`RESOLVED`，`outcome.path = waiting`、缺货前后相同，时间线写"应急事项已结束：没有在途的原订单，这次不补货"，并排一次例行检查；"需重新分析"的 Case 没人处理时仍一直暂停例行检查 | 代码 | 卡片直接收成结果一行"应急补货已结束 · 这次不补"；"决定这次不补 / 结束这次应急补货"那一步保留作兜底 | `flowState()`、`recovery/RecoveryOutcome.vue`、`recovery/RecoveryReceive.vue` |
| 23 | 已由 YH 10-19 修复：最后一笔只成交一部分、店主还没决定缺口时，`backend/app/operations_cases/lifecycle.py settle()` 不结案（`gap_open()`）；找别家补上的那笔也到齐、或店主选了等待（`CASE_ADOPT_WAITING` 晚于 `RECOVERY_PARTIALLY_FILLED`）才结案 | 代码 | 应急补货进行中，这些采购只在应急卡里登记，登记不再需要说明后果（删去 `endsCaseIfReceived`、`endsCaseWith()`）；登记后卡片仍停在"缺的找别家补上" | `purchasesOf()`、`recovery/RecoveryPurchases.vue`、`useShop.awaitingArrival` |
| 24 | 已由 YH 10-19 修复：同一委托只能有一件未结束的 Case，再建返回 409 `CASE_ALREADY_OPEN` | 代码 | 只显示最新一件未结束的 Case（排除 `CLOSED`、`CANCELLED`、`RESOLVED`）；`CASE_ALREADY_OPEN` 写"这件商品已有一次应急补货在进行，先处理完它。" | `useRecoveryCase.load()`、`caseProblem()` |
| 25 | 已由 YH 10-19 修复：`RECHECK_REQUIRED` 或比较已过期（`stale`）时调 `analyze` 返回 409 `CASE_REFRESH_REQUIRED`，要先 `control`（`refresh`）或 `revise` | 代码 | 重新比价走 `revise` + `analyze`（旧面板走 `refresh` + `analyze`），不直接调 `analyze` | `useRecoveryFlow.again()`、`useRecoveryCase.control()` |
| 26 | 已由 YH 10-19 修复：`outcome.purchases[]` 按每笔记 `planned_qty`、`purchased_qty`、`received_qty`、`spend_minor`；`outcome.planned_qty` 仍是所有订单之和；多笔采购的时间线结算句是"应急事项已解决：N 笔应急补货共 X 件已全部到货" | 代码 | 两笔以上采购时按 `purchases[].accepted_qty` 写"补到 40 件（百川批发 10 + 安和商贸 30）"；时间线把多笔结算句改写为"应急补货完成：分 N 笔补到 X 件，已全部到货" | `outcomeOf()`、`recovery/RecoveryOutcome.vue`、`utils/timeline.ts` |
