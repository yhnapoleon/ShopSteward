# Backend B0-01 至 B0-07

<!-- md-alignment-2026-09-08 -->
## 任务工作区所需后端支撑（2026-09-08增补）

[PR #12](https://github.com/yhnapoleon/ShopSteward/pull/12)组合版本需要迁移至 `0012_agent_progress`：新增Run进度序号、`agent_run_events` 与 `agent_tool_activity`，就绪检查验证这些结构。继续使用本模块既有迁移/启动命令，先核对目标数据库；独立Knowledge库的迁移不替代业务库迁移。

Agent桥接层提供真实工具开始/完成/失败/中断记录、事件回放/SSE、历史证据和结构化成果读取；修订结果增加原方案关联。业务目标、调用条件和验证见[组合交付](../docs/reports/agent-workspace-delivery.md)。规划、Mission、库存/现金账本、审批执行、业务调度和Agent主体源码未在此三阶段修改，不增加采购自主权限。

下文B0接口数和旧阶段边界保留历史用途；当前公开字段/路径以[运行时契约及增补](../docs/api/README.md)为准，不把已有设计稿的planned标记当作运行时不可用证明。
<!-- /md-alignment-2026-09-08 -->

后续已实现 B2-A Agent 框架：会话/Run、受限工具、记忆与任务 Skill、方案试算与修订、独立 Agent worker 和持久跟进。启动与 API 接入见 [Agent README](../agent/README.md)。当前迁移 head 为 `0009_agent_scopes`；原业务 worker 仍是默认 profile，Agent 不在线时原业务链路仍可工作。

已实现运行基础、业务状态/事件账本、Mission/规划、警报/看板/历史，以及B0-05精确审批、采购发送、资金预留、回执核对和到货入账。独立API/worker/simulator的显式完整SC01及重启回放已验证。B0-06已实现持久周期派发、Schedule配置、事件合并和持续新鲜度检查；自动SC01及三进程重启验收见 `docs/api/b0-06-periodic-smoke-result.json`。

B0-07已完成组合故障/并发验收，修复调度候选饥饿与孤立Action恢复阻塞。backend146项、simulator12项通过；报告见[测试报告](../docs/reports/b0-07-test-report.md)。从仓库根运行 `.venv/Scripts/python.exe backend/tools/verify_resilience.py` 可复现双worker真实进程故障与重启验收：要求8010～8013空闲且没有其他活跃worker，使用开发库新场景，保留数据/日志，最后停止自建服务。测试覆盖值和时长见报告，不代表生产SLA。

## 当前可用接口

| 接口 | 用途 | 身份 |
|---|---|---|
| GET /health/live | API活性，不依赖数据库 | 无 |
| GET /health/ready | 数据库、迁移版本与基础表就绪 | 无 |
| GET /api/v1/monitoring/status | worker心跳、待执行数量 | user admin |
| GET /api/v1/job-runs/{job_run_id} | 持久任务状态与结果 | 对应门店的user；全局任务仅admin |
| GET /api/v1/catalog?store_id=... | 已导入商品与报价 | 对应门店user或admin |
| POST /dev/v1/scenarios | 持久化初始化任务，202 | 开发/测试环境user admin |
| POST /internal/v1/events/batches | 整批事件入账 | 被授予scenario_run_ids的service |
| POST /api/v1/missions | 创建Mission并登记首次检查 | 门店operator或admin |
| GET /api/v1/missions?store_id=... | 按状态筛选、游标分页 | 门店user或admin |
| GET /api/v1/missions/{mission_id} | Mission、当前方案、Schedule配置 | 门店user或admin |
| POST /api/v1/missions/{mission_id}/control | pause/resume、complete/cancel | 前两项operator，后两项approver；admin均可 |
| PATCH /api/v1/missions/{mission_id}/schedule | 配置周期/启停，版本校验 | 门店operator或admin |
| POST /api/v1/missions/{mission_id}/checks | 异步检查，返回JobRun或合并已有检查 | 门店operator或admin |
| GET /api/v1/missions/{mission_id}/plans | 方案历史、游标分页 | 门店user或admin |
| GET /api/v1/plans/{plan_id} | 完整快照、候选与采购建议 | 门店user或admin |
| POST /api/v1/plans/{plan_id}/decision | approve返回202、reject返回200；精确版本/hash | 门店approver或admin |
| GET /api/v1/actions/{action_id} | 采购状态、原始快照与确认回执 | 门店user或admin |
| POST /dev/v1/scenarios/{run_id}/advance | 持久推进任务，随后拉取源事件 | 开发/测试环境admin |
| GET /api/v1/dashboard?store_id=... | 一致State、新鲜度、风险/任务数、检查时间 | 门店user或admin |
| GET /api/v1/alerts?store_id=... | 可选mission_id/status筛选、游标分页 | 门店user或admin |
| POST /api/v1/alerts/{alert_id}/acknowledgement | 知晓警报，无请求body | 门店operator或admin |
| GET /api/v1/missions/{mission_id}/timeline | 可追溯业务历史、游标分页 | 门店user或admin |

monitoring按 `simulation:<run_id>` 列出数据源；只有拉取追平后才记录last_success_at，缺页时STALE，默认30秒后过期。worker持续运行时默认每5秒派发源同步，每60秒派发源新鲜度检查。`worker_probe`只执行数据库探针，不代表经营检查或SC01。worker只领取已经注册的handler。

## 配置与依赖

Python >=3.11（本机验证3.12.13），PostgreSQL17.11，依赖由根目录uv.lock固定。本机已创建随机密码/演示token并保存在Git忽略的 `infra/.env`、`backend/.env`；不要复制到文档或提交。开发库shopsteward、测试库shopsteward_test，数据库只绑定127.0.0.1:55432。

新环境安装uv和Docker Desktop，参考两个目录中的 `.env.example` 创建配置，不覆盖已有配置。POSTGRES_PASSWORD和DATABASE_URL使用同一随机密码。AUTH_TOKENS由服务端映射身份，格式为：

```json
[{"token":"<自行生成至少24字符的随机token>","principal_id":"local-admin","kind":"user","roles":["admin"],"store_ids":[]}]
```

可用PowerShell的 `[guid]::NewGuid().ToString('N')` 生成随机值，不使用示例占位符。未配置token时受保护接口返回401；服务身份不能访问user专属接口；普通用户必须有角色及对应store_ids。

根目录执行 `uv sync --project backend --frozen`。若Windows默认uv缓存不可用，先设置：

```powershell
$env:UV_CACHE_DIR = Join-Path $env:TEMP 'shopsteward-contract-cache'
$env:UV_LINK_MODE = 'copy'
```

## 启动

从应用仓库根目录：

```powershell
docker compose --env-file infra/.env -f infra/compose.yaml up -d --wait
Set-Location backend
uv run --frozen alembic upgrade head
uv run --frozen python -m app
```

API为 `http://127.0.0.1:8000`，Swagger为 `/docs`。另一个终端进入backend目录：

```powershell
uv run --frozen python -m app.worker
```

初始化还需要按 [Simulator说明](../simulation/README.md) 启动8001服务；本机独立开发/测试数据库及凭证已配置。backend/.env设置SIMULATION_BASE_URL及SIMULATION_TOKEN。

API不自动启动worker或迁移。Ctrl+C让worker停止领取并限时排空；未完成技术任务按租约恢复。`--once`最多处理一条任务后退出，适合诊断。`APP_ENV=production`默认关闭Swagger/OpenAPI入口。

## 验证持久任务

backend目录执行：

```powershell
uv run --frozen python -m app.cli enqueue-probe --key local-probe-1
```

返回job_run_id；相同key返回同一资源。连续worker会执行它；未运行连续worker时可执行 `uv run --frozen python -m app.worker --once`。在Swagger中使用backend/.env的user admin token授权，GET job-runs查看状态与result。

队列使用短事务、数据库时钟、SKIP LOCKED、唯一dedup_key与lease_token。错误/过期token不能完成或续租。已明确幂等的worker_probe、initialize_scenario、sync_events、check_mission允许租约恢复，最多3次领取；临时simulator错误以原job ID退避重试，2/4秒后仍失败则终止。业务写入、后续任务与租约校验在同一事务提交；过期租约或任务超时回滚业务写入。采购不由通用恢复器盲目重发。

## 初始化与业务数据

在backend Swagger使用user admin授权，POST `/dev/v1/scenarios`，body为 `{"scenario":"SC01"}`，填写新Idempotency-Key。返回202后通过GET job-runs轮询；成功result.references包含scenario和store ID。相同key始终回放原始202受理响应，当前状态以GET JobRun为准。

初始化自动入队一次sync_events，之后按源每5秒持续同步。需要立即追平时，可在backend目录执行（与已有源任务合并）：

```powershell
uv run --frozen python -m app.cli show-state --store-id <store_id>
uv run --frozen python -m app.cli sync-events --run-id <scenario_run_id> --key <new_sync_key>
```

事件推送与拉取共用入账流程。AUTH_TOKENS服务授权增加 `"kind":"service","scenario_run_ids":["<run_id>"]`；不能凭body获得其他场景授权。幂等键按principal+operation+key唯一，换run/内容重用原键返回409。事件ID/序号/内容冲突、缺号、未知SKU、库存不足会回滚整批。来源预测版本仅保存为来源信息；本地forecast版本由backend生成。

PURCHASE_ACCEPTED仅接受已审批且登记发送的本地Action，和HTTP回执共享唯一采购账本效果。GOODS_RECEIVED按确认订单累计数量入账；缺少本地确认时先在事务外查询原回执。无本地授权Action仍返回ACTION_NOT_CONFIRMED；超量或矛盾事件整批回滚，另行保存冲突证据和ACTION_EXCEPTION。

## Mission与规划的使用

初始化并完成一次同步后，在Swagger创建Mission（替换实际store_id及catalog中的SKU/供应商）：

```json
{
  "store_id": "<store_id>",
  "sku_id": "sku_001",
  "objective": "活动备货，同时保持现金安全",
  "policy": {
    "cash_floor_minor": 30000,
    "candidate_quantities": [0, 20, 40, 80],
    "supplier_id": "<supplier_id>"
  },
  "check_interval_seconds": 30
}
```

写接口填写独立Idempotency-Key；重用同键同内容回放原响应，不同内容返回409。每个门店/SKU只能有一个ACTIVE或PAUSED Mission。首次创建、恢复和手动检查会入队；读取Mission的current_plan_id后查询Plan。控制请求包含operation及最新expected_mission_version，过期版本返回409。

SC01初始推荐40件（支出40000分、采购后可用现金60000分），80件违反30000分现金底线。这里只生成建议，现金和库存不变。objective用于展示，结构化policy决定规则。q=0或没有可行候选时proposed_purchase为null。

检查采用短REPEATABLE READ快照，计算后锁定store/Mission核验版本；过时结果为SKIPPED并登记一次复查。来源过期、报价无效或在途证据不完整为INCONCLUSIVE，不发布新方案。未知ETA不算有效到货。Plan快照及hash不可变，状态单独保存；相同有效输入复用方案，过期后生成新版本。销售扣减需求同时写入新的本地预测版本和截止时间。固定预测过期只能在来源追平后按当前剩余需求重新验证，不能恢复初始60件。

PLAN_TTL_SECONDS默认900，方案有效期同时受预测与报价限制；FIXED_FORECAST_TTL_SECONDS默认3600。决策快照时间统一UTC秒级，原始事件回执保留源精度。新Mission默认启用Schedule，从创建时刻加指定周期得到next_run_at。周期固定锚点，停机跨周期只补一次最新检查；事件全部按连续游标补齐。PATCH schedule需interval_seconds（5～3600）、enabled、expected_schedule_version和Idempotency-Key。暂停保留enabled偏好并清空next_run_at，恢复重新计时，结束关闭；配置不修改运行中的任务。迁移保留旧Mission原有禁用配置，旧Mission可通过PATCH启用。

实际三进程联调可在backend运行 `uv run --frozen python -m app.smoke_planning`，会创建独立开发场景及Mission。重启API/worker后运行同命令加 `--verify-restart` 核验原方案持久化；应在方案有效期内执行。

## 警报、看板与历史

SC01初始检查产生一条STOCKOUT_RISK（缺口40件），80件候选被淘汰不会额外触发资金警报。可用现金已低于底线，或按有效MOQ/包装补缺所需资金超出余量，才产生CASH_CONSTRAINT。同一风险连续检查更新原episode；知晓不解除风险、也不改变State。风险升级重新OPEN，保留知晓审计；新鲜检查确认风险消失才RESOLVED，再次出现创建新episode。

来源过期或输入无法判断时记录DATA_STALE并保留原有缺货/资金风险。警报解除保留最后风险事实及其版本，恢复证据在resolved_at与timeline中。ACTION_EXCEPTION已接入UNKNOWN、明确拒绝和冲突证据；正常确认解除对应动作警报，冲突manual_review停止自动改账。

知晓接口需要Idempotency-Key，不接受客户端指定操作者；同键回放原响应，不同警报重用原键返回409。RESOLVED警报的新知晓命令返回409 ALERT_RESOLVED。timeline的Reference.type增加alert，明确关联每次风险episode；已知晓者和时间保存在审计记录中。

看板使用只读REPEATABLE READ：State与各统计来自同一数据库快照。active_alert_count包括OPEN和ACKNOWLEDGED；next_check_at没有真实排队任务或已启用Schedule时为null。GET不会创建检查或警报。来源新鲜度会随时间过期，但持久警报须等检查更新；持续worker会自动同步和检查；来源不可读时持久记录错误，check_freshness补充DATA_STALE但不清除其他业务风险。

运行 `uv run --frozen python -m app.smoke_alerts` 创建独立开发场景并验证风险、知晓、看板和历史；重启API/worker后加 `--verify-restart` 核验原警报与审计保留。

## 测试与契约

普通 `uv run --frozen pytest` 执行API测试，缺少TEST_DATABASE_URL时明确跳过数据库集成测试。完整验证需专用shopsteward_test；测试会清理该库的队列、心跳或命令记录，并创建隔离场景；不得指向开发数据库。跨服务测试还需要TEST_SIM_DATABASE_URL。

首次从根目录创建测试库（本机已创建，无需重复）：

```powershell
docker compose --env-file infra/.env -f infra/compose.yaml exec -T postgres createdb -U shopsteward shopsteward_test
Set-Location backend
$dbEntry = Get-Content -LiteralPath '.env' | Where-Object { $_.StartsWith('DATABASE_URL=') }
$env:TEST_DATABASE_URL = ($dbEntry.Substring(13) -replace '/shopsteward$', '/shopsteward_test')
$env:DATABASE_URL = $env:TEST_DATABASE_URL
uv run --frozen alembic upgrade head
Remove-Item Env:DATABASE_URL
$simEntry = Get-Content '../simulation/.env' | Where-Object { $_.StartsWith('SIM_DATABASE_URL=') }
$env:TEST_SIM_DATABASE_URL = ($simEntry.Substring(17) -replace '/shopsteward_sim$', '/shopsteward_sim_test')
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen alembic check
uv run --frozen python -m app.export_openapi
uv run --frozen python ../docs/api/validate_contracts.py
```

完整验证：backend 138项测试（19 API、16单元、103 PostgreSQL/跨服务集成），simulator 12项，无跳过。开发/测试库迁移backend为0006_periodic、simulator为sim_0002_purchases。新增并发精确审批、拒绝/q0、版本/时间门控、丢响应/404重发原请求、取消后核对、租约丢失、原始冲突证据、部分到货/超量回滚、先到货后本地确认、101个待决动作恢复公平性测试；原B0-01至04回归保留。Ruff、格式、Alembic漂移和设计契约检查通过。

实际API/simulator/worker的自动SC01及重启历史记录见 [B0-06 smoke](../docs/api/b0-06-periodic-smoke-result.json)；B0-01至05历史记录保留。最新[B0-07报告](../docs/reports/b0-07-test-report.md)补充双worker中断、来源故障与精确重启回放。[运行时OpenAPI](../docs/api/backend.runtime.openapi.json)包含22个实际backend操作（21条路径）；[实现清单](../docs/api/implementation-status.json)区分已实现能力与后续目标。

## B0-05执行与复现

批准请求只传decision、expected_plan_version、expected_state_version、proposal_hash；actor从Bearer身份取得。批准仅登记Action与门店门控，发送前再次验证来源新鲜度、状态、期限及现金底线，再预留金额。执行版本单独记录，避免自己的预留让原方案失效。实际HTTP在数据库事务外发送。

UNKNOWN/PENDING保留资金预留与门店门控，按5/10/30/60秒登记原Action核对；只有原ID查询404且simulator保证幂等时才重放原请求、原键。worker会修复到期且缺少活跃任务的孤立Action。明确拒绝释放预留；合法迟到回执不会因Mission取消或方案过期而丢弃。取消未发送Action立即停止；已发送Action继续核对，存在未决Action时不能complete。

矛盾回执、409协议冲突和非法响应保留action_evidence并进入manual_review，停止自动改账；当前没有人工强制改账接口。调查依据为Action、证据、事件和账本。此路径保留未决预留与门控。

三个进程启动后，backend目录运行：

```powershell
uv run --frozen python -m app.smoke_execution
# 重启API、worker、simulator后验证原Action/原回执及采购重放：
uv run --frozen python -m app.smoke_execution --verify-restart
```

显式SC01：采购40 → 到货40 → 销售10 → 剩余需求70 → 采购20 → 到货20；最终现金40000分、应收20000分、现货70、在途0、预留0。采购账本2条、到货2条。故障测试使用真实PostgreSQL和受控传输；该smoke验证真实HTTP及进程重启，未提供运行时故障注入端点。B0-06已启用持续自动检查/同步；本节保留显式手动smoke入口，自动验收使用下节smoke_periodic。

## B0-06前的结构收口

纯JSON digest位于app/core/hashing.py；公共身份/参数与可见性位于api/dependencies.py，错误模板及B0Router位于api/routing.py。B0Router统一附加phase/implementation元数据；各业务router不相互导入。完整目录和模型归属以docs/backend-development.md第2章为准。

app/bootstrap.py统一调用各模块make_handlers(settings)并拒绝重复job_type。Handler.before_claim在领取事务前调用，共享回调每次run_once去重；失败时不领取。Handler.on_error在原业务事务回滚后的失败事务中写证据，最后由repo.fail核验租约；租约无效或钩子失败时证据回滚。两种钩子不执行外部HTTP；before_claim自行管理短事务，on_error不得自行提交。周期派发由独立异步扫描循环驱动，与执行槽位解耦；before_claim继续负责已有Action恢复。

新增7项回归覆盖全路由元数据、钩子去重/停止/失败、租约过期和换主时证据回滚。收口记录见[quality review](../docs/api/b0-05-quality-review-result.json)。现有SC01 smoke为B0-05历史证据，本轮未重新运行三进程smoke；重新启动API/worker后加载新代码。

## B0-06迁移与自动验收

迁移头为 `0006_periodic`。升级前停止旧版本worker；迁移新增source_schedules并为已有数据源配置5/60秒周期，同源重复未完成只读同步任务合并为一条并保留追平请求，不修改采购、事件或账本。开发库和专用测试库分别执行Alembic upgrade head。

正常运行需独立API、worker和simulator；`--once`只处理已排队的一条任务，不作为定时服务。源任务有数据库唯一活跃约束，空页追平不会误标缺页，失败JobRun结束后常规周期仍会继续。

已有服务运行时，在backend执行 `python -m app.smoke_periodic`，重启三进程后执行 `python -m app.smoke_periodic --verify-restart`。使用根虚拟环境Python。该命令创建开发场景和模拟采购，保存独立B0-06证据。

也可在仓库根运行 `.venv/Scripts/python.exe backend/tools/verify_periodic.py`：要求8000/8001空闲、配置及迁移已就绪；脚本仅启动、重启和停止自己创建的三个进程，完成后不留下服务。PostgreSQL继续运行。
