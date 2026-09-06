# Simulator 行为契约与 B0 协作顺序

版本：0.2.0-draft · 日期：2026-09-06 · 状态：完整目标契约；create/events/purchases/query/advance五接口已实现，显式SC01及双方重启回放已验证；周期调度和更广故障矩阵仍属后续阶段。启动与边界见[Simulator说明](../simulation/README.md)。

配套：[Backend 开发规范](backend-development.md)、[外部服务 OpenAPI](api/services.openapi.json)、[Backend OpenAPI](api/backend.openapi.json)。JSON 文件定义 payload；本文定义产生这些 payload 的状态转移、事务、顺序、重复和故障行为。二者一起构成契约。

## 1. 先开发谁

**backend 可以现在开始细化和实施，不需要先完成完整 simulator。** 先固定本文的 v0.2 契约，backend 用契约样例/fake 开发数据库、规则和 API；simulation 同期实现最小五接口。在第一次采购跨进程联调前接入真实持久 simulator，随后验证恢复。

| 顺序 | backend 产物 | simulator 产物 | 能证明什么 |
|---|---|---|---|
| 契约先行（本文） | 输入 DTO、错误、Action/事件幂等语义 | 相同 DTO 与 SC01 状态转移约定 | 团队可以独立开始开发；尚无运行结果 |
| B0-01 / B0-02 | API/DB、INIT、事件账本、最小持久 runner | 创建 run、catalog/初始状态、事件拉取 | 首次导入和一次销售/到货事件能够正确入账 |
| B0-03 / B0-05 的首个切片 | 手动检查、Plan、批准、发送、唯一回执入账 | 采购受理/按 action_id 查询，采购记录持久化 | 采购40后现金600、现货20、在途40；重复命令无重复效果 |
| B0-05已验证 / 后续B0-06/07 | 审批核对、显式SC01；后续周期/事件调度 | advance四阶段已实现；受控测试覆盖丢响应 | SC01数值、UNKNOWN核对及双方重启已验证；后台连续运行仍待后续验收 |

前两行不以 simulator 完整完成为前置；后两行不能用永远返回 ACCEPTED 的 mock 宣称完成。B0 不建设随机需求平台、真实商城、复杂多供应商、Agent 环境或 benchmark 适配框架。

## 2. 唯一世界与存储所有权

- B0 默认一个 HTTP simulation 服务，拥有 run、模拟库存/现金/应收、事件日志、采购订单、命令幂等记录和模拟时间。多个客户端共享该世界。
- backend API 和 worker 都通过适配协议访问，不能各启动一份内存世界。进程内 fake 仅用于开发和纯逻辑测试。
- simulation 使用持久 PostgreSQL 表及自己的迁移。可共用 PostgreSQL 实例，但独立 schema 与访问权限；不读写 backend 表。模拟状态和 backend 投影的同步只能通过初始化、事件、回执完成。
- 每个 run 对应一个全新 store_id；首次创建从 SC01 配置产生双方一致的商品、报价和初始预测。backend 导入 initial_catalog，不另行硬编码不同报价。
- backend 独占审批、资金预留与 state_version；simulation 只校验自己的报价、现金和采购输入，不信任客户端金额。初始化 State 中 reserved_cash_minor=0、available_cash_minor=cash_minor、state_version=1 仅是导入种子；此后源 sequence 不等于 backend state_version，模拟器不递增或控制后者。
- B0 的多个 run 隔离；同一 run 的采购、advance 与事件序号分配在 run 行锁下串行。进程重启恢复同一 run，不自动创建新世界。

## 3. 五个最小接口

| 接口 | 请求/响应要点 | 行为要求 |
|---|---|---|
| POST /sim/v1/runs | ScenarioCreate → ScenarioRun，含 initial_catalog/state/forecast | 相同命令键返回同一个 run 与原始初始化响应，不返回变动后的当前状态 |
| GET /sim/v1/runs/{run_id}/events | after_sequence、limit → EventPage | 无副作用；按序拉取；空页和重试不推进模拟时间 |
| POST /sim/v1/purchases | PurchaseRequest → PurchaseReceipt | 同 action_id 永远指向同一采购内容；受理、扣模拟现金、增加在途、写事件同事务 |
| GET /sim/v1/purchases/{action_id} | PurchaseReceipt 或404 | 已提交回执可重启后查询；GET 不创建订单、不触发受理 |
| POST /sim/v1/runs/{run_id}/advance | steps → AdvanceResult | 唯一命令推进有限场景步骤，不隐含在轮询中执行 |

所有 POST 要求 Idempotency-Key。服务端保存 principal + operationId + key、规范化请求摘要、目标资源与响应；摘要包含路径 run_id 和请求体，不能只比较 body。不同内容复用相同键返回409 IDEMPOTENCY_KEY_REUSED。采购还以 action_id 建独立唯一约束；不同幂等键使用相同 action_id/相同内容也只返回原采购，不重复受理。鉴权和资源授权先于幂等回放。

run 和 advance 的命令记录与其世界变化同一事务提交。run 创建响应丢失时，原命令键必须找回原 run。backend 的开发入口持久化命令与 JobRun，向 simulation 转发稳定命令键，不能每次 runner 重试生成一个新键。

## 4. 源事件顺序与原子效果

初始快照不进入增量日志，backend 本地记录 INIT，cursor=0；第一条源事件 sequence=1。run 内 sequence 连续递增；用受 run 行锁保护的事务计数器分配，回滚不消耗序号。每条事件有稳定 event_id、schema_version、event_type、store_id、真实 occurred_at、simulation_time 和 typed payload。

| 事件 | 模拟器与 backend 的一次性业务效果 |
|---|---|
| PURCHASE_ACCEPTED | cash -= total_minor，in_transit += quantity；backend 同时释放本动作本地预留 |
| GOODS_RECEIVED | in_transit -= quantity，on_hand += quantity；按 action_id 累计，不超过确认采购量 |
| SALE_RECORDED | on_hand -= quantity，receivables += quantity × unit_price_minor；剩余需求=max(0,旧剩余需求-quantity) |
| DEMAND_REVISED | 剩余需求替换为 payload 数值；不重新扣已经计入的历史销售，不改变现金或库存 |

quantity 必须为正整数，金额为整数分。销售只能因库存不足等真实事实冲突拒绝，不能因预测少于实际销售就拒绝。DEMAND_REVISED 引用截至该事件前的全部销售，data_as_of 使用真实数据截止，horizon 使用模拟时间，valid_until 使用真实时间。源 forecast_version 是不透明来源版本，事件先后以 sequence 判断；backend 另生成本地版本，不对版本字符串作字典序大小比较。

模拟器修改世界、保存订单/回执、追加对应事件和成功命令响应必须同事务。采购 ACCEPTED HTTP 回执与事件里的 action_id、external_order_id、quantity、total_minor 完全相同。backend 用 action_id+PURCHASE_ACCEPTED 唯一入账；后到的受理事件仍登记并推进游标，但不再次扣现金或增加在途。采购订单的累计已收货数量同样要持久化。

GET events 的 events、last_sequence、source_head_sequence、has_more 来自同一数据库读取快照：

- events 是 after_sequence 之后的升序页，最多100条。
- last_sequence 为本页末尾序号；空页等于请求 after_sequence。source_head_sequence 是读取时已提交的源头部序号。
- has_more=(last_sequence<source_head_sequence)。cursor 超过源头返回409 EVENT_CURSOR_AHEAD，不能悄悄回退。
- backend 全批应用事务成功才推进本地 cursor。校验到缺口则整批不应用并请求缺失范围；不能越过坏事件。收到重复事件检查内容一致，不只忽略 event_id。
- source cursor 与账本同事务；只有追平源头后才更新成功同步时间。空事件页且已追平同样是成功同步，静止世界不等于数据陈旧。
- B0 首条联调使用拉取；可选内部推送不作为前置。推送通过相同去重逻辑，但不能单凭一次推送证明已经追平源头。

## 5. 采购与不确定结果

正常 B0 采购在一次 simulator 数据库事务里完成明确 ACCEPTED 或 REJECTED。报价过期、商品/供应商不匹配、MOQ/包装或模拟现金不足可明确拒绝；backend 已批准不意味着模拟器必须受理。ACCEPTED 必须有非空订单号、正数量和正金额；REJECTED 必须有非空原因。PENDING 为可选故障/未来适配状态，不是首条模拟主线的必需功能。

网络超时与“供应商拒绝”不同。测试可在成功事务提交后丢弃/延迟响应，backend 应保留 UNKNOWN/预留，并查询原 action_id。模拟器必须保存结果，不能在重启后遗忘幂等键。

GET404 只表示查询时没有**已提交**订单，可能仍存在未提交请求，不能作为释放预留或新建 action_id 的证据。B0 使用主库查询和幂等采购事务，核对404后允许按原 action_id、原 payload、原命令键重发；即使原请求随后提交，唯一约束仍保证一次受理。原请求摘要保存在 Action.purchase_snapshot，重发不能从当前报价重新组装不同内容。真实供应商适配器必须另行声明是否支持这一保证。

协议内容冲突时保留收到的证据、显示 ACTION_EXCEPTION 并停止自动改写账本；不得将与批准数量/金额不符的回执当正常成功。明确未受理才转 FAILED 并释放资金；合法受理证据不因 Plan 过期或 Mission 取消丢弃。

## 6. SC01 的最小状态转移

创建：现金1000元，现货20，在途0，应收0，剩余需求60；采购单价10元，售价20元；固定供应商与20件包装，MOQ20。Offer 同时给出版本、CNY、lead_time_seconds=86400、真实有效起止。初始模拟时间由场景配置确定，horizon_end 为模拟开始后7天；真实创建时刻用于 data_as_of/报价有效期/预测TTL，不能将文档中的2026-09-06时间字面量用于所有运行。

采购 POST 独立产生受理事件，不消耗 advance 的脚本步骤。正常 SC01 的 advance 脚本如下：

| 脚本步骤 | 前置 | 原子变化 | 正常 SC01 源序号 |
|---|---|---|---|
| 采购40（独立 POST） | 正确报价、现金足够 | 受理、现金600、在途40 | 1 PURCHASE_ACCEPTED |
| advance 1 | 有未到货的已受理采购 | 模拟时间推进到到货ETA；按 action_id 到货，现货60 | 2 GOODS_RECEIVED |
| advance 2 | 现货至少10 | 推进模拟时间1小时；售出10，现货50、应收200、剩余需求50 | 3 SALE_RECORDED |
| advance 3 | 上一步已完成 | 推进模拟时间1小时；剩余需求替换为70 | 4 DEMAND_REVISED |
| 采购20（独立 POST） | 正确报价、现金足够 | 受理、现金400、在途20 | 5 PURCHASE_ACCEPTED |
| advance 4 | 有新增未到货的已受理采购 | 推进到新到货ETA；现货70、在途0 | 6 GOODS_RECEIVED |

到货步骤收取该阶段待收订单的实际未收数量，不把40/20硬编码成任何采购的到货量。正常验收由 backend 推荐这两个数量；非正常采购数量允许触发不同结果，模拟器不篡改订单凑出预期表。ETA 不得超出场景活动范围；同一到货阶段多笔订单按 action_id 排序，每笔一条事件，所以上表序号只适用于正常两笔采购的 SC01。

steps 可请求多个连续脚本步骤；整个命令同事务，任一步前置不满足则全部回滚，返回409 SCENARIO_STEP_BLOCKED，不消耗步骤/序号/时间。超过末尾返回409 SCENARIO_FINISHED。相同成功命令键回放原 AdvanceResult，即使当前世界已继续推进也不再次执行。条件未满足的拒绝不保存为成功幂等映射；状态满足后原键可重新尝试。GET 不自动到货，B0 的 lead_time 由显式 advance 推进到ETA来实现。

模拟时间改变不能延长真实 forecast/offer 有效期。固定预测过期时，backend 仅在源已成功追平后基于当前剩余需求重新验证并生成本地新版本；模拟器重新产生 DEMAND_REVISED 时提供新的真实 valid_until。报价首版固定，过期后不得继续采购；演示可以创建新 run，报价刷新服务后续增加。

## 7. 最小存储与恢复验收

simulation 至少保存 runs（时间/脚本位置/连续计数器）、world_state、catalog/报价版本、purchases、events、command_records；具体可用受校验 JSONB 存小场景状态，不要求每个概念单独建表。run 行锁、action_id 唯一键、事件序号唯一键和命令唯一键必须落在数据库。

| 检查 | 必须观察到的结果 |
|---|---|
| 同创建/advance 命令并发重试 | 同 run 或同推进结果，只应用一次 |
| 同 action_id 同内容与异内容 | 前者原订单，后者409；模拟现金/事件都只变化一次 |
| 受理后响应丢失 | backend 可查询回执并唯一入账 |
| simulator 重启后重试采购 | 原订单仍可查询，不生成第二笔 |
| backend 入账前重启 | 重查/补拉后账本正确，预留最终释放 |
| advance 批次中途前置失败 | 时间、状态、事件序号和步骤全部回滚 |
| 空事件页/分页/重复事件 | 游标含义明确，追平才判新鲜，重复无重复效果 |
| HTTP回执与源受理事件先后顺序互换 | 支出与在途各应用一次，到货不会造成负在途 |

以上是待实现验收，不是现有运行成绩。纯规则/fake 测试可先做；跨进程与恢复结果必须由真实 PostgreSQL、API、worker、simulation 的集成运行提供。
