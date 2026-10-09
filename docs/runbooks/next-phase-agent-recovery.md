# 下一阶段运行与验收手册

更新：2026-10-02。功能实现范围、已验证结果与尚未接入项见[交付说明](../reports/2026-10-02-next-phase-delivery.md)。完整产品/研究目标仍以[整合设计](../superpowers/specs/2026-09-30-next-phase-integrated-design.md)为准。

## 启动依赖

沿用根 README 的依赖安装、数据库与模拟器配置。新的业务迁移头是 `0015_operations_cases`，新增 Case/版本/方案/事件表及 `missions.planning_context`。先确认 `DATABASE_URL` 指向要升级的数据库，再在 `backend/` 执行 `python -m alembic upgrade head`，随后重启业务 API、业务 worker 和前端。本轮只迁移了隔离测试库，没有升级日常使用库。

业务 worker：`python -m app.worker --profile business`。它现在同时执行显式开启的 Case 跟进；仅运行 API 不会定期跟进。Mission Agent 仍使用独立的 `python -m app.worker --profile agent`。启动器/环境文件说明沿用根 README，不在代码中嵌入凭据。

恢复求解和普通 Case 工作区不需要模型。前端通过 `/api/v1/me` 的 `operations_cases` 能力自动显示入口，新端点已进入生成的同源代理白名单。

## 使用流程

1. 打开已有备货委托的任务详情，展开 **供应异常应对**，填写问题、应急预算及可选数量上限。
2. 选择最多三家结构化报价。报价不超过三家时可留空比较全部。有效 v6 日预测可直接使用；缺少日预测时，在“补充七日需求情景”中填写七个非负整数和首日 UTC 结算时间。它们被标为用户假设，不冒充预测。首日结算必须落在当前业务时钟起的首日内，后续逐日相隔 24 小时。
3. 分析后查看等待/补购候选、逐日缺货与库存、现金、拒绝原因及证据。这里只形成分析。
4. 选择 **生成待确认方案**，在原采购确认卡中核对供应商、金额、现金与到货时间。确认仍受现有审批权限和发送前校验约束。同量不同供应商按候选 ID 绑定。
5. 改预算后重新分析会创建新版本，旧候选不能采用。依据过期使用 **重新核对最新依据**。响应丢失时使用 **核实并重试原提交**，沿用原请求与幂等键。
6. 可显式开启 **自动跟进**。业务 worker 约每 30 秒核对执行/到货/版本，变化事件去重；依据变化时要求重新分析，不自动采购。采购受理、部分收货与全部收货分别呈现。缺少真实目标结果证据时，窗口结束标未知结果，不声称达成经营目标。
7. 结束 Case 不取消已发送采购，也不结束原委托；可新建独立恢复事项。单个 Case 跨版本最多一笔已受理应急采购。

## 模型与上下文配置

| 配置项 | 当前行为 |
|---|---|
| `AGENT_ENABLED` | 控制 Mission Agent；沿用当前部署设置 |
| `AGENT_MODEL` / `AGENT_BASE_URL` / `AGENT_API_KEY_FILE` | 沿用已有配置，不自动切换模型或复制 key |
| `AGENT_API_MODE` | `chat_completions` 或 `responses`，按服务支持选择 |
| `AGENT_CONTEXT_ENABLED` | 默认 `true`；新运行冻结配置，旧运行保持已有语义 |
| `AGENT_PROFILE_ID` | 默认 `mission-configured`，用于记录配置身份 |
| `AGENT_REASONING_EFFORT` | 可选；两种协议都实际传入，需服务支持该值 |
| `AGENT_MAX_INPUT_TOKENS` | 默认 24000；当前是保守 UTF-8 上界估算，并留 10% 余量 |
| `AGENT_MAX_OUTPUT_TOKENS` | 默认 2048 |
| `AGENT_MODEL_TIMEOUT_SECONDS` | 默认 30 秒 |
| `AGENT_CASE_EXPERTS_ENABLED` | 默认 `false`；启用后 Case 分析提交后运行解释专家 |
| `AGENT_CASE_MODEL` / `AGENT_CASE_API_MODE` | 单独显式配置 Case 模型；协议默认 `responses` |
| `AGENT_CASE_STRATEGY` | 协作策略，默认 `adaptive_multi`；可选 `fixed` / `single` / `static_multi`，对应实验编号 R0–R3 |
| `AGENT_CASE_TEXT_BUNDLE` | 专家提问所用的文本版本，默认 `seed`；版本文件带哈希且不可覆盖，演化与评测见[协作策略评测说明](strategy-evaluation.md) |
| `AGENT_CASE_ROLE_MODELS` | 可选 JSON，如 `{"evidence":"<模型ID>"}`；按角色指定模型并在运行开始时冻结，未列出的角色用 `AGENT_CASE_MODEL` |

先保持已验证可用的 Mission 模型；Case 模型独立启用。设计中的 Sol/Luna/Astra 是实验候选，并不表示当前账号已具备对应 API ID、配额或价格。本轮没有替换用户现有模型配置，也没有调用付费模型。专家默认共用一个 Case profile；`AGENT_CASE_ROLE_MODELS` 只改变某角色使用的模型，不改变其工具和权限。哪种分工更好尚无实验数据。

专家只读取当前 Case 冻结的授权证据/求解器输出。最多两个并发，委派深度一；根任务共享 14 次模型调用、28 次工具调用、150 秒预算，四种策略用同一份预算、同一份证据和同一输出格式（2026-10-08 接入）：

- `fixed`（R0）：一次无业务工具的说明调用。
- `single`（R1）：一个 Agent 持有全部专家工具，可用完整根预算，不委派。
- `static_multi`（R2）：三个专家全部启动，不补查。
- `adaptive_multi`（R3，默认）：先 evidence、impact；多报价或求解器没有可行补购时加 options；之后最多一次定向补查。补查优先处理代码检出的适用性分歧，其次是专家提出的第一条请求，其余请求记入 `followup.unserved`，不循环。

结果由代码合并（`expert_analysis.merged`）：多个专家重复同一说法只算一份依据；`calculation` 类说法未引用求解器方案 ID 的不采信；同一对象的适用性结论相互矛盾时，只有那一次补查能裁决，否则两边都不发布并标为部分完成；专家的澄清请求合并成一个问题。路由只看结构化事实（报价数、可行补购数），不看措辞。每次发送前持久化预算/请求，取消、改口或撤权阻止后续调用；已发送调用继续入账。未知 usage/cost 不记为零。专家输出不改变求解器数值或采购许可。

离线评测时用 `shopsteward_pt.case_eval.strategy_trace.strategy_trace(...)` 把一次 `expert_analysis` 转成可评分的 `CaseTrace`。经营事实必须由调用方的可信 oracle 提供；该函数只附加运行账本自身能证明的 `collab.*` 诊断项，不能替代任务成功判据。

在 Agent 工作区打开 **查看上下文记录**，可见冻结模型、任务来源/约束、选取与排除理由、调用状态和实际/未知用量。只有可访问该会话的用户能够读取。当前 TaskFrame 是有界解析：精确预算、数量上/下限与等量、取消约束及工具作用域意图；原句/字符范围可核验。未识别原文保留，必需输入超预算明确失败，没有宣称任意自然语言压缩或完整自动摘要。

## 离线 rubric

详见 [Rubric v1 使用指南](../../posttraining/rubrics/agent_case_rubric_v1/README.md)。入口是 `python -m shopsteward_pt.case_eval`，支持 `validate`、`score`、`report`、`schemas`；在已安装 `posttraining` 包或包含 `posttraining/src` 的 Python 环境中运行。

新旧评分独立。`true / false / null` 分别表示确认成功、确认失败、证据/评审不足。任何关键检查即使未列入普通 required 列表，也必须参与成功判断。语义复核绑定精确 case、trace、rubric、response 哈希。九个随附示例都是开发样例，不能作为 CE48/OPS48 成绩或简历提升百分比。

## 验证

数据库测试只使用迁移后的 `shopsteward_test`；模拟器测试使用独立 `shopsteward_sim_test`。设置 `TEST_DATABASE_URL`、`TEST_SIM_DATABASE_URL` 及测试进程自己的 `DATABASE_URL`、`SIM_DATABASE_URL`，禁用模型。不要让单元/集成测试继承日常数据库 URL。先创建仓库内的 `var/next-phase-tests`；本机系统临时目录存在权限问题，因此命令显式设置 `--basetemp`，并禁用缓存。

```powershell
# 从各包目录运行，使用已安装 workspace/测试依赖的 Python
python -m pytest tests -q -p no:cacheprovider --basetemp=../var/next-phase-tests/backend --tb=short  # backend/
python -m pytest tests -q -p no:cacheprovider --basetemp=../var/next-phase-tests/agent --tb=short    # agent/
python -m pytest tests -q -p no:cacheprovider --basetemp=../var/next-phase-tests/posttraining       # posttraining/

# frontend/；浏览器回归需先启动本地前端
pnpm typecheck
pnpm build
pnpm api:check
pnpm exec playwright test tests/recovery.spec.ts tests/task-workspace.spec.ts tests/agent-progress.spec.ts tests/work-intake.spec.ts
```

项目固定 `pnpm@10.17.1`，使用匹配版本，避免其他全局版本自动改写 workspace 设置。依赖已经安装时，浏览器命令也可直接运行 `node node_modules/@playwright/test/cli.js test tests/recovery.spec.ts tests/task-workspace.spec.ts tests/agent-progress.spec.ts tests/work-intake.spec.ts`；类型/代理检查可用 `node scripts/generate-api.mjs --check`。

后端三个可选真实浏览器用例默认跳过。先完成前端 build，再给测试进程设置 `PROGRESS_BROWSER_E2E=true`、`OUTCOMES_BROWSER_E2E=true`、`WORK_BROWSER_E2E=true` 可纳入全量运行；它们自行启动本地 Node/HTTP 服务，使用已安装的 Chromium，不调用真实模型。Windows 下只对这些浏览器用例使用支持子进程的 Proactor，其余数据库测试保持原 Selector 配置。

**PostgreSQL 测试必须串行运行。** 多个现有测试模块会清理全局 job 队列，并行运行会干扰彼此的 fixture。本轮曾复现此干扰，顺序复验已区分环境竞争与业务失败。

真实 HTTP 浏览器夹具：在设置了 `TEST_DATABASE_URL`、`PYTHONPATH`（含 `backend`、`agent/src`）的独立测试环境中，运行 `python backend/tests/support/recovery_browser_api.py`。它仅接受 loopback 上名为 `shopsteward_test` 的数据库，在 `127.0.0.1:18000` 提供 API，并将无凭据的 fixture 标识写到 `var/next-phase-tests/browser-state.json`。它用“前四日有需求、无旧在途”的专用浏览器情景；带旧预付订单的金标准由 PostgreSQL Case 集成测试独立覆盖。

另启构建后的前端，设 `NUXT_BACKEND_URL=http://127.0.0.1:18000`、`NITRO_HOST=127.0.0.1`、`NITRO_PORT=18001`，运行 `node .output/server/index.mjs`。从 `frontend/` 设置 `RECOVERY_FRONTEND=http://127.0.0.1:18001`、`RECOVERY_FIXTURE=../var/next-phase-tests/browser-state.json`、`RECOVERY_TEST_TOKEN` 为 `test_missions.py` 中固定的 operator 测试凭据，再运行 `node tests/support/recovery_browser.mjs`。可选 `RECOVERY_OUTPUT=../var/next-phase-tests` 保存截图/结果。该夹具只在 loopback 暴露固定测试身份，不应部署。
