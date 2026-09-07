# 首批前端数据契约设计

实施状态（2026-09-07）：本设计已落实，7个GET已注册，runtime为29操作/28路径；见[测试报告](../../reports/frontend-data-test-report.md)。下文保留设计阶段的“拟实现”措辞，补充OpenAPI保留设计基线；当前可调用接口以runtime为准。

日期：2026-09-07。输入：用户同意在[边界核对](../../data-and-frontend-boundaries.md)之后明确数据字典与前端可调数据。输出：[数据字典](../../data-dictionary.md)、[7个拟增操作的OpenAPI](../../api/frontend-data.openapi.json)和实施计划。本次完成契约设计，不宣称新增路由已经上线；运行时仍以backend.runtime.openapi.json的22个操作为准。

## 1. 范围与选择

采用**基于现有权威表的只读查询与类型化投影**。相比直接暴露表/JSONB，这能稳定语义、过滤权限与内部字段；相比现在建设完整商品/仓储/财务子系统，它能直接补足首版查询而不引入没有来源的业务字段。

首批固定：演示身份发现、可见店铺、已记录销售明细/日汇总、采购列表、当前收货明细、经营效果流水；商品/库存/资金/任务/警报/方案继续复用现有接口。支持现有单店/SKU/供应商场景数据；查询按store_id隔离，也必须验证不同场景之间不会串数据。

本批不新增表/列、不迁移旧事实、不调用外部服务补数据。JSONB金额、事件类型、业务时间通过类型检查后查询/映射；真实性不足时保留未知，不造名称/当前售价/历史覆盖。

## 2. 操作清单

所有操作要求用户Bearer，无副作用，不需要Idempotency-Key。本表路径为**拟实现**。

| 方法/路径 | operationId | 参数 | 输出 |
|---|---|---|---|
| GET /api/v1/me | get_current_user | 无 | CurrentUser |
| GET /api/v1/stores | list_visible_stores | limit/cursor | StoreList |
| GET /api/v1/sales | list_sales | store_id必填；sku_id、成对from/to、limit/cursor可选 | SaleList |
| GET /api/v1/sales/summary | get_sales_summary | store_id/from/to必填；sku_id可选 | SaleSummary |
| GET /api/v1/actions | list_actions | store_id必填；mission_id/sku_id/status、limit/cursor可选 | ActionList，复用现有Action |
| GET /api/v1/inbounds | list_inbounds | store_id必填；mission_id/sku_id/arrival_status、limit/cursor可选 | InboundList |
| GET /api/v1/ledger-entries | list_ledger_entries | store_id必填；effect_type、limit/cursor可选 | LedgerEntryList |

没有为summary设计limit/cursor：统计所有匹配记录，不受明细页大小影响。v1只接受列出的筛选参数；禁止静默接受前端以为生效的warehouse_id、channel、真实日期粒度等未知参数，统一422。

## 3. 权限、错误与快照

- 复用require_user/authorize_store。admin可列全部已初始化店铺；其他用户仅列配置store_ids中已存在的店铺且roles非空。me允许合法用户看到空roles；stores此时为空。
- 店铺作用域接口先鉴权，再查询；跨店/不存在店铺均404 RESOURCE_NOT_FOUND，不泄露存在性。传入sku_id或mission_id时验证属于已授权store；即便store存在，跨店Mission也404。
- 非法/缺失Bearer为401 UNAUTHENTICATED；service身份为403 FORBIDDEN。显示按钮不代替服务端权限检查。
- 参数类型/枚举/未知query key/日期缺时区/单独from或to/from≥to/跨度>90天为422 VALIDATION_ERROR；游标不适配为422 INVALID_CURSOR。
- SQL/数据库不可用沿用503 DEPENDENCY_UNAVAILABLE。无法安全映射已存JSONB/关联缺失返回503 INVALID_STORED_DATA，retryable=false；不跳过坏记录、不伪装空列表，服务日志用安全记录ID定位，不返回原始payload。
- 聚合计数/金额/数量超出非负int64范围返回422 AGGREGATE_OUT_OF_RANGE，不截断或使用float近似。
- 每个店铺读响应以REPEATABLE READ READ ONLY事务一次读取授权资源、context与结果。建立快照后记录as_of；它是本次采样时间，不是源最后更新时间。
- freshness复用dashboard规则。STALE/UNKNOWN仍返回本地可读事实及标记，不触发同步，也不把旧数据说成最新。

## 4. 分页

limit默认20，1～100；next_cursor是string或null。每次请求重新应用当前授权与筛选，不依赖cursor提供权限。

| 列表 | 排序键 | 下一页谓词 |
|---|---|---|
| stores | store_id ASC | id>anchor_id |
| sales | sequence DESC,event_id DESC | (sequence,event_id)<anchor |
| actions | created_at DESC,id DESC | (created_at,id)<anchor |
| inbounds | action_id ASC,sku_id ASC | (action_id,sku_id)>anchor |
| ledger | state_version DESC,id DESC | (state_version,id)<anchor |

游标payload包含版本、列表种类、规范化作用域摘要、类型化排序锚点。作用域包含principal_id、当前角色/授权范围指纹、store_id、所有有效筛选；日期先转UTC规范形式再hash。limit不参与摘要，允许换页大小。解码校验版本/类型/范围/最大2048字符；这是查询一致性约束，不宣称提供防篡改签名或授权。

当前core分页工具只接受created_at/id，不能拿它伪造sales的时间或inbound.created_at。实施时仅为这些查询增加窄范围排序游标适配，不重写现有全部分页。

跨页不持有长事务或服务端缓存快照。新增事实通常出现在第一页之前；可变采购/到货状态可能在翻页之间改变。前端切换筛选或主动刷新时重置cursor；不能承诺跨页完整静态数据集。

## 5. 销售查询与日汇总

数据源限定当前门店SourceCursor对应scenario_run_id的已接受SALE_RECORDED。销售事件可能有乱序实际时间，分页按来源序号而非假设时间单调；时间筛选单独使用document.simulation_time。

明细from/to同时省略时读取全部本地已记录事实；同时提供时要求UTC规范化后的[from,to)且跨度≤90天。summary必须带完整区间。v1固定模拟时间、UTC日桶，避免把真实执行的几秒挤成一天，或假定不存在的店铺时区。

每桶是UTC日与查询区间的交集，按起点升序，无重叠且连续覆盖查询范围；90天跨度跨非零时刻最多91个桶。输出record_count、recorded_quantity、recorded_sales_amount_minor；空桶为0已记录值。总计等于全部桶之和，也等于所有匹配事实聚合，不能只加当前分页数据。

coverage固定RECORDED_EVENTS_ONLY。它刻意不提供COMPLETE：当前last_success_at只能证明一次追平，无法证明任意历史日期全部接入。UI固定说明“已同步销售记录”，空桶为“无已记录销售”；FRESH/STALE/UNKNOWN单独标明。销量≠剩余需求，成交额≠应收余额/回款/利润。

## 6. 采购与到货

ActionList直接复用现有Action及PurchaseReceipt/ProposedPurchase，不改审批或执行。可按任务/SKU/单个status筛选，默认所有状态。

InboundItem从inbound_items关联actions获取Mission/订单引用。默认包含已确认且已全收的历史采购；不因Mission暂停/取消过滤。arrival_status由数量决定，不依赖Action SUCCEEDED推断已到货。未知ETA或当前经营时刻时is_overdue为null；已全收为false；其余用simulation_time严格大于ETA，边界相等不算逾期。

金额、收货数、remaining与状态均由后端输出。前端可以链接原Action/Plan，但不能修改事实列或自行重新解释外部Receipt。

## 7. 经营流水映射

排序使用账本state_version/id，**不用尚不存在的统一created_at列**。具体增量和字段映射见数据字典§7。

- INIT返回原State作为opening_state，changes为null；不会给现金“加一次收入”。
- PURCHASE_ACCEPTED读取Receipt，关联Action.purchase_snapshot取得SKU；现金−total，在途+quantity。保留source_event_id原值，即使后来同步受理事件也不伪造另一个账本效果。
- GOODS_RECEIVED、SALE_RECORDED与DEMAND_REVISED解码已存Event，返回对应SKU、引用与时间。DEMAND_REVISED四个资金/库存增量全0，另返回新的remaining_demand。
- 采购回执只有recorded_at，simulation_time返回null；不可用expected_arrival_at、当前经营时间或后来到货时间替代采购时刻。
- 本版不支持日期过滤和期末“完整财务余额推算”，不包含逐笔预留释放、结算、退款、成本结转或净利润。列表不输出action_evidence原文。

## 8. 数据保存与迁移结论

这些接口读取21张现有应用表中的相关事实/投影，新增字段都是响应映射或派生值，**本批无需Alembic迁移**。也不为现有销售创建第二张可任意修改的sales事实表。

如将来需要售出成本/毛利、当前售价、实体仓库、真实销售订单、商家身份管理或历史数据覆盖，需要新业务字段、更新责任与迁移；不能自动把本规格的“无需迁移”推广到这些范围。当前Agent/文件/记忆/技能仍按完整产品首版要求保留在数据字典的后续部分，不在这7个查询操作中实现。

## 9. 前端使用与例子

用户身份→可见店铺→catalog/dashboard；按需加载销售、采购/到货和流水。Mission详情继续加载计划、警报和时间线，批准提交原Plan版本/hash。默认轮询已有GET；实时推送不属于本批。

示例请求（路径未实现前仅供Mock）：

```http
GET /api/v1/sales?store_id=store_demo&from=2026-09-07T00%3A00%3A00Z&to=2026-09-12T00%3A00%3A00Z&limit=20
Authorization: Bearer <user-token>
```

```http
GET /api/v1/sales/summary?store_id=store_demo&from=2026-09-07T00%3A00%3A00Z&to=2026-09-12T00%3A00%3A00Z
```

OpenAPI含所有7种成功响应和统一404示例。合成例子严格分开2026-09-07的实际执行时间与9月7～11日的经营时间；销售在经营9月9日记录10件/200元。两笔采购40/20件，最终期初1000元−400−200=400元，现货20+40−10+20=70，应收200、在途0。它们是契约样例，不是本轮在线服务结果。

## 10. 验收要求

契约阶段：OpenAPI3.1/schema/ref/required/null/枚举与例子通过；共享Action/State/Freshness/Error及可达schema与runtime逐项相等；示例汇总算术、桶连续性、到货关系、SC01账本核算通过；负例拒绝小数金额、缺字段、错误枚举、额外凭证字段及伪造完整性标记。现有设计契约校验继续通过。

实施阶段：用真实PG验证所有门店隔离、筛选与分页；特别覆盖“只读”“过滤后分页”“汇总不受页大小影响”“迟到时间不乱序游标”“重复事件不增销量”“同一采购不重复出账”“过期来源仍显示STALE”“UNKNOWN采购与已发取消Mission保留”。模拟器协议无需变更；当前B0回归通过后再更新runtime为29操作，不能在实现前先改统计数字。
