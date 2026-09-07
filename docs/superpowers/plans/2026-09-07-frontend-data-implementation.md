# 首批前端只读数据接口实施计划

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task in the current session. Do not run shared test databases concurrently.

**Goal:** 实现数据字典定义的7个GET接口，使前端能发现店铺、查询已记录销售、采购与到货以及经营流水。

**Architecture:** 复用当前PostgreSQL事实与投影；新增只读查询/DTO及窄范围游标适配；不新增数据事实副本或修改执行链路。

**Tech Stack:** 当前FastAPI/Pydantic、SQLAlchemy、PostgreSQL、pytest、httpx；不新增依赖。

**Spec:** [设计规格](../specs/2026-09-07-frontend-data-contract-design.md)、[数据字典](../../data-dictionary.md)、[OpenAPI](../../api/frontend-data.openapi.json)。

## Global Constraints

- 本计划已实施并验收；runtime为29操作/28路径。见[测试报告](../../reports/frontend-data-test-report.md)及[HTTP证据](../../api/frontend-data-http-result.json)。
- 基础HEAD为YH/da79cbd；保留现有文档改动。本轮不自动提交/推送。
- 无新增表/列/迁移；GET无业务写入、无供应商HTTP、无模拟推进。
- user+门店授权，service不得作为用户；其他门店不可见。查询参数只接受规格列出的字段。
- ReadContext与业务结果使用同一REPEATABLE READ READ ONLY事务。
- 时间固定模拟时间/UTC/[from,to)，日期跨度≤90天。销量仅承诺RECORDED_EVENTS_ONLY。
- 默认页大小20，范围1～100；游标绑定当前身份/授权/规范化筛选，跨页无持久快照承诺。
- 运行PG测试前按HANDOVER配置精确的shopsteward_test/shopsteward_sim_test；不同测试套件串行。不得清理开发库。

## 文件责任

| 文件 | 职责 |
|---|---|
| backend/app/api/router.py | 添加me/stores只读身份发现路由 |
| backend/app/reporting/read_schemas.py | 依据OpenAPI增加新查询DTO；Action/State/Freshness直接导入现有模型 |
| backend/app/reporting/read_repository.py | 权限后查询、ReadContext、销售聚合、到货与账本映射 |
| backend/app/reporting/read_pagination.py | 仅新增查询的多种排序键游标；不修改现有分页行为 |
| backend/app/reporting/read_router.py | sales/summary/actions/inbounds/ledger的路由、参数校验和只读事务 |
| backend/app/main.py | 注册read_router |
| backend/tests/integration/test_frontend_reads.py | 权限/隔离、筛选分页、汇总、只读、真实DB快照验收 |
| backend/tests/unit/test_read_projections.py | 桶边界、收货状态、账本异构形状与非法存储负例 |

## Task 1：身份、店铺发现和共同读取基础

**Interfaces:**

- `current_user(principal) -> CurrentUser`，仅principal_id/去重roles/store_scope。
- `list_stores(session, principal, *, limit, cursor) -> StoreList`。
- `read_context(session, store_id, settings) -> ReadContext`，由路由只读事务调用。
- `encode_read_cursor(scope, anchor) -> str`及`decode_read_cursor(cursor, scope, key_types) -> tuple | None`；类型限定str/int/aware datetime，按列表种类显式传入。

- [x] 新增集成负例，先运行确认新路径404；复用现有environment/headers，最低测试如下：

```python
async def test_identity_discovers_only_authorized_store(db):
    async with environment(db) as (seed, client):
        me = await client.get('/api/v1/me', headers=headers('viewer'))
        assert me.status_code == 200
        assert me.json() == {
            'principal_id': 'viewer', 'roles': ['viewer'], 'store_scope': 'ASSIGNED'
        }
        stores = await client.get('/api/v1/stores', headers=headers('viewer'))
        assert stores.status_code == 200
        assert {s['store_id'] for s in stores.json()['items']} == {seed['store_id']}
        assert 'token' not in me.json()
```

- [x] 添加admin分页、无授权空列表、service403、无凭证401、游标跨身份/换筛选422；给另一环境初始化第二店铺证明不是只测单店空库。
- [x] 根据OpenAPI实现CurrentUser/StoreSummary/StoreList/ReadContext。店铺SQL按授权过滤后再order/limit：

```python
query = select(Store).order_by(Store.id)
if 'admin' not in principal.roles:
    query = query.where(Store.id.in_(principal.store_ids if principal.roles else []))
if anchor is not None:
    query = query.where(Store.id > anchor[0])
rows = list(await session.scalars(query.limit(limit + 1)))
```

- [x] 所有日期锚点要求带时区，整数锚点拒绝bool/float；作用域hash包含当前principal/角色/store授权及规范化筛选。错误统一INVALID_CURSOR。不要复用created_at分页器伪造字段。
- [x] 定向测试通过后检查新DTO不含token、lease或其他用户信息；保留改动供后续任务，不自动commit。

## Task 2：销售明细与日汇总

**Interfaces:**

- `list_sales(session, store_id, *, sku_id, start, end, limit, cursor) -> SaleList`。
- `summarize_sales(session, store_id, *, sku_id, start, end) -> SaleSummary`。
- `sale_view(row) -> SaleRecord`、`day_buckets(start, end, records) -> list[SaleBucket]`；前者按已有SaleEvent校验document，后者用UTC日边界并裁切查询起终点。

- [x] 使用test_operations的event/ingest制造两条销售，重复投递其中一条；明细limit=1，而汇总必须包含两条且不重复。检查明确预期quantity和amount，不只比较两个可能同错的端点。
- [x] 覆盖午夜边界、非UTC偏移输入规范化、from包含/to排除、单边日期422、90天上限、空桶RECORDED_EVENTS_ONLY、STALE仍返回已录事实。用与sequence顺序相反的occurred_at证明分页不依赖时间单调。
- [x] 查已接受EventRow，连接SourceCursor.store_id；先store/sku/时间过滤，再按sequence/id倒序分页。只统计SALE_RECORDED，不union同一销售的ledger。

```python
query = (
    select(EventRow)
    .join(SourceCursor, SourceCursor.scenario_run_id == EventRow.scenario_run_id)
    .where(SourceCursor.store_id == store_id,
           EventRow.document['event_type'].astext == 'SALE_RECORDED')
    .order_by(EventRow.sequence.desc(), EventRow.event_id.desc())
)
```

- [x] 日期在读取前规范化，SQL或类型化映射后筛选必须遵守“先筛选再分页”。JSONB取值无法解释时503 INVALID_STORED_DATA，不跳过。不把缺少历史证明改成COMPLETE。
- [x] 汇总从所有匹配记录计算Python整数和/数据库精确numeric，应用int64范围检查；桶生成不使用服务器本地时区。将结果与ReadContext一起在路由同一只读事务返回。
- [x] 运行本任务定向测试及契约例子校验，修复失败后继续。

## Task 3：采购列表与收货明细

**Interfaces:**

- `list_actions(session, store_id, *, mission_id, sku_id, status, limit, cursor) -> ActionList`，复用现有Action模型。
- `list_inbounds(session, store_id, *, mission_id, sku_id, arrival_status, limit, cursor) -> InboundList`。
- `inbound_view(inbound, action, simulation_time) -> InboundItem`，无需外部HTTP。

- [x] 使用test_execution既有planned/approve与受控Supplier执行采购，创建两笔或两个隔离门店事实；验证filter在limit之前，Action列表与同ID详情逐字段相等。
- [x] 收货量0/部分/全部对应明确枚举。核心纯函数断言：

```python
ordered, received = 40, 10
remaining = ordered - received
status = 'RECEIVED' if received == ordered else 'PARTIALLY_RECEIVED' if received else 'NOT_RECEIVED'
assert (remaining, status) == (30, 'PARTIALLY_RECEIVED')
```

- [x] 加入已全收ETA未知仍is_overdue=false、未全收ETA未知为null、simulation_time=ETA为false、稍后为true；实际wall-clock变化不得改变此判断。
- [x] 实现Action分页(created_at,id)，Inbound分页(action_id,sku_id)。验证Mission属于请求store；暂停/取消不能隐藏已发送Action/Inbound。
- [x] 运行采购/到货与原test_execution、test_execution_recovery相关回归；确认查询没有触发外部Supplier调用或写入。

## Task 4：经营流水映射

**Interfaces:**

- `ledger_view(row, action_by_id) -> LedgerEntryView`，只接受规格列出的5种效果。
- `list_ledger_entries(session, store_id, *, effect_type, limit, cursor) -> LedgerEntryList`。

- [x] 给纯函数构造INIT State、受理Receipt、到货/销售/需求Event；逐项断言字典§7四项增量，Receipt无模拟时间必须返回null，INIT只返回opening_state。
- [x] 把非法或缺失关联Action的Receipt列为503 INVALID_STORED_DATA；不能在dict缺字段时填0或跳过记录。
- [x] 按state_version/id倒序、effect_type过滤后分页；按页批量读取需要的Action映射SKU，避免每行N+1。只返回LedgerEntryView，不透传document。
- [x] 实际SC01读取流水，确认现金40000、应收20000、现货70、在途0，采购2条/到货2条，重复采购回执与受理事件不再出现另一效果。
- [x] 检查未经实现的日期筛选返回422；用户不能误以为把Receipt真实日期当作模拟日期筛选。保留state_version缺口，不补造资金预留流水。

## Task 5：整体联调、契约状态与交接

- [x] 以viewer反复调用7个GET，比较业务State、ledger/events/jobs/commands/alerts/timeline计数前后不变；同步/worker不在此测试并行运行，排除正常后台写入干扰。
- [x] 使用数据库屏障在读取过程中提交另一笔事实，证明context与列表/汇总来自同一快照；跨页变化按设计不承诺静态快照。
- [x] 设置两套专用测试DB，串行运行backend全量及simulator全量；运行Ruff/格式和Alembic check（预期没有迁移）。
- [x] 导出runtime；仅在7路由实际可用后将实现清单追加这7个operationId，runtime计数29操作/28路径。源码只增7个新路径，原22操作/21路径保留。
- [x] 调整validate_frontend_data_contract.py中的“尚未实现路径不在runtime”断言为“实现状态按清单逐路由匹配”，保留共享schema/算术/负例验证。设计稿保留planned含义，运行证据用runtime与清单表示。
- [x] 从实际服务获取7接口的schema匹配响应，并核验没有schema-only成功。记录请求/响应、权限、数据口径和测试结果；更新HANDOVER/PROJECT_CONTEXT/API README，本计划逐项完成后标记。

契约阶段已执行的验证：OpenAPI7操作/22schema/14响应示例、8个runtime共享schema一致、SC01算术、10个schema负例和4个跨字段负例通过；它们不代替上述实现/PG/真实HTTP验收。

## 实施记录

2026-09-07完成。增加read_projections.py承载纯映射，read_queries单元测试覆盖日期/游标；SQL和路由由主代理实现，投影由子代理实现，独立复审后修复问题。保持当前YH工作区，不提交/推送；共享测试库串行运行。最终backend 186、simulator 12通过；HTTP读取既有持久SC01（未重新推进场景），7接口及页大小1的列表重建通过。

时间说明：日期区间/日桶规范化为UTC；复用Action/Receipt/State的既有序列化，事实时间保留RFC3339显式时区，以保持列表与详情一致。商品/库存展示继续复用catalog/dashboard，未新增页面。
