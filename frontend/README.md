# ShopSteward 前端

<!-- md-alignment-2026-09-08 -->
## 三阶段当前行为与适用范围（2026-09-08增补）

第一阶段经[PR #11](https://github.com/yhnapoleon/ShopSteward/pull/11)合并；第二/三阶段及补齐项经[PR #12](https://github.com/yhnapoleon/ShopSteward/pull/12)合并为 `1bbcad5`。当前是“首页任务卡 → 同一Mission详情 → 方案/事实与常驻Agent区”，手机在业务结果与Agent间切换；真实工具状态、历史片段、试算/修订成果可恢复，原件入口固定引用版本，代码块可逐段复制。

这一组合版本包含后端支撑变化，需要 `0012_agent_progress`；试算不改变方案或账目，修订仍需独立采购确认，停止回答不撤销已提交变更。接口、条件和分批验收见[组合交付](../docs/reports/agent-workspace-delivery.md)与[运行时契约](../docs/api/backend.runtime.openapi.json)。

下文“任务工作区·2026-09-08”是第一阶段记录，其中“实时工具生命周期属于下一阶段”仅适用于当时。“文档中心不接Agent引用”限定文档中心自身的K1管理职责；当前Agent区已可核对历史证据，不代表文档中心已新增检索控制。早期“无迁移/后端不变”和Windows模型通过记录也仅对应各自那一轮。

本机模型保持关闭；语音、流式正文、多任务并发、完整A-01/L-01及远端检索的本轮联合验收未纳入。旧后端的工具完成摘要降级不等于完整支持当前成果/证据接口，缺能力时不能猜测结果。
<!-- /md-alignment-2026-09-08 -->

按v0.3高仿真原型实现的Nuxt/Vue前端，面向首版接口联调。默认三项主视图外，另提供只读的次级经营概览。当前视觉采用暖光磨砂、顶部导航、连续经营工作区、固定快捷浮条、资料入口和确认弹层；经营名称、数值、日期与状态取真实API，不使用原型的模拟账本或文字匹配来驱动采购。

后续界面迭代先读取[前端视觉规范](style.md)，沿用当前的材质、布局、控件、响应式与验证约定。经营功能与接口边界仍以下文为准。

## 任务工作区 · 2026-09-08

首页现在以任务卡片为入口，进入同一 Mission 的独立详情页；左侧为方案与业务事实，右侧为 Agent 工作过程和对话。工具完成记录、历史 run、引用定位、跨视图草稿、结束委托与失败恢复已接入既有接口。手机切换“方案与进展 / Agent 工作”。当前阶段不展示不存在的工具开始事件，语音与实时工具生命周期属于下一阶段。

实现、生产截图及验证边界见[任务工作区报告](../docs/reports/task-workspace-verification.md)。新功能以该报告为准，下方早期联调记录保留原验证时点。

## 实时工具生命周期 · 第二阶段

在第一阶段PR #11合并后，新增真实工具开始/完成/失败/中断、调用耗时、持久事件回放和同源SSE。界面自动使用新Run快照能力；旧后端仍显示工具完成摘要，事件流失败时使用轮询。后端需要 `0012_agent_progress` 迁移；本机模型开关不因本功能自动开启。实现、业务边界与真实串联证据见[第二阶段报告](../docs/reports/agent-progress-events.md)。

## 运行

服务分别是前端3000、API8000、模拟器8001；业务worker和PostgreSQL需要同时运行。Windows 完整启动与模型配置见[全栈联调报告](../docs/reports/frontend-agent-fullstack-test-report.md)。macOS 使用[开发指南](../docs/local-macos-development.md)。Windows 已完成官方 Luna 真实模型联调，是否启用取决于本机配置。

其他开发环境先按后端和模拟器README启动服务，再安装前端依赖、复制本目录`.env.example`为`.env`并配置后端地址。执行：

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @shopsteward/frontend dev --host 127.0.0.1 --port 3000
```

使用后端已有用户凭证，不新增账号系统。可在页面“更换后端用户身份”连接；凭证经后端验证后仅保存为HttpOnly、SameSite=strict会话，不进入localStorage或客户端bundle。`NUXT_BACKEND_TOKEN`仅在开发模式、localhost地址自动使用；生产构建不自动使用它。不要把开发服务器和管理员自动身份暴露到公网。正式身份系统、外部部署与店铺接入不属于本轮。

`infra/local_dev.py start`只给本机前端进程注入既有开发用户凭证和开发控制开关，不打印密钥。其余服务及此前Mac配置保留。没有配置真实模型时，Agent入口显示未启用，已有会话仍可读取。

## Windows 兼容边界

Windows 同学沿用后端/模拟器 README 中的 PowerShell 与 Docker 启动方式；不要运行 `infra/local_dev.py`，它只管理 macOS 本机环境。前端的 pnpm 命令和 API 接入方式保持通用。SQLAlchemy 的 asyncio 依赖修复适用于各平台，Agent 测试的 Windows SelectorEventLoop 分支保留。

PR 的 Windows compatibility 检查在 Windows runner 安装锁定依赖、校验前端类型/构建、验证 Windows 事件循环和基础业务/API测试。它不替代 Windows 上数据库、模拟器与浏览器的完整端到端联调。

## 基础用例

1. 在模拟器默认“联动后端”模式创建 SANDBOX，或从“联调控制”创建 SC-01。导入成功后成为后端当前环境，已打开的前端自动切换，旧场景保留。
2. 建立备货委托。前端等待业务worker产生方案，不自己计算推荐。
3. 比较0/20/40/80的后果；选中数量后核对具体方案，逐笔确认。
4. 查看采购受理、在途与到货；刷新页面继续原店铺与原任务。
5. 暂停/恢复主动检查、修改检查间隔；暂停不撤销已发生事实。
6. 联调控制按模拟器规则逐步推进到货、销售、需求修订、追加到货。
7. 查看警报、标记知晓、账本、历史决定与简报。知晓不等于解除风险。
8. 资料入口可在本地读取固定格式CSV、显示缺失项、保留原币种、换算和下载结果；不写经营账目。
9. “资料与简报 → 文档中心”管理当前店铺的原件、资料信息与版本；也可直接打开 `/?view=documents`。使用既有K1接口，不接智能检索或Agent引用。

不要照原型一天的时钟猜测事件顺序。当前模拟器分四步，第一和第四步需要存在可到货采购；其余约束由模拟器/后端决定。

## 接口分工

| 前端行为 | 后端接口 | 关键边界 |
|---|---|---|
| 身份/店铺/商品/状态 | GET `/api/v1/me`、`stores`、`catalog`、`dashboard` | 保留未知/过期，金额为整数分，显示时转换 |
| 委托和方案 | GET/POST `missions`；GET `plans/{id}` | 初始政策为SC-01约定；推荐和候选来自后端 |
| 改选数量 | POST `plans/{id}/revision`（本轮最小适配） | 复用原规划服务；成功后新版本仍待确认，不采购 |
| 明确确认/拒绝 | POST `plans/{id}/decision` | 精确plan/state版本、hash、用户身份与幂等键 |
| 原动作和到货 | GET `actions`、`inbounds` | SUCCEEDED表示采购受理，不表示到货 |
| 检查/暂停/恢复 | POST `missions/{id}/checks`、`control`；PATCH `schedule` | 检查记录与计划不等于后台永远在线 |
| 风险与记录 | GET `alerts`、`ledger-entries`、`missions/{id}/timeline`；POST `alerts/{id}/acknowledgement` | 风险知晓与解除分开；分页历史在轮询后保留 |
| 开发场景 | POST `/dev/v1/scenarios`、`{run_id}/advance`；GET `job-runs/{id}` | 仅开发控制+后端admin；异步完成后读取真实结果 |
| Agent会话 | conversations/messages、agent-runs、resume/cancel、followup | 官方Luna真实模型前端验收已通过；启用状态由本机配置决定 |
| 报价、展示偏好、整理要求 | 本地浏览器工具 | 当前后端没有报价接口；不算真实L-01 |
| 文档中心 | 既有K1 documents、versions、content、control | 上传/追加为multipart，其余沿用公开接口；已保存原件不等于已索引 |

上表未重复全部路径前缀，完整字段由[实际OpenAPI](../docs/api/backend.runtime.openapi.json)生成到`app/types/backend.d.ts`。`server/utils/backend-routes.ts`也由该契约生成，只允许注册的公开操作；内部事件与Agent租约工具不对浏览器代理。

页面启动探测当前运行后端是否提供`revision`。没有时仍能读取和比较候选，但不能确认非推荐数量；拒绝与推荐方案确认照常使用既有接口。旧后端关闭OpenAPI入口时也会保守禁用数量修订。

## 安全与恢复

- 同源Nitro代理隐藏后端凭证，写请求校验Origin；不代理任意URL，不暴露内部服务工具。
- 前端不写现金/库存，不改变现金底线来实现其他数量，不把聊天文字当采购授权。
- 确认弹层保留独立方案快照。后端版本/hash冲突时重新核对。
- 采购确认在浏览器sessionStorage暂存原请求和幂等键（不含凭证）。丢响应后重放同一确认或查询已有Action，不生成新采购来试错。
- 数据读取失败保留上次状态并阻止确认；来源FRESH、方案有效、任务ACTIVE仍要由后端最终校验。
- localStorage只保存店铺/场景引用及明确标为本地的报价记录，不维护业务账本。

## 已知差异，交给后端同学继续确认

1. **少买后的再建议。** 原型把少买作为本轮取舍。当前后端在采购20成功后清除临时数量上限，立即对剩余缺口再次推荐20；本轮前端如实显示，没有修改或隐藏这一规则。是否要保留取舍范围，后续再定义。
2. **数量修订接口。** 本轮只将Agent已用的evaluate逻辑提取为共享服务，并增加普通用户入口；算法、审批、资金和执行规则未变，无数据库迁移。同学可单独审阅这一适配，前端也有未接此接口的降级路径。
3. **场景控制引用。** 现有店铺列表未提供scenario_run_id；仅本浏览器创建的场景能直接推进。旧场景可查看，或新建一轮；没有让前端直读数据库补字段。
4. **报价/技能。** 报价解析、下载和整理要求当前仅本地实现；缺后端输入/产物/技能接口，不能当A-01/L-01产品完成。
5. **Agent与通知。** 官方 Luna 的发送、澄清/恢复、取消、偏好、方案修订及自主跟进已完成 Windows 前端真实模型验收。需要 `AGENT_ENABLED=true`、`AGENT_API_MODE=responses`、模型与密钥文件，以及独立 Agent worker；启动器同步设置前端能力开关。没有外部通知。
6. **名称与时间。** 使用后端实际商品名、供应商标识和经营时间，因此内容不照抄原型假名/固定时刻；视觉结构沿用原型。

## 代码组织

- `app/pages/index.vue`：三项主视图、经营概览入口与操作编排，确认时冻结方案。
- `app/components/BusinessOverview.vue`、`app/composables/useOverview.ts`：独立只读概览及查询上下文；不改变Agent/审批状态。
- `app/components/OverviewChart.client.vue`：只在概览打开后加载的ECharts图表。
- `app/composables/useShop.ts`：API读取、命令、轮询和持久引用；不复制经营规则。
- `app/components/`：决策、跟进、事实、会话、报价和弹层。
- `app/utils/`：错误/单位呈现、CSV工具；业务DTO使用生成类型。
- `server/`：同源代理与身份连接，公开路由白名单自动生成。
- `DocumentCenter.vue`、`useDocuments.ts`：按需加载的资料列表、筛选分页、信息编辑、原件/版本、权限状态和原提交恢复；独立于经营与报价状态。
- `server/utils/knowledge-transfer.ts`：只处理白名单中的K1上传和原件下载；按字节限制上传请求并保留下载响应头，其他JSON代理逻辑不变。
- `tests/`：真实业务E2E与明确标注的受控故障/兼容性/本地资料检查。

## 验证

```bash
corepack pnpm --filter @shopsteward/frontend api:check
corepack pnpm --filter @shopsteward/frontend typecheck
corepack pnpm --filter @shopsteward/frontend build
corepack pnpm --filter @shopsteward/frontend test:e2e
```

真实模型 E2E 需显式设置 `AGENT_E2E=true`，执行 `test:e2e` 即加入 `tests/agent.spec.ts` 三项测试，会产生模型用量。默认运行普通业务和受控故障测试，真实模型项明确跳过。测试会新建合成场景，保留结果。

E2E只允许loopback地址，需要已经运行的后端、模拟器、worker和前端；会新建独立合成店铺并实际执行模拟采购，保留数据供复核，不清开发库。Playwright需安装Chromium。前端原始测试输出在Git忽略的`var/frontend-e2e/`，汇总见[前端联调验证](../docs/reports/frontend-integration-verification.json)、[真实终态](../docs/reports/frontend-business-state.json)。

后端有新契约时，先在backend运行`.venv`对应Python的`-m app.export_openapi`，再运行`api:generate`和`api:check`。不要手改生成类型。

本轮不是正式部署、真实商家试用、完整可访问性认证或课程效果实验。

## 文档中心（2026-09-08）

支持PDF、DOCX、XLSX、CSV、Markdown和TXT，单文件上限20 MiB。按标题、分类、状态、商品或供应商筛选，资料和历史版本均可分页。可编辑标题、分类、可见范围及实体关联；有效期随原件版本保存。原件仅下载，不直接执行或内嵌预览。后端继续负责文件格式、权限、版本冲突及幂等校验。

operator/admin可上传；私有资料原件只有所有者可读，admin对其他成员私有资料仅能查看元数据。归档保留历史，恢复后才能读取版本和原件。上传成功始终如实显示原件已保存，尚未智能索引，不新增解析、OCR、RAG或Agent调用。

提交前把恢复用的幂等键、操作和文件指纹保存在按身份/店铺隔离的sessionStorage；不保存凭证或原文件正文。丢响应后保留原提交并禁止新写入，刷新后重新选择同名且hash一致的原文件再重试。首次上传或重试在计算文件hash期间离开原场景时，不再发起旧页面的写请求。重试回执可能是旧元数据，成功后总是GET最新详情。浏览器不允许会话存储时保留只读浏览并明确阻止无法恢复的写入。

文档中心复用暖光磨砂、原生dialog和现有图标，无新依赖。新增的dialog实例使用独立标题ID；已有弹层的关闭、焦点和忙碌语义保持。

验证与隔离复现见[文档中心验收记录](../docs/reports/frontend-documents-verification.md)。本次接入保持后端与其他业务模块不变。


## 经营概览（2026-09-08）

默认仍进入今日。点击“店铺此刻”或移动端事实摘要里的“经营概览”，或固定浮条的辅助入口，进入 `/?view=overview`；原有来源查询保留。返回今日继续原方案和会话，概览不提供采购确认动作。

现金/库存读dashboard；销售读sales/summary并用sales分页展开；采购到货读inbounds；完整ledger从期初计算现金余额变更，核对当前余额一致后才画事件顺序图。这不是历史可用现金，也不是等长日期曲线。有采购预留时，不把可用现金底线画到余额历史上。库存实色/斜纹只分别表示在库与在途。

销售默认以已同步模拟经营日期取最近7个UTC日，可选30日或不超过90日自定义区间。包括所选结束日，API查询为[from,to)。统计已记录销量和成交金额，不展示利润、回款或订单数；无记录不解释成真实零销量。销售日期不改变当前现金和库存。

概览独立保留context、分页和错误，12秒可见页面刷新；原有环境轮询与确认保护保持。不同请求不自动构成原子快照；不一致、过期或失败就地提示。不同场景请求通过代次和storeVersion保护。完整列表最多读取20页×100条，达到上限不显示完整总数或现金曲线。明细每页30条，加载更多时核对上下文。

ECharts6.1.0按模块引入Line/Bar、SVG渲染、提示与底线参考；图表引擎在进入概览后才下载，未引入React、整套UI组件库或WebGL特效。保留键盘方向键选择/回车明细、Escape关闭与焦点恢复、降低动效。

受控回归命令（全拦截API，不新建场景或采购）：

```bash
corepack pnpm --filter @shopsteward/frontend exec playwright test tests/overview.spec.ts
```

生产验证额外设置 `FRONTEND_URL=http://127.0.0.1:3012 OVERVIEW_PRODUCTION=true`，指向本机已经启动的生产预览，执行相同命令；此模式核对图表懒加载。生产服务器自身不自动使用本机管理员身份，测试会拦截会话和业务查询。正常不带该开关时仅跳过生产资产检查。原test:e2e中的业务用例仍会创建合成数据、模拟采购；本轮没有运行那些写入用例。

验证范围与未测项见[经营概览验证](../docs/reports/frontend-overview-verification.md)。


## 证据与业务成果（2026-09-08）

任务Agent区提供持久试算/修订比较，来源可打开准确历史片段；任务页从真实相邻方案读取版本回执，刷新后继续核对。原文/成果、权限与恢复边界、实际验证见[第三阶段报告](../docs/reports/agent-business-outcomes.md)。复用原审批、唯一Run同步器及原生dialog；未新增组件库。模型关闭时仍可读取既有历史，不能创建新模型运行。


### 原件下载与代码块复制补齐

历史来源弹窗可下载绑定版本的原件；核对文件大小/hash，下载前后校验权限，关闭或切换时停止旧请求。Markdown每段代码有独立复制按钮，保留原字符/换行并提供失败说明。两阶段合并交付的业务边界、迁移及组合验证见[交付说明](../docs/reports/agent-workspace-delivery.md)。
