# B0-07 综合测试报告

日期：2026-09-07。结论：**B0-07范围验收通过**。发现并修复2处生产代码的锁竞争缺陷；新增8个真实PostgreSQL集成用例。全量backend 146项、simulator 12项通过，无失败、无跳过。自动SC01、双worker故障恢复及重启回放通过。

本报告对应分支`YH`、基础提交`516252df73f77ef5d3507968e2f943e2fdcde7db`上的未提交工作区。保留原B0-05质量收口与B0-06实现；本轮没有提交或推送，也没有新增接口、迁移、Agent、模型或线上故障注入入口。

## 1. 证据与环境

| 项目 | 本轮实际情况 |
|---|---|
| 环境 | Windows、PowerShell、Python 3.12.13、PostgreSQL 17.11；根目录`.venv`与现有`uv.lock`依赖 |
| backend测试 | 专用`shopsteward_test`；146通过，67.73秒：19 API、16单元、111 PostgreSQL/跨服务集成 |
| simulator测试 | 专用`shopsteward_sim_test`；12通过，3.20秒 |
| 数据隔离 | 两套测试串行运行；真实进程验收在开发库创建独立新SC01，不清开发数据 |
| 真实服务 | 独立API、两个worker、持久HTTP simulator；8010/8011服务端口，8012/8013为测试代理 |
| 进程归属 | 启动前检查端口与近期worker心跳，记录每个自建PID，仅中断/清理自建进程 |
| 迁移 | backend `0006_periodic`；simulator `sim_0002_purchases`；两侧Alembic check无漂移 |
| 格式/静态检查 | 两侧Ruff通过；backend 99个、simulator 13个Python文件格式通过；git diff --check通过 |
| 接口与契约 | runtime快照完全一致；22操作/21路径/8 handler与实现清单一致；53个设计示例、2个Plan hash及契约负例通过 |

可归档证据：[验证汇总](../api/b0-07-verification-result.json)、[真实进程原始结果](../api/b0-07-process-result.json)。本机详细JUnit输出在`var/b0-07-backend-tests.xml`、`var/b0-07-simulator-tests.xml`；进程日志目录由原始结果的`logs_directory`记录。`var`受Git忽略，不随仓库分发。B0-05/06历史结果没有覆盖。

## 2. 验收矩阵

“传输替身”指真实SQLAlchemy/PostgreSQL、真实业务代码与HTTP客户端，但在httpx传输边界控制响应；不能把这类测试写成实际杀进程。

| 覆盖面 | 证据与关键断言 | 结果 |
|---|---|---|
| RULE-01/02，PLAN-04/05/06 | 全量规则/规划/审批回归；q=40/20与现金底线、历史快照/hash、输入过期、q=0不创建采购 | 通过 |
| EVENT-01/02/03，FRESH-01 | 重复/缺口/冲突/分页/空页回归；游标不越过缺页，回执与事件只入账一次 | 通过 |
| APPROVAL-01/02/03 | 权限与版本回归；新增不同键竞争审批；真实HTTP两轮各8个同键并发请求，每轮相同响应/Action | 通过 |
| ACTION-01/02/03 | 丢响应、过期租约、孤立Action、现金门控回归；组合测试中双Runner竞争，UNKNOWN保留预留并核对原ID | 通过，传输替身+PG |
| PLAN-01/02/03，JOB-05/06/07 | 一致快照/旧租约回归；规划中事件突发并pause→resume，旧结果不发布，唯一后继覆盖最新版本 | 通过 |
| MISSION-01 | 暂停/取消时外部已受理且响应被挂起；到货先对账，晚到超时不得把SUCCEEDED改回UNKNOWN | 通过，参数化2项 |
| ALERT-01/02/03 | 100次重复风险不刷屏、知晓不恢复；来源重试耗尽后保留风险，后续周期追平才恢复；真实源中断显示STALE并恢复同一告警 | 通过 |
| JOB-01/03 | 既有5秒源同步与30秒Mission固定锚点测试；真实5秒Mission，双worker停机跨周期，合并遗漏周期并保持锚点 | 通过；非时延SLA |
| JOB-02 | 槽位饱和不阻断独立扫描/其他worker；新增101门店前100被锁仍派发空闲第101；忙门店恢复不阻塞无关任务 | 修复后通过 |
| JOB-04 | 过期token回写回归；真实中断持有RUNNING同步任务的worker，存活worker在租约过期后重试同一Job | 通过 |
| API-01/02/03 | schema/required/null/权限/跨店回归与runtime一致性；GET无业务写入；service身份不能冒充审批人 | 通过；Agent未接入 |
| SIM-01/02/03 | 持久世界、advance原子回滚回归；全部服务重启后原订单/回执一致；供应方六条事件和后台精确账本不变 | 通过 |
| EXT-02 | 无Agent/LLM在线依赖的自动完整SC01 | 通过；未模拟已集成Agent故障 |
| EXT-01 | 真实预测适配器替换及模型效果 | **未验收，归B1**；当前仍为FixedForecastProvider，不能据B0通过声称可替换模型已验证 |

新增用例文件：[组合场景](../../backend/tests/integration/test_b007_combinations.py)5项、[派发公平性](../../backend/tests/integration/test_dispatch_fairness.py)2项、[恢复公平性](../../backend/tests/integration/test_recovery_fairness.py)1项。使用事件屏障建立关键顺序；到期/租约逻辑使用数据库时间，避免仅靠任意sleep制造竞争。

## 3. 发现的问题及自动修复

### B007-01：前100个候选被锁后，后面的空闲门店长期没有机会

- 复现：101个到期门店，持有最早100个Store行锁，第101个保持空闲。原派发器先LIMIT 100取候选，再跳过忙门店，因此源计划、Mission计划两种测试均得到0个新任务，而应得到1个。
- 根因：候选截断发生在跳过锁竞争之前，每轮扫描反复遇到同一页。
- 修复：[dispatcher.py](../../backend/app/scheduling/dispatcher.py)发现候选时join Store并使用`FOR UPDATE OF Store SKIP LOCKED`，在批量限制之前跳过忙门店。发现阶段释放短锁后，逐项事务仍重查并遵守store→mission/schedule→job顺序。
- 验证：修复前2项失败；修复后与原periodic测试合跑11项通过。锁住门店的到期锚点不变，空闲第101个门店成功派发。最终146项全量回归通过。

### B007-02：孤立采购恢复等待忙门店，拖住整个任务领取

- 复现：保留一个QUEUED孤立Action并锁住其Store，同时登记无关worker_probe。`Runner.run_once`卡在领取前`recover_actions→lock_store`，1秒内不能完成无关探针。
- 根因：before_claim共享恢复钩子使用阻塞式门店锁；一个业务门店的竞争会阻塞其他任务进入领取阶段。
- 修复：[execution/jobs.py](../../backend/app/execution/jobs.py)恢复候选发现时跳过忙Store；逐项处理时再次尝试非阻塞门店锁，覆盖发现阶段释放锁后出现的新竞争。保留原Action状态/活跃任务过滤与统一锁顺序。
- 验证：修复前用例超时；修复后持锁期间无关探针可完成。与既有租约/101项孤立恢复回归合跑6项通过；最终全量通过。

### 验收工具修正

1. 新增组合用例最初以approver执行pause，API正确返回403。按现有契约改用operator；cancel继续用approver。这是测试账号配置问题，没有放宽生产权限。
2. 独立审查提出P2：仅比较供应商回执和后端账本，可能漏掉被后端去重的重复供应商事件。补充真实HTTP事件历史快照，要求恰好序号1～6、head=6、has_more=false，并在重启/采购回放后全文相同。补强后重新完成整轮进程验收；复审无剩余重要发现。
3. 时间指标改名为“最终一次尝试的启动滞后”，明确重试会覆盖started_at，包含停机和重试时间，不能称为纯派发延迟。强杀连接时测试代理出现一次预期ConnectionResetError；验收断言通过，进程清理完成，此输出不代表后台业务失败。

独立审查为静态审查，未自行运行测试或数据库；所有本轮运行结论来自主任务实际执行。

## 4. 双worker真实进程结果

执行脚本：[verify_resilience.py](../../backend/tools/verify_resilience.py)。最终补强轮总耗时**102.516秒**，其中场景开始到持续观测结束**90.110秒**。该时间包含人为故障及恢复，不表示服务无中断连续在线。

| 参数 | 验收配置 | 默认代码配置 |
|---|---:|---:|
| 每worker执行并发 | 4 | 4 |
| worker轮询 | 0.2秒 | 1秒 |
| 租约 / 心跳 | 6秒 / 2秒 | 30秒 / 10秒 |
| 来源过期阈值 | 8秒 | 30秒 |
| Mission周期 | 5秒 | 创建参数可配置，通常30秒 |
| 源同步 / 独立新鲜度周期 | 5秒 / 60秒 | 5秒 / 60秒 |

覆盖值只传给本次进程；未覆盖既有.env。模拟时间推进与上述真实时间分开，只有明确advance推进SC01业务。

| 场景 | 最终补强轮观测 |
|---|---|
| 并发审批 | 40件和20件两轮各8请求，同键同内容；每轮返回完全相同响应，只产生2个Action |
| 自动规划 | 手动checks请求数0；首次推荐40，销售/需求变化后推荐20 |
| 中断RUNNING worker | 测试代理确认目标源请求到达，DB确认唯一RUNNING任务；强杀所属worker1；原Job第1次→第2次尝试，存活worker在原租约过期后成功，耗时6.266秒 |
| 来源中断 | simulator实际停止9.125秒；看板STALE且有DATA_STALE；重启追平后FRESH，同一告警RESOLVED |
| 两worker停机 | 停止11.515秒；停机期间Schedule完全不变；恢复后到期锚点跃进10秒，遗漏区间仅登记1个合并任务 |
| 有界运行 | 90.110秒内完成16次周期Mission检查、13次周期源同步；原始结果含各任务时刻及采样 |
| 时间指标 | 最大最终尝试启动滞后10.474秒；包含注入故障/重试，不是纯派发时间或SLA |
| 全服务重启/回放 | API、两个worker、simulator全部重启；原Action/供应商回执相同，模拟器六条连续事件及head完全不变，后端精确账本行完全不变 |
| 清理 | 所有自建服务进程均停止，测试代理退出；开发场景与日志保留，PostgreSQL保留运行 |

最终SC01：现金**400元**、预留**0**、应收**200元**、现货**70件**、在途**0**。账本为INIT 1、PURCHASE_ACCEPTED 2、GOODS_RECEIVED 2、SALE_RECORDED 1、DEMAND_REVISED 1。应收不当作可用现金；到货不表示商品已销售完，Mission不自动完成。

## 5. 复现方式与边界

先按[HANDOVER](../../HANDOVER.md)准备专用测试库与迁移，在backend设置TEST_DATABASE_URL和TEST_SIM_DATABASE_URL后运行pytest；在simulation设置TEST_SIM_DATABASE_URL后运行pytest。不要并行清理/运行共享测试库。Ruff、Alembic与契约命令也在交接文档中。

真实进程验收从仓库根执行：

```powershell
.venv/Scripts/python.exe backend/tools/verify_resilience.py
```

要求开发库已迁移、忽略的.env已配置、8010～8013空闲且没有其他活跃worker。脚本会创建开发场景并实际采购/推进模拟世界，保留数据，退出时停止自身进程。最终结果覆盖本工作包的process-result；B0-05/06独立证据保持不变。

本轮不是长时间soak、高吞吐压测、跨主机网络分区、PostgreSQL宕机恢复或真实供应商验收。101门店测试证明特定锁竞争下空闲门店能进展，不能推出任意规模的公平性或时延上限。实际杀进程发生在来源读取阶段；外部采购成功但本地丢响应/丢租约的严格组合由真实PG和受控传输测试覆盖，不冒充真实采购进程崩溃实验。

B0主干可进入用户指定的下一阶段；真实模型适配/效果、Agent/LLM工具权限与降级、RAG，以及前端联调仍需各自工作包验收。本轮不把课程最终技术整合视为完成。
