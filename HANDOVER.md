# ShopSteward 当前开发交接

更新：2026-09-07（B0-07完成并验收）。配套入口：[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)。先读PROJECT_CONTEXT理解项目、架构和历史，再读本文掌握当前开发现场；两份文件足以确定范围、设计约束、进度和下一步，实施某个接口时再查具体源码或契约。

本轮已完成B0-07组合故障、并发和真实进程验收，自动修复两处锁竞争缺陷。backend 146项、simulator 12项通过，无跳过；最新[测试报告](docs/reports/b0-07-test-report.md)、[进程证据](docs/api/b0-07-process-result.json)与[验证汇总](docs/api/b0-07-verification-result.json)。验收脚本已停止自己创建的API/两个worker/simulator；PostgreSQL容器继续运行。历史B0-05/06证据保留。

## 1. 用户已经明确的工程原则

**唯一原则：结构正确，功能完整满足要求，且没有赘余的设计。**

- 审查意见是待验证的建议，不能因为CC或其他审查者提出就全部执行。
- 修复真实缺陷；重构必须解决实际维护问题或支撑明确需求，并衡量新增复杂度。不要为“五件套”、目录对称、消除全部包级双向依赖或展示抽象能力而重构。
- 当前为模块化单体。跨模块原子事务、共享模型归属及部分双向依赖可以保留；未要求独立部署的业务模块不必提前满足可单独抽离条件。
- 功能验收看业务结果和异常路径，测试数量、代码行数、目录层数都不是完成度指标。已有测试验证与本次变更相关的真实风险即可，不围绕实现细节堆测试。
- 不为未来Agent/ML接入提前建设插件系统、通用工作流引擎或复杂模拟平台。现有HTTP与业务契约足够支持渐进接入。
- 用户指定工作包后，完成该范围内实现、必要验证和交接更新；阅读交接材料本身不表示要开始所有后续阶段。已有授权范围内的常规可逆工作不必反复请示。

## 2. 当前开发现场

| 项目 | 本次核对结果 |
|---|---|
| 工作资料根目录 | `D:/HuaweiMoveData/Users/13736/Desktop/AIS/Group_Project` |
| 应用仓库 | 上述目录下的`ShopSteward`；命令需在正确目录执行 |
| 分支 / HEAD | `YH` / `516252df73f77ef5d3507968e2f943e2fdcde7db`，`feat: backend B0 foundation and simulation service` |
| 已提交基础 | B0-01至B0-05功能在上述提交中 |
| 未提交工作 | 保留B0-05质量收口及B0-06全部改动；新增B0-07组合测试、两处锁竞争修复、进程验收脚本、报告/交接 |
| 下一阶段 | B0-01至B0-07完成；按用户指定进入前端联调、B1预测或B2 Agent，不自动扩大范围 |
| 暂未接入 | 真实预测模型、Agent/LLM、RAG/记忆/技能；前端进度未在本任务核验 |

接手先执行`git status --short`、`git log -1 --oneline`、`git branch --show-current`。不要把未提交改动当垃圾清掉，也不要假定远程仓库包含它们。本次没有提交、推送或远程最新状态核验。

## 3. 项目和设计的必要摘要

ShopSteward是面向小商家的持续经营助手，首条业务线为活动备货与现金安全。当前先交付不依赖AI在线的backend主干B0：记录经营事实、比较采购候选、提出方案、用户审批、执行并根据新事实继续检查。未来Agent负责解释、推理和跟进，不能取代账本、确定性约束或审批。

采用FastAPI模块化单体、独立API进程、独立worker、PostgreSQL。simulator是独立HTTP进程，拥有自己的持久世界、数据库、账号及迁移；backend通过契约调用，不能直接读取simulator表。多个API/worker实例共享同一模拟世界。

当前实际代码按`api/core/db/scheduling/operations/missions/planning/alerts/execution/reporting`组织，没有`app/modules/`、`app/workflows/`、`app/integrations/`或`api/routes/`层。PlanRow、ScheduleRow、TimelineRow、InboundRow仍在`missions/models.py`；纯候选规则在`planning/engine.py`，哈希规范化在`planning/canonical.py`，风险规则在`alerts/rules.py`。跨模块用例暂由jobs/repository/accounting等函数承担，不为目录整齐搬模型。

### 必须保持的业务与事务约束

1. 金额用整数分，数量用整数件，当前币种CNY；现金、预留、应收、现货、在途分别记录。可用现金为现金减预留，应收不作为可用现金。
2. Plan保存不可变DecisionSnapshot、候选、proposed_purchase及`sha256:`摘要；规范化采用decision-v1、UTC秒级时间。q=0时proposed_purchase为空，不能创建采购Action。
3. 审批只接受decision、expected_plan_version、expected_state_version、proposal_hash，审批人从Bearer身份取得。审批和发送前分别核对当前状态、Mission/策略、来源新鲜度、输入期限、到货窗口和现金底线。
4. 审批事务登记Approval、唯一Action与持久JobRun；发送前才预留资金并记录EXECUTING/执行版本。每个门店最多一个未决采购占用执行门控；自己的预留不能让原方案误判失效。
5. 写事务按store→mission/plan→action→job锁顺序；领取/续租只锁任务。规划/看板使用短一致快照，旧计算结果可丢弃并安排重算。HTTP不能包在本地写事务里。
6. 派生业务写入与JobRun完成或失败必须同事务受实际租约/token保护。租约丢失不能撤回外部请求，也不能把采购判为失败；当前持有者核对原Action。
7. 网络超时/PENDING保留UNKNOWN、资金预留和门控。核对先查询原Action；只有实际404且供应方保证幂等时才使用原ID、原payload、原键重发，不能创建第二个采购。
8. HTTP受理回执和PURCHASE_ACCEPTED共享Action级唯一账本效果。GOODS_RECEIVED累计不超过已确认订单；缺少本地确认时先在事务外查询回执，再整批原子入账。来源事件要求连续游标，重复内容无重复效果，矛盾内容不得覆盖旧事实。
9. 冲突事件整批回滚后另存证据和ACTION_EXCEPTION；非法JSON、null、NaN、HTTP409不能被当成404或普通超时无限重试。manual_review停止自动改账，目前没有人工强制改账接口。
10. Action SUCCEEDED表示采购受理及资金/在途入账，不表示已到货。取消未发送采购可直接停止；已发送采购即使Mission取消或Plan过期仍继续核对；有未决Action时不能complete。
11. 警报知晓不表示解除；恢复要有新鲜且可判断的证据。UNKNOWN数据保留原业务风险并标记DATA_STALE。GET不创建检查、不采购、不推进模拟时间。
12. 租约、心跳、超时、重试使用真实时间；经营事件使用simulation_time。只有拉取事件并追平源头才能证明同步新鲜，空页也可证明追平，单次推送不证明已经追平。

### worker当前扩展方式

`app/bootstrap.py`统一调用四个`make_handlers(settings)`工厂，发现重复job_type即报错。当前8种handler：worker_probe、initialize_scenario、sync_events、check_mission、execute_purchase、reconcile_action、advance_scenario、check_freshness。agent_followup仍未注册。

Handler的职责：

| 阶段 | 事务和用途 |
|---|---|
| before_claim(db) | 领取事务前调用，自管短事务；共享回调每次run_once只执行一次。异常则不领取，停止信号阻止继续执行。当前用于恢复到期且无活跃任务的孤立Action |
| run(db, job) | 在发布事务外读取/计算/调用HTTP；需要发送登记时先完成短事务再发送 |
| apply(session, job, prepared) | 发布派生结果，与JobRun完成在同一租约事务内 |
| after_complete(session, job, result) | 同一完成事务内登记后续任务或历史 |
| on_error(session, job, error) | 原业务事务回滚后的失败事务；当前只对retry_safe且未报告丢租约的任务调用。先写业务证据，最后repo.fail验证租约；验证失败或钩子异常时全部回滚。钩子不得HTTP或自行提交 |

业务异常解释在对应handler内，Runner不识别某个采购任务名或EventActionConflict。on_error自身失败会保留RUNNING供租约恢复。before_claim保留Action恢复用途。B0-06的周期派发由Runner.serve的独立扫描循环调用dispatch_due，不占执行槽位；run_once不运行周期扫描。

## 4. 已完成和验证到什么程度

| 阶段 | 已实现内容 | 当前边界 |
|---|---|---|
| B0-01 | API/身份/统一错误、DB迁移、独立worker、持久队列/心跳/租约 | 技术探针不代表业务完成 |
| B0-02 | catalog/初始化、State、事件/账本、连续游标、独立simulator | 正向采购/到货已在B0-05补齐 |
| B0-03 | Mission管理、固定预测、候选比较、不可变Plan、手动检查及重算 | 真实模型未接入 |
| B0-04 | 四类警报的基础、知晓/恢复/历史、一致看板；动作异常由B0-05接入 | B0-06补齐周期新鲜度派发，GET仍不写警报 |
| B0-05 | 精确审批、预留/发送、原Action核对、唯一采购/到货入账、显式advance及SC01 | 周期自动运行由B0-06补齐，故障注入仍仅为受控测试 |
| B0-05后收口 | core哈希、API公共定义/B0Router、通用钩子与工厂、文档对齐 | 当时未迁移数据库；原有未提交内容保留 |
| B0-06 | 固定锚点周期派发、Schedule接口/生命周期、源同步/新鲜度、事件合并及租约恢复 | backend迁移0006_periodic |
| B0-07 | 组合竞争/故障测试、101门店锁竞争、双worker中断/停机/源恢复、自动SC01与精确重启回放 | 有界本机运行，非长期负载或生产SLA；无新接口/迁移 |

本轮验证：backend **146通过**（19 API、16单元、111真实PostgreSQL/跨服务集成），simulator **12通过**，无跳过；Ruff通过，backend app/tests/migrations/tools共99个Python文件格式通过；backend及simulator Alembic无漂移；53个设计示例、2个Plan hash通过。见[verification-result](docs/api/b0-07-verification-result.json)。

本轮另运行独立API、两个worker与simulator，完成两轮各8个同键并发审批、自动SC01、RUNNING源任务所属worker强杀、来源中断与告警恢复、双worker停机跨周期及不少于90秒的有界观测。重启全部服务后Action、供应商回执、六条完整来源事件及精确账本均不变。细节与参数见[报告](docs/reports/b0-07-test-report.md)。这不等于长期负载验证；B0-06的11.6秒自动检查结果仍保存在原[periodic-smoke-result](docs/api/b0-06-periodic-smoke-result.json)。

历史B0-05的122/12测试记录及显式SC01/restart证据保持原文件，不冒充本轮结果；旧结构收口没有重跑smoke的限制仅适用于那一轮。

SC01固定验收：成本10元/件、售价20元/件、现金底线300元、候选0/20/40/80。初始现金1000元/现货20/需求60；采购40受理→到货40→销售10→需求从50上调到70→采购20受理→到货20。最终现金400元、应收200元、现货70、在途0、预留0；采购账本2条、到货2条。80件候选会使现金降至200元，必须淘汰。活动尚未销售/结算完成，不自动结束Mission。

### 当前接口边界

实际backend有22个操作、21条路径，全部有B0实现元数据；完整设计稿有26个操作，不能当作已实现清单。

| 入口组 | 当前接口 |
|---|---|
| 健康/运维 | GET `/health/live`、`/health/ready`、`/api/v1/monitoring/status`、`/api/v1/job-runs/{job_run_id}` |
| 经营/展示 | GET `/api/v1/catalog`、`/api/v1/dashboard`、`/api/v1/alerts`；POST `/api/v1/alerts/{alert_id}/acknowledgement` |
| Mission | POST/GET `/api/v1/missions`；GET `/api/v1/missions/{mission_id}`；POST其`/control`、`/checks`；PATCH其`/schedule`；GET其`/plans`、`/timeline` |
| 方案/执行 | GET `/api/v1/plans/{plan_id}`；POST其`/decision`（approve=202、reject=200）；GET `/api/v1/actions/{action_id}` |
| 内部/演示 | POST `/internal/v1/events/batches`、`/dev/v1/scenarios`、`/dev/v1/scenarios/{run_id}/advance` |

用户Bearer有viewer/operator/approver/admin角色及store授权；operator可创建/检查/暂停恢复/知晓警报，approver可审批/完成取消，admin可访问开发入口。内部事件要求独立service身份及scenario_run_ids授权；service不能冒充用户审批。命令幂等键包含principal、operation和请求路径资源/内容，不因重放绕过当前资源授权。

simulator有create run、list events、purchase、query purchase、advance五个业务接口和ready；服务token仅backend使用。advance四阶段为到货、销售10、需求70、再次到货，多步中途阻塞整批回滚；所有GET不推进世界。

## 5. 后台调度与B0-07验收结果

1. **持久周期派发。** Mission Schedule继续保存在missions/models.py；源计划source_schedules按scenario_run_id/job_type保存5秒sync_events和60秒check_freshness周期。dispatcher发现候选时以FOR UPDATE OF store SKIP LOCKED在LIMIT之前跳过忙门店；释放发现阶段短锁后，再逐项短事务锁store→mission/schedule→job，重查到期，入队/合并和推进next_run_at同事务。停机跨周期合并为最新发生点并跳到下个未来锚点。每类每轮最多100条。
2. **配置与生命周期。** PATCH `/api/v1/missions/{mission_id}/schedule`返回Schedule，要求operator/门店授权、幂等键、interval_seconds（5～3600）、enabled、expected_schedule_version。新Mission默认启用，旧禁用Mission迁移时保持禁用。暂停清空到期时间并保留enabled偏好，恢复重新计时，完成/取消关闭。配置及生命周期变更提升schedule.version；周期派发不提升版本、不修改运行中的任务。
3. **持续来源与新鲜度。** 同源/类型只有一个活跃Job；周期触发、初始化、advance、Action完成、CLI都走合并。分页及运行中的新显式请求用持久rerun_requested在完成事务中登记后继；事件全部补齐。空页追平刷新last_success_at，失败保存last_error。check_freshness可为ACTIVE/PAUSED Mission留DATA_STALE，不清除原业务风险；源恢复后唤醒ACTIVE Mission重新核验报价/预测等输入。
4. **事件与恢复。** 事件入账后在同一事务中合并受门店状态版本影响的ACTIVE Mission检查及目标版本；重复事件不重复唤醒。RUNNING检查仍以recheck_required在完成事务创建后继；旧租约不能提交派生结果。扫描循环独立于执行槽位，慢HTTP不会阻止到期登记。源事实和已发采购核对不随Mission暂停/取消停止。
5. **验收。** 新测试覆盖周期锚点/停机合并、多派发并发、事务回滚、事件唤醒、分页/运行中请求合并、手动同步重放、源错误/新鲜度、饱和槽位与其他worker推进、旧租约回滚、Schedule权限/版本/生命周期。自动三进程SC01和重启已验证。

**B0-07已完成：** 新增8个集成用例，覆盖不同键竞争审批+丢响应核对、来源重试耗尽后周期恢复、规划中事件突发与暂停恢复、暂停/取消中先到货后超时，以及101门店候选公平性和忙门店Action恢复。复现并修复两处生产缺陷：LIMIT之前未跳过锁导致候选饥饿；孤立Action恢复等待门店锁导致整个领取前钩子卡住。真实进程验收与独立审查通过，具体断言、修复及边界见报告。B1预测、B2 Agent/LLM、RAG、多SKU/多供应商优化仍未开始；下一工作包按用户指定，不承诺负载下5/30/60秒时延上限。

实现计划与决定见[2026-09-07-b0-06.md](docs/superpowers/plans/2026-09-07-b0-06.md)。无需重新实现Schedule、source同步或现有Action恢复。

B0-07计划见[2026-09-07-b0-07.md](docs/superpowers/plans/2026-09-07-b0-07.md)。在仓库根运行 `.venv/Scripts/python.exe backend/tools/verify_resilience.py` 可复现验收。要求8010～8013空闲且无其他活跃worker；创建新开发场景并保留数据与var目录日志；使用租约6秒/心跳2秒/来源过期8秒覆盖值，最后只停止自身进程。

## 6. 已知边界与CC复核结论

- 接受并完成：纯digest放core；路由公共定义集中；4个缺失操作元数据补齐；错误模板统一含409；runner业务特判改为有具体用途的两个钩子；make_handlers统一注册。
- CC“每个模块完整五件套”不准确；“删Store局部导入即可”需先在顶部补Store；“约40行零行为变化”不适用于租约失败路径。移动Python模型定义通常不需要数据库迁移，当前不搬是收益不足，而不是必然需要迁表。
- 模块级立即执行的导入图无循环，不代表所有业务包可独立部署；函数内延迟导入及跨包依赖仍有实际用途。scheduling/repository.py的monitoring_status仍读取SourceCursor，只有Runner已移除业务特判。
- 记录即可，非后续阶段前置：Plan/Schedule/Inbound模型归属、operations.apply_event放在repository、跨用例事务复杂度、smoke在运行时包且依赖开发库/本地路径、int64上限常量重复、local版本UUID与digest两种生成方式、simulator剧本和持久化耦合。出现实际扩展/打包需求再决定处理。
- manual_review仅留证并停止自动改账，暂无人工覆盖接口；simulator没有在线故障注入入口。看板读取时的新鲜度会随时间变化，持久警报由Mission检查或周期check_freshness更新。

## 7. 本机运行与必要验证

已配置环境的历史记录：Windows/PowerShell，Python3.12.13，PostgreSQL17.11，依赖锁在根目录uv.lock；虚拟环境在根`.venv`。API默认8000、simulator8001，PostgreSQL绑定本机55432。backend库shopsteward / 测试库shopsteward_test；simulator独立库shopsteward_sim / 测试库shopsteward_sim_test及独立账号。

迁移头：backend `0006_periodic`，simulator `sim_0002_purchases`。凭证在Git忽略的`backend/.env`、`simulation/.env`、`infra/.env`；backend的SIMULATION_TOKEN与simulator的SIM_SERVICE_TOKEN对应。不要打印/写入文档/覆盖已有配置。新机器按两个模块README准备数据库和配置，不能假定根目录资料、虚拟环境或.env随Git带来。

当前默认值（本地.env可以覆盖）：worker并发4、poll1秒、租约30秒、续租10秒、任务超时120秒、停机等待10秒、来源新鲜30秒、Plan TTL900秒、固定预测TTL3600秒。普通安全任务最多3次尝试，临时失败2/4秒重试；Action核对5/10/30/60秒，是另一层机制。

### 启动（已有配置时）

从仓库根启动数据库：

```powershell
docker compose --env-file infra/.env -f infra/compose.yaml up -d --wait
```

三个独立终端，分别进入对应目录：

```powershell
# simulation目录
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m simulator
```

```powershell
# backend目录：API
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app
```

```powershell
# backend目录：worker
..\.venv\Scripts\python.exe -m app.worker
```

API不自动启动worker、不自动迁移。开发Swagger为http://127.0.0.1:8000/docs；production默认关闭docs与dev路由。接手时先确认端口和进程归属，不盲目启动第二份或终止不明进程；升级0006_periodic前停止旧worker；迁移会合并重复未完成只读源任务，保留一个任务及后继追平请求，不修改采购账本。验收后已停止本轮自建三进程，普通开发需按上述命令启动。

### 验证命令（按变更需要执行）

backend目录；集成测试只允许专用测试库，未设置时会skip：

```powershell
$entry = Get-Content '.env' | Where-Object { $_.StartsWith('DATABASE_URL=') }
$env:TEST_DATABASE_URL = ($entry.Substring(13) -replace '/shopsteward$', '/shopsteward_test')
$simEntry = Get-Content '../simulation/.env' | Where-Object { $_.StartsWith('SIM_DATABASE_URL=') }
$env:TEST_SIM_DATABASE_URL = ($simEntry.Substring(17) -replace '/shopsteward_sim$', '/shopsteward_sim_test')
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check app tests migrations tools
..\.venv\Scripts\python.exe -m ruff format --check app tests migrations tools
..\.venv\Scripts\python.exe -m alembic check
..\.venv\Scripts\python.exe -m app.export_openapi
..\.venv\Scripts\python.exe ../docs/api/validate_contracts.py
```

simulation目录设置TEST_SIM_DATABASE_URL后执行`..\.venv\Scripts\python.exe -m pytest -q`。新测试库需先按模块README迁移；上面的alembic check读取当前DATABASE_URL，不代表自动检查或迁移测试库。

两套测试共用本机实例，backend集成测试还访问simulator测试库；不要让多个代理同时清理/运行同一套测试库。部分测试夹具会清任务/命令，并把测试Action终止以隔离恢复扫描；这些操作不能用于开发库。

真实HTTP联调可在三个服务运行后于backend执行 `..\.venv\Scripts\python.exe -m app.smoke_periodic`；重启三服务后加 `--verify-restart`。也可在仓库根运行 `.venv/Scripts/python.exe backend/tools/verify_periodic.py` 自动管理自己的三进程，两轮验收后全部停止（要求8000/8001空闲）。脚本会创建开发场景及模拟采购，不是只读诊断；结果保存在独立B0-06文件，不覆盖B0-05历史证据。持续worker已有自动源同步，CLI sync-events仍可立即请求同步并合并已有任务。

## 8. 新对话接手顺序与交接维护

1. 读PROJECT_CONTEXT与本文，先确定用户本轮任务；不要把历史建议自动提升为当前待办。
2. 核对Git、已有未提交文件、相关源码和运行环境；保留B0-05质量收口及B0-06/07所有未提交改动，暂不清理记录级问题。
3. B0-07已经完成，阅读报告后执行用户新指定的工作；不要再次把组合验收列为未开始。
4. 修改完成后更新PROJECT_CONTEXT的状态/设计变更和本文的现场/待办/验证日期；保存可区分测试、真实HTTP和重启验收的证据，不覆盖历史结论的适用范围。

主要入口：[backend开发设计](docs/backend-development.md)、[simulator契约](docs/simulation-contract.md)、[接口设计/用法](docs/api/README.md)、[实际实现清单](docs/api/implementation-status.json)、[backend启动说明](backend/README.md)、[simulator启动说明](simulation/README.md)。这些用于深入实施，不是先理解交接必须逐份读取的材料。
