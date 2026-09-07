# 首批前端数据字典 v1

日期：2026-09-07。**新增7个GET接口已实现**，runtime现为29个操作、28条路径；基础提交为`YH / da79cbd`，实现保留在工作区。需求依据见[来源与范围核对](data-and-frontend-boundaries.md)；字段约定和示例见[前端数据OpenAPI](api/frontend-data.openapi.json)，实际服务schema见[runtime](api/backend.runtime.openapi.json)；处理规则见[设计规格](superpowers/specs/2026-09-07-frontend-data-contract-design.md)，验证见[测试报告](reports/frontend-data-test-report.md)。

状态含义：**已有**=当前代码保存/计算并可按接口访问；**新增查询**=本批已提供的7个只读接口；**后续范围**=本批不建立字段或表，不能返回伪造默认值。逻辑对象不必一一建表；派生展示字段不创建第二份权威事实。

## 1. 通用规则

| 项目 | v1约定 |
|---|---|
| ID | 不透明string，1～128字符；不解析业务含义，不依赖示例ID格式 |
| 金额 | `_minor`为整数分；币种CNY；不能用二进制浮点累积金额；单值与聚合结果受int64业务范围约束 |
| 数量 | 非负/正整数按schema；单位piece。库存、在途、销量、预测量分别命名 |
| null | 机器schema列为required的字段仍必须出现；null只用于明确允许的未知/不适用，不等于0 |
| 时间 | RFC3339带时区；查询区间与日桶规范化为UTC，事实时间保留显式时区并复用既有DTO序列化。真实as_of/occurred_at与模拟simulation_time分开 |
| 日期统计 | 本批固定simulation_time、UTC、日粒度；筛选[from,to)，跨度≤90×24小时；不暗示店铺实际业务时区为UTC |
| 类型安全 | DTO拒绝额外字段；前端如处理超出JS安全整数范围的值，需无损整数解析/计算，不能静默舍入 |
| 访问角色 | user身份且门店可见；沿用viewer/operator/approver/admin体系。admin可见所有店铺；service身份不作为用户 |
| 写入者 | 经营事实由现有导入/事件/执行事务更新，前端读取或提交受控命令；GET无业务写入、不调用供应商、不推进模拟时间 |
| 版本 | state_version是当前门店决策输入版本；每条历史Plan/账本保留自己的版本，不用当前版本覆盖历史 |

## 2. 身份、店铺与来源

| 字段 | 类型 / 可空 | 来源与更新者 | 前端用途 / 状态 |
|---|---|---|---|
| principal_id | string / 否 | 服务端TokenGrant配置；配置维护者 | 显示当前身份；新增GET /me |
| roles | role[] / 否，可空数组 | TokenGrant.roles，输出去重 | 界面能力提示；服务端始终重新鉴权 |
| store_scope | ALL或ASSIGNED / 否 | admin→ALL，其余ASSIGNED；计算 | 作用范围提示，不返回凭证或全量配置 |
| store_id | string / 否 | stores.id；场景初始化 | 门店选择、所有店铺数据查询 |
| currency | CNY / 否 | stores.currency；初始化 | 金额显示 |
| source_type | simulation / 否 | source_cursors.source | 合成场景标记，不表示真实商家接入 |
| simulation_time | datetime / 是 | stores.simulation_time；已接受事件更新 | 当前已同步经营时刻 |
| 店铺名称、地址、业务时区 | 不在本批响应 | 目前无可靠存储/来源 | 后续范围；前端可显示store_id，不编造名称 |

GET /me不负责登录或发token。GET /stores只列已初始化、对当前身份可见的店铺；没有授权店铺时返回空列表。当前不新增users、memberships或stores扩展列。

## 3. 已有商品、报价、库存与资金

以下继续使用catalog/dashboard，避免接口重复。Product/Offer的完整结构在[现有runtime](api/backend.runtime.openapi.json)。

| 对象 / 字段 | 类型 / 可空 | 持久化 / 事实来源 | 访问 |
|---|---|---|---|
| Product.sku_id、name、unit | string、string、piece / 否 | products.document；模拟器初始化catalog | GET /catalog |
| Offer.supplier_id、sku_id | string / 否 | supplier_offers主键与document | GET /catalog |
| Offer.unit_price_minor | 正整数 / 否 | 报价采购单价，非售价 | GET /catalog |
| minimum_order_quantity、pack_size | 正整数 / 否 | 报价约束 | GET /catalog |
| lead_time_seconds | 非负整数 / 否 | 报价交期秒数 | GET /catalog |
| offer_version、valid_from、valid_until、currency | string、datetime、datetime、CNY / 否 | 版本化报价有效性 | GET /catalog |
| Stock.on_hand、in_transit | 非负整数 / 否 | stocks列；唯一经营事件/采购受理入账 | dashboard.state.stocks |
| remaining_demand、forecast_version | 非负整数、string / 是 | stocks当前预测投影；forecasts保留版本 | dashboard.state.stocks；不是销量 |
| State.cash_minor | 非负整数 / 否 | stores；受理采购扣减，SC01不回款 | dashboard.state |
| reserved_cash_minor | 非负整数 / 否 | stores；采购发送/核对流程维护 | dashboard.state；不等于实际支出 |
| available_cash_minor | 非负整数 / 否 | cash−reserved，后端计算，不单独存 | dashboard.state |
| receivables_minor | 非负整数 / 否 | stores；销售事件增加 | dashboard.state；不加入可用现金 |
| state_version、data_as_of、simulation_time | 正整数、datetime?、datetime? | stores；实际写入更新 | 版本/时间提示 |
| 当前售价、分类、图片、供应商名称/联系人 | 本批不新增 | 没有完整主数据来源 | 不从采购价/最近成交价猜测 |
| 仓库、库位、批次、效期 | 本批不新增 | 现有stocks只有store_id×sku_id | 不展示为已经支持的WMS能力 |

小规模商品行可按SKU组合catalog与dashboard；两次请求不是同一快照。涉及批准的依据必须展示Plan快照和hash，并交服务端重验。

## 4. 新增读响应的共同上下文

销售列表/汇总、采购列表、收货明细和经营流水统一返回`context`，同一响应的context与数据来自一个只读一致事务。

| 字段 | 类型 / 可空 | 数据来源 | 含义 |
|---|---|---|---|
| store_id、currency | string、CNY / 否 | stores | 查询作用范围和金额单位 |
| state_version | 正整数 / 否 | stores.state_version | 当前查询看到的状态版本 |
| as_of | datetime / 否 | 只读快照建立后采集服务器时间 | 响应采样时间，不是历史完整性证明 |
| simulation_time | datetime / 是 | stores.simulation_time | 已应用的经营时刻 |
| source_sequence | 非负整数 / 是 | source_cursors.last_sequence | 连续已接受来源游标，非全局ID |
| freshness.status | FRESH/STALE/UNKNOWN / 否 | 复用dashboard新鲜度计算 | 当前源同步可信度 |
| freshness.data_as_of、last_sync_at | datetime / 是 | stores.data_as_of、source_cursors.last_success_at | 最近事实/成功同步时间 |

列表沿用`items + next_cursor`，新增context不改现有旧接口。每次分页均重新鉴权；分页游标不是持续数据库快照，更新后的采购/到货状态可能在翻页间改变，前端刷新从第一页开始。

## 5. 销售事实与汇总

权威来源：`business_events`中已被接受的`SALE_RECORDED`；使用门店关联的scenario_run_id过滤，不再次合并账本中的同一销售效果。

| SaleRecord字段 | 类型 / 可空 | 存储或计算 |
|---|---|---|
| event_id、sequence | string、正整数 / 否 | business_events主键/序号 |
| sku_id | string / 否 | document.payload.sku_id |
| quantity | 正整数 / 否 | payload.quantity |
| unit_price_minor | 正整数 / 否 | payload.unit_price_minor，本次成交价 |
| sales_amount_minor | 正整数 / 否 | quantity×unit_price_minor |
| occurred_at | datetime / 否 | document.occurred_at，真实时间轴 |
| simulation_time | datetime / 否 | document.simulation_time，本批筛选/统计时间轴 |

GET /sales用于明细。GET /sales/summary的字段如下：

| 字段 | 类型 / 可空 | 口径 |
|---|---|---|
| from、to | datetime / 否 | 回显规范化UTC区间，包含起点、不含终点 |
| time_basis、timezone、granularity | simulation_time、UTC、day / 否 | 本版固定，不开放未实现的真实时间/任意粒度选项 |
| coverage | RECORDED_EVENTS_ONLY / 否 | 只承诺已同步记录的统计，不声称任意历史完整 |
| record_count | 非负整数 / 否 | 唯一销售事件数，不命名为订单数 |
| recorded_quantity | 非负整数 / 否 | 所有匹配记录的quantity总和，不限于一页 |
| recorded_sales_amount_minor | 非负整数 / 否 | 所有匹配记录成交金额和，非利润、净收入或回款 |
| buckets | SaleBucket[] / 否 | UTC日桶升序；每桶from/to与查询区间求交，含相同3个统计字段 |

没有匹配记录的桶返回0计数与0已记录量，前端文案应为“无已记录销售”；来源未知或过期同时展示相应状态，不能画成“已证实真实销量为0”。新增真实历史导入以后，再制定可证明区间覆盖的契约。本批不新增sales表或日汇总表。

## 6. 采购执行与当前到货

采购列表直接复用现有Action DTO，不另造一套采购状态：`id/mission_id/plan_id/approval_id/status/quantity/amount_minor/currency/external_order_id/receipt/last_error/created_at/updated_at/purchase_snapshot`，类型与nullable逐字段和runtime一致。来自actions，批准与执行服务维护；前端可读不可直接改状态。

| InboundItem字段 | 类型 / 可空 | 持久化或计算 |
|---|---|---|
| action_id、sku_id | string / 否 | inbound_items复合主键 |
| mission_id | string / 否 | actions.mission_id |
| external_order_id | string / 是 | actions.external_order_id，不编造外部订单 |
| ordered_quantity | 正整数 / 否 | inbound_items.ordered_qty |
| received_quantity | 非负整数 / 否 | inbound_items.received_qty，已接受到货累计 |
| remaining_quantity | 非负整数 / 否 | ordered−received，received不可超过ordered |
| expected_arrival_at | datetime / 是 | inbound_items.expected_arrival_at，模拟经营时间 |
| arrival_status | NOT_RECEIVED/PARTIALLY_RECEIVED/RECEIVED / 否 | received=0、0<received<ordered、received=ordered |
| is_overdue | boolean / 是 | 全收为false；未全收且ETA/当前模拟时间未知为null；否则simulation_time>ETA |

到货明细默认包括已收完采购，可按arrival_status过滤。Action SUCCEEDED=受理且资金/在途入账；RECEIVED=数量已全收，二者不能互换。暂停/取消Mission后已发采购仍在列表中。列表不显示原始错误证据、请求快照、租约token或服务凭证。

## 7. 经营效果流水

权威来源：ledger_entries。该表的document存在INIT State、采购Receipt、业务Event三种形状，需后端映射为LedgerEntryView。不能直接给前端raw document再让它猜语义。

| 字段 | 类型 / 可空 | 含义 / 来源 |
|---|---|---|
| id、state_version、effect_type | string、正整数、效果枚举 / 否 | 原账本字段；历史版本允许缺口 |
| sku_id | string / 是 | 非INIT从事件/关联Action取得；INIT整店快照为null |
| action_id、source_event_id | string / 是 | 原有明确引用；无来源时null，不事后伪造 |
| occurred_at | datetime / 是 | Event.occurred_at、Receipt.recorded_at、INIT.data_as_of |
| simulation_time | datetime / 是 | Event或INIT提供时返回；仅有采购回执时null |
| changes | LedgerChanges / 是 | 非INIT为下面4项增量；INIT为null |
| opening_state | State / 是 | 仅INIT有完整期初State，其余null |
| remaining_demand_after | 非负整数 / 是 | 仅DEMAND_REVISED返回payload.remaining_demand，其余null |

| 效果 | cash_delta_minor | receivables_delta_minor | on_hand_delta | in_transit_delta |
|---|---:|---:|---:|---:|
| PURCHASE_ACCEPTED | −受理总金额 | 0 | 0 | +受理量 |
| GOODS_RECEIVED | 0 | 0 | +到货量 | −到货量 |
| SALE_RECORDED | 0 | +quantity×成交价 | −销售量 | 0 |
| DEMAND_REVISED | 0 | 0 | 0 | 0 |

INIT返回期初快照，不当成收入增量。采购受理回执和对应受理事件只产生一个账本效果；不因展示而重复计数。本批不提供按日期过滤，因为采购回执没有模拟时间，不能混用真实时间和经营时间筛选。

该接口不含预留/释放的完整变化历史，不提供成本结转、利润、净资产、应收逐笔结算或银行对账；前端标题使用“经营流水”。在本SC01内可以从INIT与确认效果核对现金/现货/在途/应收，但不能据此重建全部历史available_cash。

## 8. 沿用与后续数据对象

| 对象 | 本批处理 | 后续设计范围 |
|---|---|---|
| Mission/Policy/Schedule | 复用现有目标/策略/状态/周期DTO；现金底线由正式策略校验 | 独立活动、多SKU共享预算、正式任务类型拓展 |
| Plan/DecisionSnapshot | 复用不可变事实、预测、报价、在途与策略快照；前端批准回传原版本/hash | 不把当前商品资料替换历史决策依据 |
| Approval | approvals已有actor/decision/hash/time；本批不增审批审计详情接口 | 需要审计页时再定义授权可见字段 |
| Forecast | 历史Plan可读预测快照，dashboard有剩余需求 | 独立当前预测API、真实模型输入/版本/效果 |
| AgentRun/消息 | 保留整体产品首版要求，本批经营读API不实现它们 | principal/store/mission、触发来源、状态、工具结果引用、模型/提示版本、成本、恢复信息 |
| Artifact/上传资料 | 不将本机路径直接作为公开下载地址 | 存储文件内容；DB管理引用、来源、权限、MIME、大小、hash、关联任务/运行与保留规则 |
| Memory/Skill/Experience | 不冒充B0已有数据 | 有范围与来源的偏好、有效/替代关系、技能版本、来源经历、实际应用与反馈 |
| 内部恢复/幂等 | 现有JobRun/source cursor/command receipt等继续由服务维护 | 对前端只输出业务状态与安全错误摘要，不把内部表全量开放 |

本批7个读API无需新增数据库表/列。未来需要完整售价、仓储、结算、真实数据覆盖、用户管理和Agent存储时，按对应业务事实新增字段与迁移；不先为未知需求建空表。详细接口参数、响应示例与校验脚本由[API入口说明](api/README.md)维护。
