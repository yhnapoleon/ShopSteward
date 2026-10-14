# 前端工作区重构设计（2026-10）

本文是前端重构的实施依据，供实现者（人或 Agent）逐项执行。读者可以不了解之前的对话。基线为 main `87eb193`（本机标签 `qa-baseline-20261014`）；所有改动在个人分支 `jeffrey` 上按阶段分别提交，每一阶段都能单独回退。

## 0. 目的与边界

**要解决的问题。** 2026-10-14 的真实浏览器走查证明：业务数字正确、确认护栏有效、重启不重复采购；但店主看到的是后端的形态——原始日志、UUID、状态码、"分"为单位的金额；同一项委托有两套工作区（任务工作区 / 事项工作区）互相跳转；顶部导航和底部浮条重复；没有模型时建立委托的入口消失；后端停机被误报为"身份未连接"；Agent 的跨会话记忆没有任何界面。

**目标用户。** 课程评审与演示观众为主，但要达到真实店主可用的周到程度：每个数字可追溯，每个动作有反馈，没有需要翻译的内部术语。

**本轮做什么。** 只改前端（`frontend/`）。后端不改；若发现某个效果必须改后端，先记录在第 16 节，不实现。预测面板、时间语义、后端文案结构化按既定决定暂不处理。

**不做什么。** 不动同学分支（`YH`）涉及的文件区域（第 14 节）；不安装新的组件库；不引入远程字体；不把任何模拟逻辑放进前端；不让任何组件绕过后端直接改金额或发起采购。

## 1. 设计判断

一句话：**重构-保留型的经营工作区，面向演示观众，沿用现有暖光磨砂语言；动效克制但在"系统在动"的时刻明确。** 参数：布局变化 5 / 动效 5 / 密度 5（1–10）。

视觉遵循 [`../style.md`](../style.md)，动效遵循 Emil Kowalski 的设计工程规则（本机 skill `emil-design-eng`）。两者冲突时，以 style.md 的材质与排版为准，以 Emil 的动效规则为准。

三条总原则：
1. **先回答店主的三个问题**：要我拍板什么 → 系统在替我盯什么 → 店里现在什么情况。页面结构按这个顺序排。
2. **对话负责意图和过程，卡片负责结果和动作。** 店主的每个动作（确认、改选、暂停、结束、纠正）只在卡片上发生；聊天里的话永远不触发采购。
3. **后端事实到了前端必须变成店主的语言。** 任何事件、状态、金额都经过翻译层；原始标识只在"可追溯依据"的折叠区里出现。

## 2. 用户旅程（逐步）

以 SC-01 示例店铺为例，每一步写明店主看到什么、想什么、点什么。实现时逐步对照。

| # | 店主的处境 | 看到 | 想 | 点 | 系统反馈 |
|---|---|---|---|---|---|
| 1 | 第一次进入 | 今日页：标题"今天的经营安排"，右栏现金 ¥1,000 / 在库 20 / 在途 0 / 待结算 ¥0；主区一张"开始"卡：三步说明（试算→委托→逐笔确认） | 先看看买多少合适 | 「先试算补货」 | 试算弹层，默认 0/20/40/80 与底线 ¥300 |
| 2 | 看试算结果 | 事项工作区：左栏结果卡（推荐 40 件 · 支出 ¥400 · 余 ¥600 · 缺口 0）与四候选表；委托条件卡（现金底线、检查频率）；右栏对话（无模型时写明"助手未启用，仍可用卡片操作"） | 可以，交给系统盯着 | 「按这些条件开始跟进」 | 标题下状态徽章变为"持续跟进中"；同步条显示"后台正在生成方案" |
| 3 | 等方案 | 20 秒内方案卡出现：建议补 40 件，三项影响数字，候选切换，依据链接 | 为什么是 40 | 「查看依据」 | 依据弹层：需求假设 60、周期、底线、来源 |
| 4 | 决定买 | 「核对 40 件采购」→ 确认弹层（商品/供应商、数量×单价、支出、到货、现金变化、缺货） | 没问题 | 「确认采购 40 件 · ¥400」 | 徽章"正在核实采购"；采购单卡出现（编号、提交时间、预计到货）；回执后徽章"等待到货" |
| 5 | 过了一天（演示：过一天） | 同步条"后台正在同步"→ 到货卡：在库 20→60，在途 40→0；时间线新增"到货已核实 40 件" | 到了 | — | 徽章"持续跟进中" |
| 6 | 销售发生 | 事实卡更新：在库 50、待结算 ¥200；时间线"售出 10 件，待结算 +¥200" | 待结算不是现金 | — | 右栏事实卡上"待结算 · 还未到账"保持 |
| 7 | 需求上修 | 变化卡：剩余需求 50→70；已执行 40 件保留；这次只补缺口 20；新方案 v5 建议补 20 件 | 为什么又要买 | 看变化卡 | 候选 0/20，40 与 80 标注"低于现金底线" |
| 8 | 确认追加 | 同第 4 步 | — | 「确认采购 20 件 · ¥200」 | 最终 ¥400 / 70 / 0 / ¥200；徽章"持续跟进中" |
| 9 | 问 Agent（有模型时） | 右栏 Agent 对话；发送后工具进度逐条亮起（读看板→读方案→试算），对应左栏卡片短暂高亮；结果卡落到左栏，对话里一行回执 | 它真的在看我的数据 | 输入"少买一点先试算" | 试算结果卡（未修改方案）；若要求修订，新方案仍待确认 |
| 10 | 说出偏好（有模型时） | "以后现金至少留 500" → 对话回执"已记住"，顶栏记忆入口出现小点 | 下次不用再说 | 顶栏「记忆」 | 记忆面板：关于你 / 经营笔记 / 技能，可纠正、删除 |
| 11 | 整理报价 | 报价事项：上传 CSV → 结果版本 1；纠正第 3 行包装数 → 版本 2；表头徽章"沿用了你的整理规则 v1（来自事项 A）" | 它记得我上次怎么整理的 | 「下载此版本 CSV」 | 文件含来源与哈希 |
| 12 | 回看 | 经营记录：经营变化（分组后的事件）、我的决定（只有用户动作，分页取全）、经营账本 | 一眼看懂发生了什么 | — | 例行检查折叠为"N 次例行检查，方案无变化" |
| 13 | 服务出问题 | 后端不可达：卡片"后端暂时无法连接，正在重试"，保留上次数据；恢复后自动继续 | 不是我的问题 | — | 不显示"先连接后端用户身份" |

## 3. 信息架构与导航

### 3.1 视图

| 视图 | 路由 | 内容 |
|---|---|---|
| 今日 | `?view=today` | 第 5 节 |
| 跟进 | `?view=following` | 当前店铺全部事项（进行中在前，已结束折叠），每项一行：标题、状态徽章、下一次检查/预计到货、最近一次变化；页首放提醒摘要 |
| 记录 | `?view=journal` | 三个标签：经营变化 / 我的决定 / 经营账本（第 7 节翻译后） |
| 事项工作区 | `?view=work&item=…&store=…[&panel=agent]` | 第 4 节 |
| 经营概览 | `?view=overview` | 不改 |
| 文档中心 | `?view=documents` | 只改一句说明文案 |
| 任务工作区 | `?view=task&mission=…` | 保留为兼容入口，界面上不再链接 |

### 3.2 导航去重

- 顶部导航：品牌、三个视图（今日/跟进/记录）、Agent 入口、**记忆入口（新）**、设置、店铺切换。
- 桌面底部浮条（`.workspace-dock`）在普通模式下不再显示；它的"经营概览"入口由右栏"店铺此刻"卡和事实条承担。
- 演示模式下，底部出现**演示条**（第 10 节）。
- 移动端底部导航保持三项。

### 3.3 入口规则

- 「先试算补货」与「交给我一件事」在今日/跟进页头常驻，两者永远并存；事项助手不可用时「交给我一件事」仍可保存原话，并在卡片内写明。
- 「交给我一件事」弹层（GoalDeck）同时提供：自然语言输入（WorkIntake）与结构化入口「按当前条件开始备货跟进」（startMission）。右下角两张装饰卡改为真正可点的两个入口（备货跟进 / 报价整理），或删除。
- 顶栏「Agent 工作区」按钮进入当前委托所属事项的工作区并打开对话面（`panel=agent`），不再跳到无对话的页面。

## 4. 事项工作区（统一容器）

事项（work item）是唯一容器；备货委托是一种事项。组件 `components/space/SpaceWorkspace.vue` 替换 `WorkWorkspace.vue` 内部对 `TaskWorkspace` 的嵌套使用。`TaskWorkspace.vue` 本身不修改、不删除（第 14 节）。

### 4.1 页头

返回链接；眉标"备货委托 · SC01 sample product"或"我的事项"；标题（委托目标或事项标题）；状态徽章（第 6 节词汇）；次要动作用文字链接：委托详情、暂停/恢复、结束（仅审批角色）。

### 4.2 左栏 = 执行面（按出现顺序）

1. **同步条 `SyncStrip`**：一行，含经营时点、数据同步时间；当 `s.refreshing` 或"推进事件后状态版本未变"时显示脉冲点与"后台正在同步"。
2. **需要处理 `IssueCard`**：沿用现有 `issue` 语义（confirmation/unknown/stale/expired/changed/offline），文案与按钮与现有一致。
3. **变化卡 `ChangeCard`**：方案版本变化时显示。内容：前后建议数量、剩余需求前后值、已执行采购件数（保留）、本次只补的缺口、触发原因（需求修订/到货/销售/依据更新）。数据来自当前方案与前一版方案（`/api/v1/missions/{id}/plans?limit=2`）及账本最近一条 `DEMAND_REVISED`。
4. **方案卡**：复用现有 `DecisionCard`（不改它）；无待确认方案时显示 `OutcomeCard`（等待到货 / 暂无新决定 / 已结束），样式沿用 `.task-outcome`。
5. **采购与到货 `OrdersCard`**：每笔采购单一行：数量 · 金额 · 状态（第 6 节词汇）· 预计到货 · 到货进度条；点开查看编号与回执。替代弹层式回执，弹层保留作为详情。
6. **经营事实 `FactsCard`**：现金/在库/在途/待结算 + 同步时间 + "查看来源"。保留 `data-testid="cash|stock|inbound|receivables"`。
7. **跟进安排**：复用现有 `FollowUpCard`（不改它）。
8. **事项内容**：试算结果（`WorkResult`）、委托条件卡（mission_request → 接受）、澄清卡（`question`，用 `ClarificationCard` 呈现为结构化输入：若问题含"预算/日期/数量/供应商"等词，展示对应快捷字段；否则纯文本）、报价工作区（`QuotationWorkspace`）。
9. **时间线 `TimelineCard`**：第 7 节翻译后的事件，默认 6 条，例行检查折叠，"历次方案与决定"折叠区沿用现有逻辑（读 `/plans`）。
10. 提醒链接、结束委托、页脚说明。

### 4.3 右栏 = 对话面 `ConversationPanel`

一个分段控件切换两条对话：
- **Agent 对话**（委托绑定的 Mission Agent）：复用 `AgentWorkspace.vue`（不改它），它自带运行状态、工具过程、业务成果、对话。
- **事项对话**（事项处理者）：复用 `WorkConversation.vue`。

默认标签：事项有委托且 `session.agentEnabled` 时为 Agent 对话；否则事项对话。两者都保持挂载（`v-show`），切换不丢草稿。`panel=agent` 查询参数打开 Agent 对话。无模型时对应标签内保留现有"暂未启用"说明，输入框禁用。

### 4.4 过程联动

Agent 工具完成（`useAgentConversation().s.activity`）时，左栏对应卡片短暂高亮约 1.1 秒（沿用 `.task-target.target-active` 的做法，映射：facts→事实卡，plan→方案卡，mission→页头，history→时间线，receipt→采购卡）。首次加载与历史回看不重播。

### 4.5 移动端

≤820px：顶部分段「执行 / 对话」，默认执行；事实摘要前置；输入区不被固定元素遮挡。

## 5. 今日页

顺序固定：
1. 页头：标题、副标题、两个入口按钮。
2. **需要你拍板**：只放需要动作的卡（待确认方案、需要补充、需要处理、确认结果待查）。计数徽章只数这些。
3. **系统在盯 `WatchList`**：其余进行中的事项，每项一行（标题、状态徽章、下一次检查或预计到货、最近变化一句话）；没有时显示"暂无跟进中的事项"。
4. **已结束的委托**：折叠，沿用现有。
5. 提醒链接（有 OPEN 提醒时）。
6. 资料与简报：三张入口卡沿用。
7. 七日预测面板：保持现有组件与 DOM，位置移到资料之后；不改其内部。
8. 右栏：店铺此刻（`BusinessFacts`，不改）+ **服务状态 `ServiceStatus`**（第 11 节）。

空店铺（无事项、无委托）时主区显示一张"开始"卡：三步说明 + 两个入口。

## 6. 词汇与状态模型

### 6.1 词汇表（界面只用这些词）

| 词 | 指 | 不再使用 |
|---|---|---|
| 事项 | 店主交给系统的一件事（容器） | 任务、Work |
| 备货委托 | 持续跟进某商品备货的事项 | 委托、Mission、活动备货跟进 |
| 方案 | 一次检查给出的候选比较与建议 | Plan、计划 |
| 采购单 | 店主确认后发出的一笔采购 | 动作、Action、订单 |
| 到货 | 采购单的实际收货 | 入库、inbound |
| 提醒 | 系统发现的风险 | 警报、alert |
| 检查 | 后台按计划或事件触发的一次评估 | 周期检查、job |
| 记忆 | Agent 跨会话记住的内容 | 知识、knowledge |
| 技能 | 可复用的做法（记忆的一类） | skill |

### 6.2 状态徽章（`utils/glossary.ts`）

输入：事项状态、委托状态、方案状态、未决采购单、`business.code`。输出：`{ label, tone }`。优先级从上到下取第一个命中：

| 条件 | 标签 | tone |
|---|---|---|
| 确认结果待查 / 采购结果 UNKNOWN | 需要处理 | amber |
| 方案待确认且可确认 | 需要你拍板 | amber |
| 事项 WAITING_INPUT | 需要你补充 | amber |
| 采购单 QUEUED/EXECUTING | 正在核实采购 | blue |
| 有在途且无待确认方案 | 等待到货 | blue |
| 事项 PROCESSING | 正在处理 | blue |
| 委托 PAUSED | 已暂停 | gray |
| 委托 COMPLETED/CANCELLED 或事项 COMPLETED | 已结束 | gray |
| 事项 CANCELLED | 已停止 | gray |
| 事项 RESULT_READY 且无委托 | 结果已出 | green |
| 委托 ACTIVE | 持续跟进中 | green |

后端 `business.label` 只作为无法匹配时的回退。

### 6.3 标识显示

店铺：演示模式下显示"示例店铺 · 10/14 15:26"（创建时点），其他模式显示尾号。供应商：有目录名称用名称，否则"供应商 001"（从 `supplier_001` 派生）。UUID、哈希、状态版本只出现在折叠的"可追溯依据"里。

## 7. 时间线翻译规则（`utils/timeline.ts`）

`describeEvent(entry: TimelineEntry) → { title, detail?, tone, icon, routine, references }`。解析失败时 `title = summary` 原样。

| type | summary 形态 | 显示 |
|---|---|---|
| MISSION_CREATED | `Mission created` | 建立备货委托 |
| MISSION_CONTROLLED | `pause` / `resume` / `complete` | 已暂停主动跟进 / 恢复主动跟进 / 结束委托（用户动作） |
| PLAN_CREATED | `推荐采购{n}件；预计支出{分}分，采购后可用现金{分}分，剩余缺口{n}件。` 或 `当前候选均不满足采购约束，未提出采购。` | 新方案：建议补 {n} 件 · 支出 ¥{元} · 采购后现金 ¥{元} · 缺口 {n} 件 / 新方案：没有可行的采购 |
| PLAN_DECIDED | `approve` / `reject` | 你确认了采购 / 你选择本轮不采购（用户动作） |
| CHECK_REQUESTED | `{reason}（任务{id}）` | 你要求重新检查 |
| CHECK_COMPLETED | `检查{STATUS}：{summary}（任务{id}）`；summary ∈ `Candidate comparison saved` / `Existing valid plan reused` / `Mission inactive or an action is pending` / `DATA_STALE` / 其他 | 检查完成：已生成新方案 / 方案无变化（routine） / 有采购待核实，本次跳过 / 数据未更新，未能检查 / 原文；STATUS 只影响 tone：HEALTHY green、ANOMALY amber（含"（这是风险判断，非系统故障）"的 detail）、INCONCLUSIVE gray、SKIPPED gray |
| ALERT_OPENED / ALERT_ESCALATED | `{TYPE}：{summary}` | 发现{提醒名}：{summary} ；TYPE 映射 STOCKOUT_RISK 缺货风险、CASH_CONSTRAINT 现金约束、ACTION_EXCEPTION 采购需核实、DATA_STALE 数据未更新 |
| ALERT_RESOLVED | `{TYPE}：状态版本{n}的新鲜输入确认风险已解除。` | {提醒名}已解除（routine） |
| ALERT_ACKNOWLEDGED | `已知晓{TYPE}；风险尚未解除。` | 你已知晓{提醒名}（用户动作） |
| ACTION_EXECUTING | `采购已登记发送，资金暂时预留。` | 采购单已发出，资金已预留 |
| ACTION_SUCCEEDED | `SUCCEEDED` | 供应商已受理采购 |
| ACTION_UNKNOWN / FAILED / CANCELLED / STALE | 原因或状态 | 采购结果待核实 / 采购未成功 / 采购已取消 / 原方案失效 |
| 其他 | — | summary 原样，tone gray |

分组：连续的 `routine` 事件折叠为一行"{n} 次例行检查，方案无变化 · 最近 {时间}"，可展开。金额显示用 `money()`（分→元）。用户动作用人物图标，系统事件用圆点。简报（`briefing()`）与经营记录都使用同一翻译。

## 8. 记忆面板

入口：顶栏图标按钮「记忆」（移动端在设置旁）。形态：右侧抽屉（原生 `dialog`，从右侧滑入，`--ease-drawer`，≤300ms）。

数据：`GET /api/v1/stores/{store_id}/agent-knowledge` → `items[]: { id, kind: USER|NOTES|SKILL, task_type, version, entries[]: { id, content, required_tools } }`。写入：`POST` 同路径，body `{ kind, task_type, expected_version, operation: add|replace|remove, entry_id?, content?, required_tools? }`，带幂等键（`api()` 第四参数）。写入接口在后端 Agent 未启用时可能返回 503：此时面板只读，并说明"修改记忆需要启用 Agent"。

分区与内容：
- **关于你**（USER）：每条一卡，正文 + 「纠正」（内联编辑后 replace）+ 「删除」（remove，二次确认）。
- **经营笔记**（NOTES）：同上。
- **技能**（SKILL）：标题取内容首句，副行"适用：{task_type} · 依赖工具：{required_tools 翻译}"；「停用」= remove。

空态：解释记忆如何形成（"在对话里说'以后现金至少留 500'，Agent 会记下来；报价纠正会形成整理规则"）。

形成提示：`useAgentConversation` 观察到工具 `memory_edit` 成功完成时，右栏对话内出现一行回执"已记住一条偏好"，顶栏记忆图标显示小点，面板重新读取。

来源与时间：后端条目没有逐条时间和来源字段，面板不伪造；只显示版本号。补字段列入第 16 节。

## 9. 动态 surfaces（A2UI 的前端层）

目的：让 Agent 的结构化产物以"组件组合"的形式动态呈现，同时保证数值来自后端、组件不能发起审批。

- `app/surfaces/catalog.ts`：受信组件目录，首批：`MetricRow`（指标组）、`PlanComparison`（候选表）、`EvidenceList`（依据列表）、`DemandChange`（需求变化）、`QuoteTable`（报价表）、`NextStep`（下一步入口，只能指向既有弹层/路由）、`ClarificationForm`（澄清表单）、`Text`（Markdown 正文，经现有 `MarkdownMessage` 净化）。
- `app/surfaces/types.ts`：`Surface = { version: 1, blocks: Block[] }`，`Block = { component: keyof catalog, props }`。限额：≤24 块；props 只允许目录声明的字段；未知组件整块降级为 `Text`；不允许 HTML、URL 以外的资源。
- `app/surfaces/derive.ts`：从现有结构化结果确定性地生成 surface：`WorkResult`（kind、columns/rows、assumptions、references、calculation）、`BusinessOutcome`（before/after 比较）。这保证今天没有后端改动也能工作；将来后端若在结果里附带 `surface` 字段，渲染器先校验再使用。
- `components/surfaces/SurfaceRenderer.vue`：按 blocks 渲染，进入时 40–60ms 阶梯淡入（仅首次出现，不在后台刷新时重播）。
- 使用位置：事项结果卡、对话中的结果回执、Agent 业务成果。

## 10. 演示模式

`useDemoMode()`：`localStorage` 开关，设置弹层里一个开关"演示模式"，也接受 `?demo=1`。

开启后：
- 底部出现**演示条**：「过一天 ▶」（即现有 advance：调用后轮询看板直到 `state_version` 变化或 90 秒，期间同步条脉冲；完成后用最近一条账本条目生成一句提示，如"到货已核实：在库 +40"）、「新建示例店铺」、「切换店铺」、「经营概览」。
- 页面上的联调徽章改为"演示 · 合成数据"；店铺显示名用"示例店铺 · {创建时点}"；供应商用派生名称。
- 不改变任何业务规则，不改时钟，不预设数据。

关闭时：保留现有"联调控制"弹层与顶部徽章（测试依赖），底部浮条不显示。

## 11. 服务状态与同步

- `server/api/health.get.ts`（新）：请求后端 `/health/ready`（无需凭证，3 秒超时），返回 `{ backend: 'ok' | 'unreachable' }`。
- `composables/useBackendHealth.ts`（新）：当 `session.authenticated === false` 或 `s.connected === false` 时每 5 秒探测；从不可达恢复后调用 `shop.init()`。
- 今日页：后端不可达时显示"后端暂时无法连接，正在重试"卡（保留上次数据与时间），不显示"先连接后端用户身份"。只有 health 正常且身份确实无效时才显示身份卡。
- `ServiceStatus` 右栏小卡：业务接口（connected）、事项助手（`work.s.processorAvailable`）、Agent（`session.agentEnabled`）、预测服务（对 `/forecast/model` 的一次探测，按店铺缓存）。每项一个点 + 文字，不用颜色单独表达。
- `SyncStrip`（第 4.2 节）在今日页右栏也显示一行。

## 12. 视觉与动效规则

- 材质、字号、间距、圆角、按钮层级：按 style.md 第 2–5 节；新组件复用 `.glass`、`.tag`、`.primary`、`.secondary`、`.text-link`、`.detail-row`、`.section-label`、`.notice`、`.source-note`。
- 新样式写在 `app/assets/css/space.css`（新文件，在 `nuxt.config.ts` 注册）；不修改 `tasks.css`、`work.css`、`shop.css` 的既有规则；需要覆盖时在 space.css 用更具体的选择器。
- 动效：只动 `transform`/`opacity`；进入用 `cubic-bezier(0.23, 1, 0.32, 1)`，抽屉用 `cubic-bezier(0.32, 0.72, 0, 1)`；UI 动效 ≤300ms；可按压元素 `:active` 缩放 0.97；没有 `scale(0)` 入场；键盘触发的切换不动画；`prefers-reduced-motion` 下只保留透明度变化。
- 只在三类时刻使用阶梯入场：surface 首次渲染、过一天后的事实更新、记忆形成；后台轮询刷新不重播任何入场。
- 状态永远同时有文字；不用颜色单独表达。
- 英文：所有新字符串写入 `app/i18n/en.json`（见第 14 节位置规则），`node scripts/check-i18n.mjs` 必须通过。

## 13. 实施分期与提交

每阶段一个提交；提交信息用英文祈使句，正文列出改动与验证结果。阶段之间先跑第 15 节验证。

| 阶段 | 内容 | 新文件 | 触及的既有文件 |
|---|---|---|---|
| C1 修复 | 健康探测与后端不可达卡；我的决定分页取全；GoalDeck 双入口；Agent 入口进入对话面；时间线翻译接入记录/简报/任务记录；账本时间回退 `occurred_at`；手机端设置按钮与 Agent 入口不重叠；`.gitignore` 加 `backend/var/`；文档中心说明改为"检索由 Agent 工具使用，本页只管理原件" | `server/api/health.get.ts`、`composables/useBackendHealth.ts`、`composables/useDecisionRecords.ts`、`utils/timeline.ts`、`utils/glossary.ts`、`assets/css/space.css` | `pages/index.vue`（允许区域）、`components/GoalDeck.vue`、`components/WorkWorkspace.vue`、`components/DocumentCenter.vue`、`i18n/en.json`（顶部）、`nuxt.config.ts`、`.gitignore` |
| C2 统一工作区 | `SpaceWorkspace` 及左栏卡片、`ConversationPanel`、今日页重排（需要你拍板 / 系统在盯）、跟进页、状态徽章全面接入、导航去重 | `components/space/*.vue`、`composables/useSpace.ts` | `WorkWorkspace.vue`、`WorkCard.vue`、`pages/index.vue`（允许区域） |
| C3 记忆 | 记忆面板、顶栏入口、形成提示、报价规则复用徽章 | `composables/useAgentKnowledge.ts`、`components/MemoryPanel.vue` | `pages/index.vue`（顶栏区域）、`QuotationWorkspace.vue`、`WorkConversation.vue` |
| C4 动态 | surfaces 目录/类型/派生/渲染器；演示模式与演示条；过一天同步反馈；过程联动高亮 | `app/surfaces/*`、`components/surfaces/*`、`composables/useDemoMode.ts`、`components/PresenterBar.vue` | `WorkResult.vue`、`AgentOutcome` 的使用处（不改 AgentOutcome 本身）、`pages/index.vue`（设置弹层允许区域） |
| C5 打磨 | 动效审查（Before/After 表）、英文全覆盖、手机、`style.md` 增补一节、`frontend/README.md` 增补入口说明 | — | `style.md`、`frontend/README.md`（只追加新节） |

## 14. 冲突禁区与编辑规则

同学分支 `YH` 尚未合并，以下规则保证将来合并无冲突或只有易解冲突。

**禁止修改的文件**（YH 改过）：`components/TaskWorkspace.vue`、`AgentWorkspace.vue`、`DecisionCard.vue`、`FollowUpCard.vue`、`TaskCard.vue`、`composables/useShop.ts`、`useTaskPresentation.ts`、`utils/plans.ts`、`utils/presentation.ts`、`utils/api.ts`、`types/models.ts`、`types/backend.d.ts`、`server/utils/backend-routes.ts`、`tests/task-workspace.spec.ts`。需要的新逻辑一律放在新文件；需要新的展示辅助函数写在 `utils/glossary.ts`、`utils/timeline.ts` 等新文件。

**受限修改**：
- `pages/index.vue`：只允许改第 85–200 行（函数区，不含第 1–60 行）、第 300–350 行（计算属性与 briefing）、第 351–500 行（头部与导航）、第 556–930 行（今日/跟进/记录主体、浮条、移动导航）、第 1258–1390 行（设置弹层内部）。禁止改第 1–60、500–555、957–1135、1136–1210、1477–1549 行。
- `server/api/session.get.ts`：只允许改 `catch` 分支。
- `i18n/en.json`：新键一律插在文件开头 `{` 之后，不追加到末尾。
- `.gitignore`：只在文件末尾追加。
- `nuxt.config.ts`：只在 `css` 数组追加。

**保持不变的测试锚点**：`data-testid="cash|stock|inbound|receivables|forecast-total|overview-*"`，aria 名称"追问这项备货任务""发送卡片内消息""查看Agent工作区""联调控制 · 合成数据""创建新的 SC-01 场景""七日需求预测""任务对话"，类名 `.agent-run-status`、`.agent-stream-note`、`.task-workspace`、`.work-detail`、`.work-card`、`.quotation-workspace`、`.plan-change-receipt`、`[data-invocation]`、`[data-work-id]`，按钮文字"核对 {n} 件采购""确认采购 {n} 件 · ¥…""建议补货 {n} 件"。

**后端**：不修改任何 `backend/`、`agent/` 文件。

## 15. 验证清单（每阶段）

在 `frontend/` 下：
1. `corepack pnpm exec nuxt typecheck`
2. `node scripts/check-i18n.mjs`
3. `node scripts/generate-api.mjs --check`（必须无差异：本轮不改契约）
4. `NUXT_TELEMETRY_DISABLED=1 corepack pnpm exec nuxt build`
5. `FRONTEND_URL=http://127.0.0.1:3000 corepack pnpm exec playwright test`（对比基线结果，新增失败必须解释或修复）
6. 受控 Agent 浏览器链（仓库根，使用专用测试库）：`OUTCOMES_BROWSER_E2E=true PROGRESS_BROWSER_E2E=true WORK_BROWSER_E2E=true` 运行 `backend/tests/integration/test_agent_outcomes_browser.py test_agent_progress_browser.py test_work_browser.py`
7. 真实浏览器截图：今日、事项工作区（桌面 1440 与手机 390）、记忆面板、演示条；对照第 2 节旅程逐步点一遍。
8. `git diff --stat` 核对没有触碰第 14 节禁止文件。

## 16. 需要后端配合的最小项（本轮不做）

1. 记忆条目补 `created_at` 与 `source`（来源对话/任务），面板才能显示"来源可追溯"。
2. 时间线条目增加结构化 `params`（数量、金额、版本），前端翻译层可以去掉正则解析。
3. 账本 `DEMAND_REVISED` 条目带前后需求值（现为四项变化全 0）。
4. 文档上传存储根默认指向仓库外，并在 `.gitignore` 覆盖 `backend/var/`（本轮只做后者）。
5. 事项处理者结果附带可选 `surface` 字段（按第 9 节契约），实现真正的 Agent 选组件。
