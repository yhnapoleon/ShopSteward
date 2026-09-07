# Persistent SC01 simulator — B0-05

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

当前迁移头为 `sim_0002_purchases`；升级会保留旧run和其创建幂等记录，无需清库。ready检查迁移头及采购、事件、run、命令表。运行时导出的接口见 `../docs/api/simulation.runtime.openapi.json`，共享行为契约见 `../docs/simulation-contract.md`。

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

12项真实PostgreSQL集成测试覆盖身份、跨应用实例回执与幂等回放、并发同action/同命令、持久拒绝、完整SC01、advance整批回滚、真实多订单到货量与排序、跨run键冲突、报价有效期/ETA边界、历史快照、分页/空页/游标冲突；成功响应按services.openapi.json校验。测试只连接 `shopsteward_sim_test`，按唯一run隔离数据，不清空数据库。模拟器JSON响应DTO与backend独立维护，遵循同一服务契约。

复用仓库根目录虚拟环境时，可将以上 `uv run --frozen` 替换为 `..\.venv\Scripts\python.exe -m`（启动用 `..\.venv\Scripts\python.exe -m simulator`）。模拟器测试证明自身持久行为；backend跨进程采购、UNKNOWN恢复和唯一入账由backend集成验收另行证明。
