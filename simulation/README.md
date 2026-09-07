# Persistent Simulator 与本地 Dashboard

2026-09-07 已增加可配置 SANDBOX、真实 PostgreSQL 持久化与本地控制台。保留原 SC01 固定剧本；产品 `frontend/` 独立开发。全部场景均为合成数据，金额存储为 CNY 整数分。

## 最快启动控制台

先由用户手动启动 Docker Desktop，并确认项目 PostgreSQL 已运行。助手和下面的启动器都不会启动 Docker Desktop。使用仓库根目录已有虚拟环境和 `.env` 配置：

```powershell
.venv/Scripts/python.exe simulation/tools/start_console.py --migrate --with-backend
```

打开 <http://127.0.0.1:8001/console/>。启动器会检查 8000/8001 是否空闲，增量迁移数据库，隐藏启动 simulator、backend API 与 business worker；Agent 关闭，不调用模型。后台日志和本次进程 PID 保存到 `var/simulator-console-时间戳/`。它不会覆盖 `.env` 或重置已有数据。

如果 backend 与 business worker 已在运行，省略 `--with-backend`，只启动 simulator。如果端口已占用，先使用已有页面；需要重启时先核对进程归属，不要重复启动 worker。启动器从现有 backend `.env` 读取用户 admin 身份供服务器联动使用；不把凭据写入浏览器或日志。没有该身份时仍可独立模拟。

## 使用方式

1. 默认使用**联动后端**：backend 初始化任务创建并导入场景，成功后成为当前经营环境，已打开的产品前端自动切换，随后继续同步销售、需求和到货事件。**独立模拟**只供显式选择的 simulator 单独调试，不改变当前经营环境。
2. 使用常规补货、低现金、库存充足模板，或者修改现金、库存、需求、采购单价、MOQ、包装、交期与活动期。每次创建独立 run；旧 run 可从场景记录重开。
3. SANDBOX 提供销售、需求修订、订单到货 Trigger。销售减少现货并增加应收，需求修订写入新预测事实；到货必须选实际已受理订单，可部分或全部收货，模拟时间至少推进至订单 ETA。
4. 观察事件记录、现金/应收/现货/在途/需求，以及 backend 已同步序号、经营快照、Mission、Plan 和警报。源序号和 backend 业务版本含义不同，界面分别呈现。

**联动创建导入经营数据并切换当前环境，不自动建立用户委托。** 在产品前端点击“开始备货跟进”即可为新环境建立 Mission；Agent读取该任务所绑定店铺的实际数据，采购仍需用户确认。控制台不提供直接采购或绕过审批的按钮。历史场景、任务和账本保留，查看历史 run 不会重新激活它。

SC01 只能按原剧本推进；SANDBOX 只能自由触发。所有 SANDBOX 写入带幂等键和当前源序号；冲突时刷新后重试，网络结果不明时界面保留原请求供显式重试。服务重启后状态和幂等记录仍保留。

控制台默认关闭，显式 `SIM_CONSOLE_ENABLED=true` 才注册。只接受 loopback peer/Host，写 API 检查同源、JSON 与自定义请求头。它是本机开发工具；尚无多人远程控制、退货、自动随机流量、故障注入、退款回款、RAG 或真实数据集导入。报价与预测有真实时间有效期，过期风险仍由原 backend 机制处理；需要新的完整演示时创建新场景。

## 验证与接口

23 项 simulator PostgreSQL 测试覆盖旧剧本、可配置初始化、幂等并发、非法操作回滚、部分到货、游标和本地访问边界；backend＋Agent 226 项回归通过。完整证据见 [测试报告](../docs/reports/simulator-console-test-report.md) 和 [真实 HTTP 验收结果](../docs/api/simulator-console-acceptance-result.json)。

```powershell
# 创建新的联动合成场景，创建 Mission 并通过原 API 批准模拟采购，再验证来源变化
.venv/Scripts/python.exe simulation/tools/verify_console.py
# 重启 simulator 后，只读取已保存场景并重放原请求键
.venv/Scripts/python.exe simulation/tools/verify_console.py --verify-restart
# 不连接数据库或读取凭据，导出实际注册的 API
.venv/Scripts/python.exe simulation/tools/export_console_contract.py
```

以上三条命令在仓库根目录执行。验收程序会保留新建的合成场景，结果文件记录 run/store/mission/plan/action ID；不会清空已有场景。

服务 API 有 8 个业务操作与 ready；控制台开启时增加 10 个操作（含页面入口）。[默认服务契约](../docs/api/simulation.runtime.openapi.json)、[控制台开启时契约](../docs/api/simulator-console.runtime.openapi.json)。新增服务接口为 `GET /sim/v1/runs`、`GET /sim/v1/runs/{run_id}`、`POST /sim/v1/runs/{run_id}/triggers`；`POST /sim/v1/runs` 支持 SC01 与 SANDBOX。服务 API 仍需服务 Bearer。

## 原有 SC01 与采购协议

已实现独立、持久化的五个接口，以及 `/health/ready`：

- `POST /sim/v1/runs`：SC01初始现金100000分、现货20、剩余需求60；原始初始化快照与当前世界分别保存，重复创建不会重置世界。
- `GET /sim/v1/runs/{run_id}/events`：持久事件分页读取。
- `POST /sim/v1/purchases`：保存明确 ACCEPTED / REJECTED 回执；受理时扣现金、增加在途、追加 PURCHASE_ACCEPTED 同事务。
- `GET /sim/v1/purchases/{action_id}`：查询已提交回执；404不表示采购请求一定未在处理中。
- `POST /sim/v1/runs/{run_id}/advance`：推进SC01到货、销售10、剩余需求修订70、第二阶段到货。到货按 action_id 排序，取订单实际未收数量。

所有 POST 必须带 Idempotency-Key。服务token代表固定 `backend-service` principal；命令以 principal + operationId + key 唯一，采购另以全局 action_id 唯一。相同action内容使用新命令键仍返回原回执；不同内容返回409。采购和advance持有run行锁；事件计数器、命令响应、采购累计到货量均持久化。

GET不产生销售、不自动到货、不推进模拟时间。advance多步请求在任何一步阻塞时全部回滚（409 SCENARIO_STEP_BLOCKED），原键可在满足条件后重试；超出四步范围返回409 SCENARIO_FINISHED。成功键永远回放原结果。报价过期、SKU/供应商不匹配、MOQ/包装、金额不符、现金不足或ETA超出场景范围产生持久REJECTED回执。当前报价固定，不提供刷新、PENDING或运行时故障注入接口。

## 数据库与配置

与backend使用同一个PostgreSQL实例，但使用独立数据库、账号及Alembic迁移：本机已配置 `shopsteward_sim` / `shopsteward_sim_test`，owner为 `shopsteward_sim`。应用不导入backend代码、不读取backend表。

新环境先以PostgreSQL管理员创建登录角色与这两个数据库，数据库owner设为该角色。可在psql交互式执行 `CREATE ROLE shopsteward_sim LOGIN;`，用 `\password shopsteward_sim` 设置随机密码，再执行 `CREATE DATABASE shopsteward_sim OWNER shopsteward_sim;` 和对应测试库创建语句。复制 `.env.example` 为 `.env` 并填写连接URL和随机服务token；不要覆盖已有本地配置。

`SIM_SERVICE_TOKEN` 至少24字符；backend/.env中的 `SIMULATION_TOKEN` 必须与它相同。该凭证代表backend服务，不向前端提供；backend内部推送接口另使用AUTH_TOKENS中的service身份和明确的scenario_run_ids授权。

## 启动

simulation目录执行：

```powershell
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen python -m simulator
```

地址 `http://127.0.0.1:8001`，Swagger `/docs`，Bearer使用服务token。API与backend/worker分别启动，导入模块时不迁移或连接数据库。

当前迁移头为 `sim_0003_controls`；升级只增加持久场景配置，保留旧 run、快照和幂等记录，无需清库。ready 检查迁移头及采购、事件、run、命令表。运行时导出的接口见 `../docs/api/simulation.runtime.openapi.json`，共享行为契约见 `../docs/simulation-contract.md`。

创建请求为 `{"scenario":"SC01"}`，并带 `Idempotency-Key`。事件请求必须提供 `after_sequence=0` 等游标，limit为1–100；超过源头返回409 `EVENT_CURSOR_AHEAD`。分页在只读REPEATABLE READ快照中读取事件和源头序号。

## 测试

simulation目录执行；测试只能连接指定的测试库：

```powershell
$simEntry = Get-Content '.env' | Where-Object { $_.StartsWith('SIM_DATABASE_URL=') }
$env:TEST_SIM_DATABASE_URL = ($simEntry.Substring(17) -replace '/shopsteward_sim$', '/shopsteward_sim_test')
$env:SIM_DATABASE_URL = $env:TEST_SIM_DATABASE_URL
uv run --frozen alembic upgrade head
Remove-Item Env:SIM_DATABASE_URL
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen alembic check
```

其中原12项真实PostgreSQL集成测试覆盖身份、跨应用实例回执与幂等回放、并发同action/同命令、持久拒绝、完整SC01、advance整批回滚、真实多订单到货量与排序、跨run键冲突、报价有效期/ETA边界、历史快照、分页/空页/游标冲突；成功响应按services.openapi.json校验。测试只连接 `shopsteward_sim_test`，按唯一run隔离数据，不清空数据库。模拟器JSON响应DTO与backend独立维护，遵循同一服务契约。

复用仓库根目录虚拟环境时，可将以上 `uv run --frozen` 替换为 `..\.venv\Scripts\python.exe -m`（启动用 `..\.venv\Scripts\python.exe -m simulator`）。模拟器测试证明自身持久行为；backend跨进程采购、UNKNOWN恢复和唯一入账由backend集成验收另行证明。
