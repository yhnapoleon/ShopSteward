# Windows 前端、后端与真实 Agent 全栈联调

日期：2026-09-07。代码基准：`YH / b7db9a0`，加本轮工作区改动；未提交或推送。

当前产品前端已与真实 backend、持久 simulator 和官方 `gpt-5.6-luna` Agent worker 贯通。页面发起的解释、只读试算、明确修订、澄清恢复、记忆和主动跟进均经过真实模型及 PostgreSQL；采购仍通过用户确认和原有确定性业务流程。

## 已启动服务

| 服务 | 入口 / 状态 |
|---|---|
| Nuxt 前端 | http://127.0.0.1:3000 ，已连接本机用户身份、启用 Agent |
| backend API / Swagger | http://127.0.0.1:8000/docs ，新版 revision 与知识接口已加载 |
| simulator 控制台 | http://127.0.0.1:8001/console/ |
| business worker | 独立进程，周期同步、业务检查及采购核对 |
| Agent worker | 独立进程，官方 `gpt-5.6-luna`、Responses API、并发 1 |
| PostgreSQL | 127.0.0.1:55432；backend 开发库已迁移到 `0010_knowledge` |

最新启动记录在 Git 忽略目录 `var/windows-stack-20260907-133412/processes.json`，日志同目录。记录中的 PID 只作定位，操作前必须核对进程身份。Docker Desktop 原已运行，本轮没有启动或重启 Docker Desktop。

开发数据库迁移前备份在 `var/full-stack-20260907/before-knowledge-migration.sql`。现有 `.env` 中的数据库与用户凭证保留；只新增/更新 Agent 的本机配置，密钥内容不写入源码、浏览器或报告。

## 修复与适配

1. 旧 8000 进程没有加载 `/plans/{id}/revision` 和知识接口；备份、迁移并重启 API/worker，前端现在使用完整现有契约。
2. 官方 Luna 在 Chat Completions 中返回 400，明确拒绝带推理的函数工具调用。最小 Responses 探针通过后，新增 `AGENT_API_MODE=responses` 配置，保留默认 `chat_completions` 兼容旧模型。适配器仅提取回答文本，同时保留独立的工具调用，避免将 Responses 协议块当作回答字符串。新增两项回归先失败后通过。
3. 刷新后 `active_run_id` 已清空时，前端原先无法恢复最近失败的 Run。现在从最后一条消息的 `run_id` 恢复，错误不会因刷新消失。
4. 澄清等待页面增加“停止本轮回答”，使用现有 cancel API。受控浏览器回归先复现失败，修复后通过。
5. 在线复核发现运维接口仍将 `agent_enabled` 写死为 false；已改为从 API 实际配置传入，真实 API + 专用 PG 参数化回归覆盖启用/禁用。API重启后前端session与monitoring均为true。
6. 新增 Windows 启动器 `infra/start_windows.py`，读取已有私有配置，同步前后端 Agent 开关和开发身份，隐藏启动 API、两类 worker、Nuxt 及必要时的 simulator。占用的 3000/8000 端口会拒绝启动；启动失败仅清理自己创建的进程。

## 本轮实测结果

以下为分批验证，不能拼称一次全量测试。

| 检查 | 实际结果 |
|---|---|
| backend + Agent（专用 PG / 跨服务测试库） | **308 passed**，130.98 秒，0 skipped |
| simulator | **23 passed**，6.37 秒 |
| 后续监控修复：队列/监控/API回归 | **33 passed**，10.20 秒（含新增2项配置分支） |
| 原有业务 Playwright 套件 | **8 passed**，4.3 分钟 |
| 官方 Luna Playwright 套件 | **3 passed**，4.4 分钟 |
| 新增受控 Agent 页面恢复回归 | **1 passed**，42.6 秒 |
| 前端类型与 API 生成一致性 | 通过 |
| Nuxt 生产构建 | 通过；依赖输出一条 Node exports 弃用警告 |
| 修改 Python 文件 Ruff / 格式 | 通过 |
| 开发库 Alembic 漂移与既有契约校验 | 通过 |
| 五类服务重启后的只读快照比对 | **4 个店铺、3 个会话完全一致** |
| 重启后桌面/390px 手机浏览器 | 实际现金与聊天可见，0 pageerror，无横向溢出 |

业务套件覆盖 SC01 全流程、双击确认、刷新持久化、暂停中到货、恢复、需求上修、少买生成新方案、拒绝与警报知晓、真实采购丢响应恢复，以及明确标为受控的旧接口降级、分页和本地报价工具。

真实模型套件覆盖：

- `get_plan` 解释 → `evaluate_plan` 只读试算；确认试算前后业务 State、当前 Plan、采购数量不变。
- `revise_plan` 生成 20 件待确认方案；用户点击确认后才形成唯一采购，现金 800 元、在途 20 件；刷新保留聊天与结果。
- `clarify` → 刷新 → 同 Run resume → `memory_edit` 成功保存 USER 偏好；再澄清、取消、发送新问题；读取偏好不再次写记忆。
- 页面开启主动解读，测试将真实 followup 周期配置为支持的最小 60 秒，采购事实触发持久 FOLLOWUP 回复；最后在页面关闭测试会话的主动解读。

重启前后保存的 8 个 Run 为 7 个 SUCCEEDED、1 个 CANCELLED，其中 1 个为 FOLLOWUP。消息、Run 输出、工具引用、偏好、状态、采购、到货和账本见[完整重启证据](../api/frontend-agent-restart-result.json)。早期 Chat Completions 失败保留在开发库和本轮日志中，不计入通过批次。

SC01 验收店铺 `store_73dd37c9b93f452e94063fe1f3ded3d5`：现金 **400 元**、应收 **200 元**、现货 **70 件**、在途 **0**、预留 **0**、采购 **2 笔**，重启后完全一致。真实 Agent 修订店铺为 `store_3d269c0b18a04ee8b3af61a52ccea713`；可从前端“联调控制”的店铺下拉框选择尾号 `2ccea713` 查看聊天与采购结果。

独立只读代码审查（含最终监控修复）无 P1/P2 发现。[机器汇总](frontend-agent-fullstack-verification.json)。

截图：[桌面](frontend-agent-desktop.png)、[手机](frontend-agent-mobile.png)。

## 复现

先手动启动 Docker Desktop，并按 backend/simulator README 准备已有数据库。首次配置官方 Luna：

```dotenv
AGENT_ENABLED=true
AGENT_MODEL=gpt-5.6-luna
AGENT_BASE_URL=https://api.openai.com/v1
AGENT_API_MODE=responses
AGENT_API_KEY_FILE=<本机密钥文件绝对路径>
AGENT_BACKEND_URL=http://127.0.0.1:8000
AGENT_WORKER_CONCURRENCY=1
```

确认旧项目服务已停止，从 backend 目录执行迁移，再从仓库根启动（不会自动迁移、启动 Docker 或结束未知进程）：

```powershell
# backend 目录
..\.venv\Scripts\python.exe -m alembic upgrade head
# 仓库根目录
.\.venv\Scripts\python.exe infra/start_windows.py
```

前端依赖按根 `packageManager` 与锁文件安装。以下命令在 frontend 目录直接使用已安装的工具，避免全局包管理器版本差异：

```powershell
node scripts/generate-api.mjs --check
node node_modules/nuxt/bin/nuxt.mjs typecheck
node node_modules/nuxt/bin/nuxt.mjs build
node node_modules/@playwright/test/cli.js test business.spec.ts
$env:AGENT_E2E='true'
node node_modules/@playwright/test/cli.js test agent.spec.ts
```

真实模型测试会产生模型用量，所有业务测试在开发库新建合成场景，保留数据。308 项回归仅运行专用 `shopsteward_test` / `shopsteward_sim_test`，不可将清理测试指向开发库。需要保留不同批次证据时，使用不同的 Playwright `--output` / JSON 报告路径。

重启验证：在 backend 目录执行 `python tools/verify_frontend_agent_restart.py --capture`，重启服务后执行同脚本不带参数。首次捕获选择最近三个会话和最近一个符合 SC01 终态的 Mission；该脚本用于本机完成 E2E 后的已有合成数据，不生成新业务，也不调用模型。

## 范围与边界

这是本机开发环境端到端验收，不代表生产部署或长期负载测试。报价 CSV 仍为现有明确标注的浏览器本地工具；K2–K5 文档解析、检索、Agent 文档工具和文档中心，以及真实预测未在本轮新增。K1 后端已部署，但完整 RAG 仍未实现。原件目录和 PG 仍需共同备份。

少买 20 件后的补足建议继续遵循既有后端规则，没有隐藏或改变临时上限清除语义。测试最后关闭了其主动解读开关；用户可在任一会话中自行开启。原有业务 worker 的自动同步和检查持续运行。
