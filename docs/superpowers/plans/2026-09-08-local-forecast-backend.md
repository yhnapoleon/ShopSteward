# B1-B backend与模拟回放 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将ML结果发布为后端可信预测，驱动既有规划与审批，并以隔离REPLAY验证日级反馈。

**Architecture:** 新增forecasting业务模块，复用ForecastRow、Stock投影、JobRun、租约、状态版本和业务唤醒。预测worker独立领取refresh_forecast；模拟器的历史观测和隐藏需求分开，backend只接收完整历史与已发生事实。

**Tech Stack:** 现有FastAPI/Pydantic、PostgreSQL/SQLAlchemy/Alembic、httpx、Runner；模拟器独立PG；A交付的本地ML服务。

**Spec:** [设计第6～9及12节](../specs/2026-09-08-local-forecast-design.md)。前置[A计划](2026-09-08-local-forecast-model.md)。

## Global Constraints

- 模型不直接决定采购量，不计算或更改现金账本，不审批，不使用 RAG 文本直接改预测。
- 全部门槛完成前状态为b1_ready=false。
- HTTP在数据库写事务外；Forecast发布、业务版本、唤醒和Job完成在同一实际租约事务内。
- 只使用显式专用TEST_DATABASE_URL/TEST_SIM_DATABASE_URL；不得清开发库或知识验收租户。
- SC01固定预测/账本、decision-v1历史hash、现有采购审批/UNKNOWN核对语义保持兼容。
- 此处文件/接口/迁移是待实施项；创建迁移前读取实际head，不修改旧迁移。

---

## 文件与接口地图

新建`backend/app/forecasting/`：`models.py`存绑定/观察/不可变详情；`schemas.py`存公开与ML适配DTO；`repository.py`存投影读取/绑定/入队/发布；`history.py`存日观测与种子；`client.py`存ML HTTP；`jobs.py`存Handler工厂；`router.py`存公开API；`policy.py`存纯可用性/响应校验/模式规则。

修改现有`operations/repository.py,schemas.py,jobs.py,client.py`接种子与闭日；`planning/snapshot.py`接发布预测；`execution/repository.py`补当前可用性；`scheduling/{models,dispatcher,repository}.py`及`api/schemas.py`补job类型和扫描；`worker.py`补forecast profile；`main.py`注册公开路由；`core/config.py`补配置；实际迁移`forecast_b1_0012.py`（若head变化，保留描述并重定revision）。

模拟器新建`simulation/simulator/replay.py`和`replay_schemas.py`，修改`{models,schemas,repository,controls,main,console}.py`；新建`simulation/tools/import_forecast_replay.py`、`backend/tools/verify_forecast_replay.py`。不新增通用workflow、特征数据库或模型注册平台。

### Task B1: 预测持久模型、DTO与权限边界

**Files:** Create `forecasting/{__init__,models,schemas,policy,repository,history}.py`、`backend/tests/unit/test_forecast_policy.py`、`backend/tests/integration/test_forecast_storage.py`、`backend/migrations/versions/forecast_b1_0012.py`；Modify `backend/migrations/env.py`现有模型导入、`backend/app/db/session.py`的SCHEMA_REVISION与ready表检查。

**Interfaces:** `ForecastBinding`、`ForecastObservation`、`ForecastDetail`映射设计§7；`ForecastCurrent`为公开状态DTO；`publication_matches(captured:dict,current:dict)->bool`比较state_version,source_sequence,history_revision,binding_version,model_version；`record_observation(session,store,sku,row)->bool`返回是否新增；`read_current(session,store_id,sku_id,now)->ForecastCurrent`只读。

- [ ] 用纯测试固定旧结果拒绝逻辑：

```python
from app.forecasting.policy import publication_matches

def test_changed_history_rejects_inflight_forecast():
    captured = dict(state_version=7,source_sequence=12,history_revision=3,
                    binding_version=1,model_version="m1")
    assert publication_matches(captured, captured)
    assert not publication_matches(captured, captured | {"history_revision":4})
    assert not publication_matches(captured, captured | {"state_version":8})
```

- [ ] 在backend目录执行`../.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_policy.py -q`确认失败；建立迁移、表、PK/FK/unique/check和新详情不可变约束。ForecastRow仅对B1新增且有详情的版本保护，不回写历史fixed记录。
- [ ] PG测试用事务插入同(store,sku,date)观测：同hash重放返回False、不同内容409；日曲线行数必须等于目标本地日数，总量与取整一致。shadow同样写ForecastRow/detail，但不更新Stock指针。
- [ ] 绑定按store/sku唯一，跨店forecast_id读取404；缺数据DTO为UNAVAILABLE且curve=null。对全部旧Plan JSON做反序列化再hash回归，禁止因新增默认字段改变digest。
- [ ] 在专用库upgrade/check、downgrade仅对本任务新表的空测试库验证；有数据回滚采用停用功能而非删历史。修改session.py的head与新表readiness检查，防止迁移成功后服务仍按旧head报未就绪。提交`feat(backend): persist versioned forecast bindings and evidence`。

### Task B2: HTTP调用、独立worker与可靠发布

**Files:** Create `forecasting/{client,jobs}.py`、`backend/tests/unit/test_forecast_client.py`、`backend/tests/integration/test_forecast_jobs.py`；Modify `forecasting/repository.py`、`worker.py`、`core/config.py`、`api/schemas.py`、`scheduling/models.py`、`scheduling/repository.py`、预测迁移。

**Interfaces:** `ForecastClient.predict(request:ForecastRequest)->ForecastResponse`；`prepare_refresh(db,job,settings)->PreparedForecast`保存captured/history/request；`publish_refresh(session,job,prepared,response)->JobResult`；`queue_refresh(session,store,binding,*,key,reason)->Job`；`make_handlers(settings)->dict[str,Handler]`只注册refresh_forecast。

- [ ] 先写client fixture响应（可由A契约示例构造）并覆盖返回错store/series/horizon/hash、NaN、响应缺日、负数量和错误模型；测试必须断言拒绝错误而非静默clip。纯日期helper`assert_day_range(dates,start,end,timezone)`在DST日依然接受正确7个自然日。
- [ ] 运行`../.venv/Scripts/python.exe -m pytest tests/unit/test_forecast_client.py -q`确认失败；用httpx实现connect1s/total5s、错误映射和schema显式转换。ML附加字段不直接送进原extra=forbid Forecast。
- [ ] forecast profile工厂只注册预测job，业务profile不注册；新增JobType、活跃(store,sku)部分唯一索引，并让租约回收识别该类型；target_state_version/target_mission_version迁为BigInteger以匹配业务版本。后台线程不自行commit或更改业务表。
- [ ] 以两个真实PG会话测试inflight时发生销售/配置/到货/租约替换：旧response不发布；apply写到一半发生lease丢失时ForecastRow、Stock、state、timeline全部回滚；最终唯一发布、同任务重领不增加第二版本。
- [ ] 明确Handler返回值区分PUBLISHED/REUSED/SKIPPED及对应references，不把Job SUCCEEDED等同预测已替换。失败但旧版本仍有效时保留它，HTTP422为终态而非自动多轮重试。
- [ ] 双worker只领同一预测一次，预测进程阻塞时业务worker仍完成无关只读任务及采购核对。按task diff提交`feat(backend): publish forecasts through a fenced worker`。

### Task B3: 闭日观测、规划读取与调度更新

**Files:** Modify `forecasting/{history,repository,policy,jobs}.py`、`operations/{repository,schemas}.py`、`planning/snapshot.py`、`execution/repository.py`、`scheduling/dispatcher.py`；Create `backend/tests/integration/test_forecast_lifecycle.py`、`backend/tests/unit/test_forecast_dates.py`。

**Interfaces:** `close_sales_day(session,store,stock,event)->None`校验当日销售和并写完整观测；`read_published_forecast(session,store,stock,cursor,now)->ForecastSnapshot`返回现有最小DTO；`queue_due_forecasts(db)->int`以现有扫描调用；`assert_forecast_usable(session,store,stock,plan,now)->None`用于审批和发送。

- [ ] 写纯日期与尾期测试：

```python
from datetime import date
from app.forecasting.policy import remaining_dates

def test_episode_tail_has_no_repeated_sales_subtraction():
    assert remaining_dates(date(2016,4,26),date(2016,5,2)) == [
        date(2016,4,d) for d in range(27,31)] + [date(2016,5,1)]
    assert remaining_dates(date(2016,5,1),date(2016,5,2)) == []
```

- [ ] 运行聚焦测试确认失败。实现remaining_dates：输入最近闭日与exclusive episode_end，输出次日起的日期；不足7日只请求剩余日，0日不推理。日期按绑定timezone转UTC，不硬加秒数跨DST。
- [ ] fixed模式维持原销售扣减；model销售仍入账但使当前结果不可用，不改旧日曲线。模型范围内DEMAND_REVISED只记来源冲突证据/游标，不覆盖模型权威；闭日事件不是销售账本，不重复增应收。
- [ ] 新事件1.1 `DAILY_SALES_CLOSED`只在新REPLAY环境出现；sold_quantity=0合法，数量与已同步销售合计必须相等；相同事件幂等、矛盾回滚。若当日销售后未闭日，不用未知日填0。
- [ ] 规划只读已发布ForecastSnapshot，模型不做本地fixed TTL续期。审批/发送复核history_revision、binding版本/active、forecast版本/TTL；即使数据变化没产生新模型结果也必须阻止旧Plan新采购。已发送Action核对照常。
- [ ] 扫描加入TTL/失败恢复，RUNNING合并最新requested_revision并在after_complete生成后继；idle/failed后仍能重新入队。100个忙store不饿死第101个；现有business/agent/forecast扫描同时运行不产生重复活跃job。
- [ ] 专用PG测试覆盖销售→闭日→重新预测总量绝不二次减昨日销量、零销售次日、过期无服务、暂停/恢复、终止Mission、源失联恢复。原SC01所有终态仍400元现金/200元应收/70件现货。提交`feat(backend): integrate daily forecasts with business lifecycle`。

### Task B4: 公开查询/刷新/配置与契约生成

**Files:** Create `forecasting/router.py`、`backend/tools/export_forecast_contract.py`、`backend/tests/api/test_forecast_api.py`；Modify `main.py`、`forecasting/{schemas,repository}.py`、`scheduling/repository.py`（monitoring读取实际配置）、`backend/.env.example`；Produce `docs/api/forecast-v1.openapi.json`、更新backend.runtime和implementation-status。

**Interfaces:** 五个公开操作按设计§7.1；RefreshRequest `{reason,expected_binding_version}`；RefreshAccepted `{job_run_id,status,reused}`；ConfigChange为discriminated union：http分支`{expected_binding_version,provider,mode,model_version,series_id,feature_profile,timezone,episode_end}`，fixed分支`{expected_binding_version,provider,fixed_forecast_version}`；所有多余字段拒绝。首次绑定CAS为0，后续为当前版本；配置中的模型只能来自服务制品metadata白名单。

- [ ] API测试断言GET不调用ForecastClient且不增加Job数；viewer刷新403；越店forecast详情404；POST传predicted_quantity422；重复同键返回同job、同键不同CAS/内容409。
- [ ] 运行`../.venv/Scripts/python.exe -m pytest tests/api/test_forecast_api.py -q`确认失败；实现鉴权、幂等、CAS、202与状态DTO。展示READY+最近刷新失败的组合，不强制抹掉有效预测。
- [ ] admin模型切换在写事务外请求Bearer保护的`GET /ml/v1/model`，核对单个已加载制品metadata；事务内CAS绑定、提高binding/state版本使旧Plan失效，推理回显版本再查。unvalidated active返回MODEL_NOT_VALIDATED。shadow结果写入不改变Plan，但active切shadow的配置变更会禁用旧模型依据。回退fixed使用独立schema分支选择同scope已保存且仍有效的fixed版本，找不到则保持不可用，不能自动设60。
- [ ] 先导出runtime再生成OpenAPI子契约；所有新增路径经B0Router标B1与implemented。更新旧services预测设计引用，校验共享字段/错误模板与实际响应。
- [ ] HTTP真实读/刷新/轮询/历史分页验证，使用隔离API和真实ML；查询历史总量与Plan引用相等。记录报告`docs/reports/forecast-backend.md`。提交`feat(api): expose forecast reads and asynchronous refresh`。

### Task B5: 数据回放场景、种子与隐藏需求

**Files:** Create `simulation/simulator/{replay,replay_schemas}.py`、`simulation/tools/import_forecast_replay.py`、`simulation/tests/test_replay.py`、`simulation/migrations/versions/sim_0004_forecast_replay.py`；Modify simulator `{models,schemas,repository,controls,main,console}.py`和`static/{console.js,index.html}`；Modify backend `operations/{schemas,repository,client}.py`、`forecasting/history.py`；Create `ml/tools/export_replay.py`。

**Interfaces:** `export_replay(prepared_dir,series_manifest,split_manifest,output_dir)->dict`；`register_replay(db,manifest_dir)->str`本地CLI仅写模拟器私有表；`advance_replay_day(session,run,expected_sequence,key)->dict`；ScenarioCreate新增`scenario=REPLAY,replay_manifest_id`；ScenarioRun新增nullable initial_forecast（仅REPLAY）和history_seed，旧分支严格不变。

- [ ] 写隐藏数据与零销量纯测试，helper在replay_schemas定义：

```python
from simulator.replay_schemas import public_replay_summary

def test_public_summary_cannot_expose_environment_demand():
    value = public_replay_summary(dict(
        manifest_id="r1",start_date="2016-04-25",end_date="2016-05-02",
        demand=[99]*7,lost_units=[50]*7,seed_count=365))
    assert set(value) == {"manifest_id","start_date","end_date","seed_count"}
```

- [ ] 运行simulation聚焦测试确认失败；建立私有表，禁止把未来需求放Run.world/configuration/initial_snapshot。审计现有list/detail/console/日志序列化，使用显式白名单，不只删一个字段。
- [ ] export把种子与未来环境分成文件；CLI校验hash/时间分界后写sim私表，model/frontend无权读。backend初始种子只入Observation，不重放365天经营账本；init状态仍version1、无预留/在途，REPLAY可暂时无预测。
- [ ] 实现每日到货→销售→闭日→时钟推进原子事务；销售按min(D,stock)，S=0不生成非法正数销售事件。预期sequence冲突409，丢响应同键返回原结果；advance重复不扣货；到货不超原订单。
- [ ] 日内人工trigger、DEMAND_REVISED和任意advance步数对REPLAY拒绝。console默认只展示已发生实际销量/闭日/预测状态，不显示未来需求。episode完成后不自动把Mission标为已结算。
- [ ] 真实PG测试跨重启、两次同键并发、部分到货/零销量/缺货、日结束中途崩溃；backend与simulator源事件序号和账本一致。导出双方schema、同步版本兼容说明。提交`feat(simulation): add isolated daily retail replay`。

### Task B6: 经营对照、恢复与交接

**Files:** Create `backend/tools/verify_forecast_replay.py`、`backend/tests/integration/test_forecast_replay.py`、`docs/reports/forecast-replay.md`；Modify `backend/README.md`、`simulation/README.md`；Produce `docs/api/forecast-replay-result.json`。

**Interfaces:** CLI `--backend-url --simulation-url --ml-url --manifest-dir --output-dir --verify-restart`，三URL必须loopback且对应专用验收库；`evaluate_episodes(rows)->dict`汇总fill/lost/ending/cash/J；oracle只在该隔离driver的参照预测适配器内存在，产品ML服务/绑定不注册oracle模式。

- [ ] 先写配对实验断言：三方法同episode的demand hash、初始状态、候选、价格、交期完全一致；oracle不能成为普通模型manifest；所有现金/账本违规数为0才允许输出工程passed。
- [ ] 运行专用测试确认失败，完成30序列×3条件×3方法的driver；固定种子和选择规则，逐日等待源追平、预测Job、业务Plan稳定，再由隔离测试用户调用现有精确审批API。
- [ ] 输出逐episode原始指标及J分解；不以现金余额当利润，不把原销售序列当无约束真实需求，解释初始设定。失败episode不得从分母删除。
- [ ] 保存原Action/Plan/Forecast/账本/隐藏需求hash，停止自有服务后重启并用`--verify-restart`只读复核。再注入ML503、forecast worker丢租约、请求丢响应、source停机；已发送采购不可丢失，恢复不得重复执行。
- [ ] 运行本轮相关backend/模拟器测试、迁移漂移、runtime契约；分批/skip记录不累加。报告backend_ready/replay_ready与经营增强门槛分别是否通过。提交`test(forecast): verify replay decisions and process recovery`。

## B交接结果

C接收真实公开API、runtime生成类型、可用隔离REPLAY、两种预测状态（ready与失败/过期）、可点击历史forecast_id和后端保留的scope。B不得提前宣布Agent或前端已接通，也不能为演示打开生产自动审批。
