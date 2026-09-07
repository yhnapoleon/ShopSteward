# 数据存储与前端访问边界梳理

日期：2026-09-07。性质：依据现有需求与代码形成的**范围核对及契约建议**，不是已批准的新实现计划，也不表示下列拟议接口已经上线。本轮只读取资料、核对源码与生成文档，没有修改业务代码、数据库或飞书原文。

后续进展：用户同意后，已据此完成[首批数据字典](data-dictionary.md)、[补充OpenAPI](api/frontend-data.openapi.json)及[实施计划](superpowers/plans/2026-09-07-frontend-data-implementation.md)，并实现7个只读GET；当前runtime为29操作/28路径，见[测试报告](reports/frontend-data-test-report.md)。以下保留实施前边界分析的依据；具体字段与查询规则以新字典和契约为准。

## 1. 结论

应当现在明确“用户要查看/完成什么 → 所需事实及来源 → 持久化与计算规则 → 前端契约”，再补接口与必要迁移。无需等Agent或真实预测模型接入，也无需先把长期产品的所有表设计完。

现有文档足以确定首版经营底座、任务执行、Agent持续跟进与最小技能复用需要哪些**数据类别和语义**；精确字段、查询路径和索引属于技术设计，不能把建议写成产品负责人已经确认。多仓、批次、真实订单、回款、退款、多币种等更广业务尚缺足够定义。

当前实际情况：backend源码定义21张应用表（不含迁移元数据与simulator表），runtime提供22个操作。数据库已采用PostgreSQL；这次缺口主要是数据展示契约及部分业务元数据，而非数据库选型。frontend目录目前只有package.json与nuxt.config.ts，没有可供逐页对照的页面实现。

**B0完成不等于首版产品完成。**飞书DEC-003与《01》要求首版同时验收SC-01经营正确性、A-01真实Agent持续委托、L-01技能跨任务复用。B0是已完成的独立经营工作包；Agent相关持久化仍应列入整体首版清单，实施可分阶段。

## 2. 依据与适用顺序

本次以用户当前范围、仓库最新工程约定及代码判断“现在能做什么”；飞书说明产品目标与业务含义。飞书正文仍写“尚未实现”，属于2026-09-05时的进度描述，不能据此否认后来B0实现；同样不能用B0实现反向声称A-01/L-01已完成。

| 编号 | 本次在线读取的飞书页面 | revision | 支持的结论 |
|---|---|---:|---|
| F1 | [项目基础认知](https://mvtrg57bfb7.feishu.cn/wiki/UlzDwwlU9iy9zPkzRPOc9f6Yn4f) | 22 | 用户与产品总范围 |
| F2 | [服务谁，解决什么问题](https://mvtrg57bfb7.feishu.cn/wiki/KjAcwXL36iZVtSknhWUce3Xsn1f) | 13 | 店主应看到采购决定、现金影响、执行、预计到货及调整原因 |
| F3 | [经营数据与操作边界](https://mvtrg57bfb7.feishu.cn/wiki/WNMxwUZUqiSNYtkjJUbc1Tifnih) | 14 | 当前状态、经营条件、未来假设、执行记录；事实与预测分离 |
| F4 | [五层职责与首版范围](https://mvtrg57bfb7.feishu.cn/wiki/J9Lgwq9nviOT9QkdQ9tcyzqknsf) | 18 | 一致状态、推演、方案、执行与变化调整的输入输出 |
| F5 | [01 最小业务闭环](https://mvtrg57bfb7.feishu.cn/wiki/QMA4wBJHFiH7vikBFzacuJgqnuO) | 27 | 单店/单SKU/单供应商、SC01、持续任务、CSV整理、简报、技能复用 |
| F6 | [02 智能增强蓝图](https://mvtrg57bfb7.feishu.cn/wiki/V7sMwHq1kiFwwqkezHCcifGwnDe) | 39 | 预测、优化、知识、学习的后续深度；不一次全量建设 |
| F7 | [决策与变更台账](https://mvtrg57bfb7.feishu.cn/wiki/PZ2mwrytkiZozXk1GwncKa2lnAg) | 15 | DEC-003：首版真实Agent和最小持续学习；技术选型与排期待定 |

同时读取F5的SC01画板`XeJZw2VQQhXl8xbGeLCcH34Dn5c`、F6的L1–L3画板`U5QcwxwX3hRVwybWuImch8jQnqg`原始节点，提取全部文本核对；未据节点排列推断未验证的视觉连接。本次未重读其他画板、评论全文、课程原件或外部参考项目。

本地依据：

- [后端设计§3、§6～8、§15](backend-development.md)、[模拟器契约](simulation-contract.md)、[运行时OpenAPI](api/backend.runtime.openapi.json)、[实现状态](api/implementation-status.json)。
- [产品框架v2.1](../../docs/research/2026-09-05-shopsteward-detailed-blueprint-and-pm-review.md)、[首版闭环与分期](../../docs/research/2026-09-05-shopsteward-01-agent-mvp-and-roadmap.md)、[技术架构§4与§9](../../docs/research/2026-09-05-shopsteward-02-architecture-and-continuous-learning.md)。这些是产品/技术建议资料，其中SQLite、旧状态枚举及旧事务描述以最新B0实现为准。
- [业务数据模型](../backend/app/operations/models.py)、[任务/方案/到货模型](../backend/app/missions/models.py)、[审批/采购模型](../backend/app/execution/models.py)、[查询DTO](../backend/app/reporting/schemas.py)、[业务DTO](../backend/app/operations/schemas.py)。

本机原始读取快照保存在Git忽略的`var/data-boundary-feishu-documents.json`、`var/data-boundary-sc01.json`、`var/data-boundary-blueprint-123.json`；源码表清单在`var/data-boundary-table-inventory.json`。快照是本次读取证据，不是远程版本持续同步。

## 3. 应保存什么，哪些已有，哪些缺失

下表的“应有”描述逻辑数据，不要求一行对应一张新表。已有JSONB快照可以继续使用；只有稳定查询、索引或业务约束需要时才增加明确列/投影。

| 数据域 | 核心信息及来源 | 当前存储 | 前端当前可读与缺口 |
|---|---|---|---|
| 店铺与访问范围 | store_id、币种、业务时区、显示名称、用户对店铺的角色/权限 | stores有ID/币种；角色与门店授权在服务端TokenGrant配置；无用户/成员表 | 必须预先知道store_id；缺用户身份/可见店铺发现入口。名称/时区与正式登录尚未建模 |
| 商品 | SKU、名称、数量单位；后续按需要增加分类/图片/状态 | products的document目前为sku_id/name/unit | catalog可读基础字段。图片/分类等不是已有能力，也非首版硬性字段 |
| 供应商与采购报价 | supplier_id、SKU、单位采购价、币种、MOQ、包装量、交期、版本/有效期 | supplier_offers，已入Plan历史快照 | catalog可读；只有供应商ID，没有完整供应商档案/联系人/地址 |
| 当前销售价格 | 商品销售单价、币种、生效范围与来源 | SC01价格在simulator剧本中；发生销售后单价在销售事件中。backend catalog没有当前售价 | **需要展示或使用当前售价时补明确来源/契约**；不能把最近一次成交价当成当前标价 |
| 当前库存 | store_id×sku_id、on_hand、in_transit、来源时间和版本 | stocks；最新state_version在stores | dashboard可读。无warehouse_id、库位、批次、效期、调拨或盘点单 |
| 逐笔在途/到货 | Action/订单引用、SKU、订购量、已收量、剩余量、预计到货时间 | inbound_items；采购快照、回执与到货事件 | dashboard只有总量；Plan中有决策时在途快照，不能替代当前到货进度。缺当前明细查询 |
| 销售事实 | event_id、source run/sequence、SKU、数量、成交单价、发生时间/模拟时间 | business_events中SALE_RECORDED；相应唯一ledger_entries | **事实已保存，缺销售列表与区间汇总API**。无独立销售订单号、客户、渠道、退款明细 |
| 资金 | 现金、预留、应收；采购支出与销售形成应收的唯一效果 | stores、actions、ledger_entries、business_events | dashboard可读余额；缺经营流水查询。没有独立银行账户或应收结算明细；SC01无回款 |
| 需求假设/预测 | store/SKU、预测量、窗口、输入版本、截止/有效期、来源/方法/模型版本 | forecasts及stocks当前版本引用，Plan保存完整决策快照 | dashboard有剩余需求；Plan可读历史预测。缺独立“当前预测”查询；真实模型未接入 |
| 活动与策略 | 活动目标、关联SKU、时间窗口、现金底线、候选量、供应商、完成条件、版本 | Mission objective/policy/completion_criteria；时间窗口主要在Forecast；无campaigns独立表 | Mission可读当前任务策略。一个活动多个Mission/多个SKU及活动详情需进一步定义 |
| 方案与批准 | 输入事实/预测/报价/策略版本、候选、推荐量、hash、有效期、决定人/时间 | plans、approvals | Plan可查、可决策；审批人/时间已有存储但没有独立批准详情DTO，审计页需要有选择地补读字段 |
| 采购执行 | Action、关联批准/方案、不可变请求、执行状态、回执、外部订单号、异常证据 | actions、action_evidence | Action详情可读主要业务字段；缺按店铺/任务筛选列表。SUCCEEDED只代表已受理入账，不代表到货完成 |
| 持续任务/警报 | 目标、状态、版本、下次检查、告警事实/知晓/恢复、历史引用 | missions、schedules、alerts、mission_timeline | 现有Mission、Schedule、Alert、Timeline接口覆盖主要闭环操作 |
| 来源与后台运行 | 游标、成功时间、错误、任务结果、尝试数、租约、心跳、幂等回执 | source_cursors、source_schedules、job_runs、worker_heartbeats、command_receipts | freshness/Job详情/admin监控有选择性公开；不能直接返回全部运行内部字段 |
| Agent会话与运行 | 用户输入、任务引用、运行状态、工具调用及结果引用、模型/提示版本、成本/错误、恢复检查点 | **尚未实现**；设计稿有messages与AgentRun占位 | 产品首版需要，不能把占位OpenAPI当可调用接口；应提供可解释执行摘要，不要求展示模型私有推理过程 |
| 资料与交付产物 | 上传文件元数据/权限/来源、解析结果、报告引用、创建者、关联任务/运行 | **尚未实现** | CSV整理和简报交付要求有可追溯产物；建议DB保存元数据、文件/对象存储保存内容，具体实现待设计 |
| 记忆/技能/经验 | scope、类型、内容、来源、有效/替代关系、技能版本/状态、应用任务与反馈 | **尚未实现** | F5/F7已要求跨会话偏好与一次技能修订复用；完整字段与展示/管理入口待B2技术设计 |

数据来源目前以SC01合成世界为主。未来公开销量、合成库存/采购/现金、派生统计、模型预测需要保留来源类别和数据集版本，不能拼成声称真实的商家账目。准确字段命名与落库位置仍属待实施设计。

## 4. 前端应拿到哪些数据

以下是建议的最小视图契约，不要求为每个视图建设独立页面。

| 视图/任务 | 所需数据 | 已有入口 | 拟补的最小能力 |
|---|---|---|---|
| 打开应用/选择店铺 | 当前身份、角色、授权店铺、店铺名称/币种/时区 | 无身份与店铺发现API | 可采用GET /api/v1/me与GET /api/v1/stores；是建议路径，尚未实现 |
| 经营概览 | 现金/预留/可用/应收、库存、任务/警报数、新鲜度 | GET /api/v1/dashboard | 复用；若需要“本周销量/销售额”，接独立销售汇总，不混同余额 |
| 商品与库存 | SKU/名称/单位、采购报价、现货/在途/需求、当前售价（若有来源） | catalog + dashboard | 小规模先按SKU组合；需要分页/搜索时再提供商品/库存列表，不为重复字段造接口 |
| 销售记录/趋势 | 时间范围、SKU、销售数量、成交金额、桶粒度、完整性/来源 | 无 | 建议GET /api/v1/sales与GET /api/v1/sales/summary；从唯一销售事实聚合 |
| 采购与到货跟踪 | Action列表、采购量/金额/状态、已收/未收/ETA、关联Plan | GET /api/v1/actions/{id} | 建议增加GET /api/v1/actions和GET /api/v1/inbounds；批准仍走现有Plan decision |
| 经营流水 | 初始化/采购/到货/销售/需求变更的展示DTO、数值效果及引用 | 无通用经营流水查询；Mission timeline是任务历史 | 可增加GET /api/v1/ledger-entries；不要直接透传异构document，也不要称作完整会计总账 |
| 活动/任务工作台 | 目标、当前与历史方案、批准依据、执行/到货进度、告警/下次检查 | Mission/Plan/Alert/Timeline/Schedule | 先复用；需要审计人/时间、独立活动或当前预测时再补对应字段/接口 |
| Agent委托/资料/技能 | 消息、运行、产物、偏好和技能版本/应用来源 | 设计稿仅占位 | B2中完成数据及接口契约，且按A-01/L-01验收，不由前端硬编码成功 |

上述拟议路径未写入runtime OpenAPI，避免让前端误以为已经可调用。前端与Agent通过同一业务服务读取权威数据；前端不直连数据库，不读取simulator私有表，不使用服务token向内部事件入口伪造经营事实。

一个简单商品行目前可以由catalog产品/报价与dashboard.state.stocks按SKU关联，但两次独立请求不自动构成一致快照；报价、库存的时间/版本应显式显示。若页面必须保证同一时点，则由后端提供一致的聚合查询。批准/执行仍由服务端重新验证，不能依赖页面上看起来新鲜。

## 5. 在补接口前应固定的统计口径

| 指标/规则 | 可以依据现有文档确定的含义 | 尚需技术契约明确的部分 |
|---|---|---|
| 已售数量 | 去重且已接受的SALE_RECORDED数量之和；不是remaining_demand | 日期过滤、时间字段、分桶、分页/排序 |
| 销售金额 | 同一批销售事实的quantity×unit_price_minor之和 | 字段建议sales_amount_minor；无退款时可这样定义，不能提前称为净销售额或利润 |
| 可用现金 | cash_minor−reserved_cash_minor，由后端返回 | 前端仅转换显示单位，不自行加入应收 |
| 应收/待结算 | 已售但尚未结算的余额，与现金分开 | 账期/结算批次/回款/退款均未定义，SC01不发生回款 |
| 在途剩余 | 已确认订购量−已收量，按Action/SKU可追踪 | 准确到货状态枚举和分页DTO待定义；ETA未知须明确表示未知 |
| 库存流水 | 到货增加现货、销售减少现货；采购受理增加在途 | 期初锚点/排序/修正语义需明确；不能用库存变化直接反推销量 |
| 需求 | 当前剩余窗口的假设或预测，与历史销量分开 | 当前forecast查询的版本/有效期/来源缺失如何表达 |
| 时间 | 实际发生/接收与simulation_time分开，时区明确 | 演示图建议按simulation_time；真实经营按业务发生时间与店铺时区；区间建议[start,end) |
| 空区间 | 已证明该范围数据完整且无销售时可为0 | 尚未接入、未覆盖历史或来源缺页应返回未知/不完整标记，不伪装0 |
| 历史查询 | 时间窗内事实与来源、版本可追溯 | source_cursors仅证明当前追平，不能证明任意历史区间完整；需范围覆盖契约 |
| 商品售价/成本 | 当前报价与历史成交价不同；采购报价不等于已售商品成本 | 当前售价来源、历史进货成本分摊未定义，不据最近报价算真实毛利 |

API列表应统一store权限、过滤、稳定排序、游标分页、金额单位、nullable及错误格式。聚合响应应明确from/to、时间基准/时区、as_of、来源与完整性。已有事件JSONB能先支撑SC01级查询；按实际查询压力决定是否增加事件时间/类型索引或日汇总投影，不先复制多份“权威销量”。

原始事件与账本不是所有字段齐全的通用审计模型：目前事件时间主要在JSONB，缺统一received_at列；账本document包含INIT State、采购Receipt及业务Event三种形状。经营流水查询需要转换适配；不能直接假设每条账本都有统一cash_delta/created_at。资金预留/释放也并非各有一条独立财务流水；若要展示完整预留变更历史，应单独定义审计覆盖。

## 6. 可以现在定下的边界与仍需选择的事项

已有依据充分的部分：

1. 单店、单SKU、单供应商的活动备货首版；标识和DTO保持可扩展，但不承诺多仓/多平台能力。
2. 事实、预测、建议、批准和执行分离；金额为整数分、数量为整数件；当前状态与不可变历史并存。
3. 当前状态、逐笔采购/到货、销售事实、方案/批准、风险与持续任务必须可追溯；首版Agent和技能产物也需持久化。
4. 前端只通过有权限约束的API读取和提交业务命令；新页面不能直接改cash/on_hand，也不能因有编辑按钮就发明调账接口。

仍需形成明确产品/技术决定的部分（括号内为本次建议，不是已确认要求）：

- **“仓储”具体深度**：商品现货/在途看板，还是多仓库/库位/批次/WMS？（首版按前者。）
- **销售来源及时间跨度**：只展示SC01真实已发生事件，还是要历史销量图/公开数据驱动场景？（前者可立即补查询；后者需数据覆盖与导入说明。）
- **商品与供应商维护方式**：模拟器/约定文件导入，还是需要用户新增、编辑、上下架？（首版保留受控来源，按实际操作需求补命令。）
- **身份与店铺入口**：演示账号及固定场景，还是多人注册/登录/成员管理？（演示先补授权范围发现；正式身份系统另定。）
- **活动与任务关系**：是否需要活动日期、预算、多个SKU/多个Mission共用一个活动？（单场景先复用Mission；不要机械加campaigns表。）
- **财务展示程度**：余额/经营效果流水，还是结算、退款、成本核算、毛利？（当前前者；SC01E与真实财务另开范围。）
- **Agent交互与产物**：简洁会话+任务卡+产物入口已符合文档方向；上传大小、格式、保存期限、记忆/技能管理权限及运行摘要还需技术设计。

## 7. 建议的下一步交付

先把本表收敛为一份数据字典与前端契约：每个字段写清类型、含义、来源、更新者、事实/预测类别、可空性、可见角色、时间与版本。将已存在字段映射到当前表；拟增字段注明是否需要迁移；每个视图绑定一个或多个真实/待实现API及示例。

第一批最直接的缺口是**身份/店铺发现、销售查询与汇总、采购列表与当前到货明细、经营流水**。基础商品/库存看板先复用catalog/dashboard，避免为了接口数量拆出无实际用途的重复服务。接口字段和统计口径稳定后，可并行开发前端与后端；每完成一组更新runtime Swagger并做前后端联调。

Agent消息、运行、产物与记忆/技能契约作为同一首版的数据范围，分配到B2实施；无需等B1模型训练才设计，也不能因本次只补经营查询就从产品首版中删除。长期多仓、多币种、平台交易和高级财务模型继续按新增场景逐项定义。
