# 下一阶段核心实现交付：Multiagent × Context Engineering × Rubric

实施：2026-10-02；最终验收：2026-10-03（Asia/Shanghai）。基于当前 `YH` 工作区、原 HEAD `30bed9f`，保留用户已有修改。本文记录已经写入代码的行为与验证边界；完整远期目标仍见[统一设计 v1.2](../superpowers/specs/2026-09-30-next-phase-integrated-design.md)。

## 已实现的可运行闭环

用户在现有 Mission 的“供应异常应对”中创建 Case，补充预算、数量/供应商范围及需要的七日日需求，得到等待与补购的逐日比较。选定候选只生成待确认 Plan；审批、资金预留、发送、回执和 UNKNOWN 核实继续经过原业务边界。Case 支持预算改口、过期重查、丢响应重试、新建下一事项以及显式开启后台跟进。

| 模块 | 实际交付 | 关键边界 |
|---|---|---|
| 恢复计算 | 逐日 lost demand / 到货 / 库存，整数金额，MOQ/整包/预算/现金底线，最多三家报价 | 单店、单 SKU、七日，每个 Case 最多一笔已受理应急采购；原已付款订单保留 |
| Case 持久化 | 修订、不可变证据/方案、事件、幂等命令、当前版本校验 | 绑定已存在的 Mission，所有读取/操作检查当前权限与归属 |
| 原采购链兼容 | `recovery_v1`、独立 hash、采用/审批/发送三处复核、同量不同供应商精确绑定 | 分析和模型专家没有采购审批能力；旧 Plan/hash 语义不变 |
| 自动跟进 | opt-in、持久任务、重启补调度、真实执行/收货状态、事件去重 | 不自动购买；部分到货不冒充收齐；窗口结束缺结果证据时保持未知 |
| Context Engineering | 全量已准入用户来源、来源边界、有限 TaskFrame、预算选取、原句定位、冻结 profile、调用账本、Inspector | 未识别原文保留；必需输入超预算明确失败；历史/未来输入与当前权威数据分开 |
| 模型适配 | Chat Completions / Responses，显式 reasoning effort，Responses 协议项回放，真实/未知 usage | 沿用用户模型配置；不宣称账号可用性、价格或效果已验证 |
| 受限专家协作 | evidence / impact / options，深度一、并发二、共享调用/工具/时间预算，提交后挂接到真实 Case | 解释冻结证据与计算结果，不能改业务；改口/取消/撤权停止后续发送，已发送调用继续留账 |
| Rubric v1 | D1–D6、Q1–Q6、关键失败覆盖、三态结果、精确复核绑定、完整分母、未知成本 | 与 v0 独立；模型话语不是业务真值；缺关键证据不能记为成功 |
| UI / API | Case 比较/改口/确认/恢复、来源与专家状态、Context Inspector、生成 OpenAPI/类型/代理白名单 | 确认按候选 ID，当前结果与历史 Plan 分开；失权清空可见数据 |

金标准通过可复现的数据库与纯计算测试：在库 20、七日每天需求 10、原预付 50 第五日到、现金 800/底线 500。预算 300 时 B20 支出 240、缺货 0、期末 20；预算 200 时采用等待，缺货 20。它验证计算规则，不代表模型准确率或真实门店收益。

## 验证记录

最终结果如下；过程记录见三个模块报告，复现命令与隔离库要求见[运行手册](../runbooks/next-phase-agent-recovery.md)。表中套件覆盖范围不同，不把重复运行累加为用例数。

| 检查 | 结果与范围 |
|---|---|
| Backend 全量 | **605 passed**（248.06 秒），包含三个真实浏览器用例与最后新增的禁存回归，零跳过 |
| Agent 全量 | **124 passed**，包含 PostgreSQL 测试，无跳过 |
| Posttraining 全量 | **71 passed**，包含历史 scorer 回归，无跳过 |
| 前端 Playwright | **27 passed**，覆盖恢复工作区、原任务工作区、Agent 进度、事项收集；使用可控 API 响应 |
| 真实恢复流程 | **8 项检查通过**，构建后的前端连接真实 HTTP API 与隔离 PostgreSQL |
| 静态与构建 | Nuxt typecheck / production build、OpenAPI 类型与代理同步、相关 Python Ruff、`git diff --check` 通过 |

最后的意图修复增加了同消息试算禁止、跨消息授权、记忆删除/更新的回归；模型即使提出写工具调用，Runtime 与后端 gateway 仍独立执行禁令。gateway 的三种禁存措辞均经过真实 PostgreSQL/API 校验。

已完成真实 HTTP 浏览器验收：构建后的 Nuxt → 同源代理 → FastAPI → PostgreSQL，无 API 拦截，8 项检查通过，模型调用 0、供应商调用 0。独立浏览器情景为前四日各需 10、其后三日为 0、无旧在途；验证 B20、预算改口、Plan 供应商绑定、确认页现金 560、分析/采用不创建 Action、跟进开关和刷新持久化。带原预付订单的金标准由 Case 集成测试独立验证。

本轮验证只修改 loopback 独立 `shopsteward_test` / `shopsteward_sim_test`，使用 `127.0.0.1:55434` 的测试 PostgreSQL。用户的日常数据库没有迁移。固定测试凭据仅用于隔离 HTTP 夹具，未使用用户模型密钥；测试输出与私有连接配置保留在被忽略的 `var/`，不加入项目源文件。

审查中发现并修复的实际问题包括：同数量报价在旧 UI 中串金额、修订后历史 Plan ID 阻止新采用、终态后无法新建 Case、重查没有更新来源、Chat reasoning effort 未发送、缺关键预算证据仍判成功、只试算误写以及过宽意图禁令误拦合法修订、专家取消/撤权后的发送边界。各问题使用对应层级回归验证。

遇到的环境/夹具问题也保留记录：系统 pytest 临时目录无权限（改为仓库内 basetemp）；不同 PostgreSQL 套件并发清理全局队列相互干扰（改为顺序运行）；新增 unit/integration 测试同名导致收集冲突（重命名）；最初浏览器复用了缺历史 Action 的 Inbound 夹具，被既有读取完整性校验拒绝（改为独立完整浏览器情景）；Windows Selector 测试循环不支持 Node 子进程（仅浏览器验收改用 Proactor）。旧 API 路由/能力断言也已同步新增契约。没有通过放宽生产校验让夹具通过。

本机另一版本 pnpm 的隐式安装检查曾因 esbuild 脚本策略停止，未改变依赖或审批构建脚本；移除了该命令自动写入的占位配置，并直接使用已安装的 Playwright CLI 完成最终 27 项验证。项目仍固定 `pnpm@10.17.1`。

## 未包含的完整设计目标

以下是明确的后续工作，不能把本轮核心闭环描述为整个研究设计全部完成：

- **自由文本事项到 Case 的自动路由**：WorkItem 的自然语言分类/处理者与 canonical Case 接入尚未实现；当前 Case 从现有 Mission 进入。
- **文档驱动的供应异常推断**：未将 PDF 供应通知、适用性 DSL、文档版本依赖及 ETA/报价变更模拟事件接入可执行采购来源。目前使用权威结构化业务投影和显式情景。
- **通用语义压缩与记忆学习**：TaskFrame 有限规则与原话回退已实现，任意语义提取/摘要重建、learned retention、自动 Skill 学习没有实验证据。
- **完整协作策略实验**：2026-10-08 已接入 R0–R3 四种可强制切换的策略、一次定向补查、代码合并与分歧处理、按角色冻结模型，以及把运行结果导出为可评分轨迹的适配函数（见[运行手册](../runbooks/next-phase-agent-recovery.md)）；仅用模拟模型和隔离 PostgreSQL 验证。仍未做：LLM 协调器、single+reviewer 策略、文档检索类专家工具、OPS 数据集与任何真实模型对照，因此没有“哪种策略更好”的结论。
- **业务结果 oracle 与研究数据**：真实 lost-demand 结果归因、完整 trace/业务观察自动导出、独立 CE48/OPS48 锁定集、双人人工校准、付费模型/成本/统计比较待做。随附九个开发示例、32 条 agent 示例标注、零个 locked test 不能充当模型成绩。

## 文档与代码入口

- [启用、用户流程、模型参数与复现步骤](../runbooks/next-phase-agent-recovery.md)
- [Case / 求解器 / 审批与跟进记录](next-phase-cases-implementation.md)
- [Context / 模型 / 受限专家记录](next-phase-context-implementation.md)
- [新版 rubric 交付与关键证据修复](next-phase-rubric-implementation.md)
- [实施计划与逐项状态](../superpowers/plans/2026-10-02-next-phase-implementation.md)
- 核心实现：`backend/app/operations_cases/`、`backend/app/planning/recovery/`、`agent/src/shopsteward_agent/context/`、`agent/src/shopsteward_agent/cases/`、`posttraining/src/shopsteward_pt/case_eval/`。

课程展示与简历可以据此陈述已经实现的工程机制、合成情景的具体计算结果及测试证据。成功率提升、成本下降、真实经营收益与“独立研究结论”要等相应实验完成后再写。

代码尚未自动提交、推送或部署。日常环境使用前需要确认连接配置、应用新迁移并重启相关服务。
