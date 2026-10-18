# ShopSteward Memory / Skill / Workflow Evolution Implementation Plan

> **For agentic workers:** 实施时使用 `superpowers:executing-plans` 按任务执行；只有用户选择并行代理方法时才使用 `superpowers:subagent-driven-development`。复选框记录完整计划的完成情况；当前已开始实施，第一批 Skill 闭环见下方状态及独立实施记录。

**2026-10-03 实施状态：** 已实现 Skill 的持久化/事件采集、去重计数、有界提炼、静态质量卡、离线评估登记、版本准入、会话检索、撤销隔离、前端管理及在线观察基础设施。已有真实数据库、API、模拟模型与浏览器回归；没有用模拟测试成绩冒充真实模型或经营收益。

**尚未完成整个计划：** 批量经营回放适配、首批真实模型与双人校准、全系统时间消融、自动定期复评、Workflow DSL、A2UI 与跨资产演化仍为后续任务。现有任务的部分验收项超出首批闭环，因此不将整项复选框一概勾选为完成。

运行和验证记录：[功能运行说明](../../runbooks/skill-learning.md)、[实施与审查记录](../../reports/memory-evolution-progress.md)。

**Goal:** 建立从经营轨迹到可验证 Skill、可恢复 Workflow 和可组合 UI 的持续学习闭环。

**Architecture:** 业务事务写 outbox，后台归并 Episode 与结果；学习 worker 产生类型化候选，经验证和激活策略进入版本化资产库。在线检索和有界执行器通过现有业务 gateway 工作，前端使用受信组件目录承载 A2UI。

**Tech Stack:** Python >=3.11（当前开发 3.12）、FastAPI、SQLAlchemy 2、PostgreSQL JSONB、Pydantic、现有 LangGraph/持久调度、Nuxt 4/Vue 3/TypeScript、pytest、Playwright。pnpm 保持仓库 10.17.1。A2UI web_core 的准确包版本在 Task 11 验证后锁定，不在计划中虚构已安装版本。

**Spec:** [完整设计与论文研究](../specs/2026-10-03-memory-skill-workflow-evolution-design.md)。所有任务实施前必须读该文的对象、范围与发布门槛。

**Quality spec:** [Skill 质量检验与 Rubric v1](../specs/2026-10-03-skill-quality-rubric.md)。新增/修改/合并的每个 Skill revision 先检验后激活，并在启用后持续评估。

## Global Constraints

- 计划针对当前 `ShopSteward` 工作区，不针对 `ShopSteward-forecast` 或 storage 中的旧 checkout；保留用户已有未提交改动。
- 原 USER/NOTES/SKILL 显式编辑语义不变，自动学习候选单独存储。
- 来源域 simulation/observed 分离；principal_id/store_id 必须来自当前认证与业务归属，不能信任模型字段。
- 当前用户约束、权限和硬业务规则不能被学习产物覆盖；生成器没有采购审批能力。
- 每次有效操作按 Episode 计数，聊天、轮询、重试不增加计数；第 10 次触发分类整理，不保证产生可激活 Skill。
- 冷启动程序候选：同类至少 3 个独立 Episode、至少 2 个经营日期；明确纠错可单独产生教训候选。
- 日提炼批次≤3，每批候选≤3；生成调用≤2，JSON 修复≤1；每批输入≤12000 token、输出合计≤4000 token。
- 检索最多 3 个 Skill、1800 token；Workflow≤12 节点、节点重试≤2；UI≤50 节点、深度≤8、描述≤64 KB。
- 硬规则/证据检查全通过；候选至少 20 个适用独立场景回放；样本或统计证据不足保持 SHADOW。
- H1–H6 全 pass、S1–S6 初始各≥3/4，S5 须有独立对照；unknown 和高平均分均不能绕过 gate。报告绑定精确 revision/content/rubric/dataset/model/tool/business-rule/policy/evidence 版本。
- 新迁移先应用到隔离测试库；当前观察到 head=`0015_operations_cases`，实施时先重新查询并选择无冲突 revision ID。
- 不为此安装第二套队列或图数据库；首版不训练模型，不执行生成 Python/JS。

## Review Focus

1. 同一次业务意图跨 Run/修订/响应重试，计数和副作用只能发生一次：Task 1、2、9。
2. 迟到回执、部分收货、未知执行不能学成成功，未来信息不能进入过去评测：Task 2、7、12。
3. 用户删除/禁止推断/撤权后，旧候选、缓存、UI 和已开始 Run 不能继续沿用：Task 5、6、8、11。
4. 新版 Skill 发布与运行中的旧版本并发，既要可重复恢复又要遵守紧急撤销：Task 5、9。
5. 学习工作失败、预算耗尽或 UI 版本不兼容时，原补货与人工确认仍可用：Task 3、10、11、12。

## 文件边界与交付顺序

新增后端 `backend/app/learning/`：持久化、采集、生命周期和 API；新增 agent 包 `agent/src/shopsteward_agent/learning/`：分类、提炼、检索排序的纯策略/模型接口。新增 `backend/app/workflows/`：DSL validator、能力适配与持久执行。新增 `backend/app/adaptive_ui/` 和 `frontend/app/{components/adaptive,utils/a2ui}/`：展示契约与渲染。新增 posttraining `evolution_eval/`：时序实验与发布报告。

不要把所有新逻辑塞进已有 composition.py/tools.py；它们只负责调用 adapter。学习资产为单独的 Pydantic 契约，backend 用纯数据边界导入，不能使 business API 启动时必须加载模型栈。

依赖：Task 1 → 2 → 3 → 4 → 5；Task 7a 依赖 2/5，Task 6 的激活端到端依赖 7a；Task 7b 依赖 7a；Task 8 依赖 3/5/6/7b；Task 9 依赖 5/7b；Task 10 依赖 9；Task 11 依赖 6/9；Task 12 汇总全部。Task 1–6 加 7a 完成 P1，7b/8 完成 P2。5 可先实现 fail-closed 状态机，但缺少 7a 有效评估报告时一律不能激活新 Skill。

## 测试运行约定

以下命令在对应包目录运行，使用已安装工作区依赖的 Python。每个任务先增加明确断言的测试，运行确认失败原因确属缺少新行为，再实现并复测；不能用数据库未启动或导入环境错误冒充有效红灯。

```powershell
# backend/，先确认所有数据库环境变量仅指向隔离测试库
python -m pytest tests/unit/test_learning_contracts.py -q -p no:cacheprovider --basetemp=../var/evolution-tests/backend
# agent/
python -m pytest tests/test_learning_extraction.py -q -p no:cacheprovider --basetemp=../var/evolution-tests/agent
# posttraining/
python -m pytest tests/evolution_eval -q -p no:cacheprovider --basetemp=../var/evolution-tests/posttraining
# 仓库根目录
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend exec playwright test tests/learning.spec.ts
```

测试文件为本计划要新增的交付，不是当前已有文件。集成测试要求 `TEST_DATABASE_URL` 的数据库名为 `shopsteward_test`；模拟数据库为 `shopsteward_sim_test`。基于现有 fixture 建隔离数据，不在日常库清表。不同模块共享全局队列的数据库套件顺序运行。新增测试应能指出业务失败，避免只镜像实现或泛用 mock 一切。

每个任务通过时记录具体命令、测试数、unknown/skip、fixture/model/seed 版本；不把本计划的预期写成已完成成绩。提交时只 stage 本任务文件和确切相关 hunks，不包含用户已有修改；如无法区分则保留未提交并记录。

## Task 1 — 持久契约与事件 outbox（P0）

**Files**
- Create: `backend/app/learning/{__init__,schemas,models,repository,outbox}.py`
- Create: `backend/migrations/versions/0016_learning_foundation.py`（实施时确认 ID/head 可用）
- Modify: `backend/migrations/env.py`、`backend/app/db/session.py` 中模型/迁移准备检查（沿现有模式）
- Test: `backend/tests/unit/test_learning_contracts.py`、`backend/tests/integration/test_learning_storage.py`

**Interfaces**
- `schemas.py` 定义 `LearningScope(principal_id, store_id, source_domain)`、`SourceRef(kind,id,version,available_at,digest)`、`OperationEpisode`、`OutcomeRevision`、`AssetRevision`、`LearningPolicy`、`GateResult`、`UsageRecord`。
- `outbox.append(session, *, scope: LearningScope, event: LearningEvent) -> str`；event 自带来源实体/版本/类型，返回 event_id。
- `repository.create_candidate(session, *, scope, kind, spec, evidence, idempotency_key) -> AssetRevision`；所有检索强制 scope 参数。

- [ ] 写测试：跨店相同实体 ID 不串读；同 event source key 重放只产生一条；事务回滚无 outbox；同 asset revision 内容不可覆盖；kind 不合法被拒绝。
- [ ] 运行两个新测试文件，确认缺失模型/契约行为；实现设计 §7 的表、复合唯一约束、FK 和服务层范围检查。
- [ ] 在隔离库演练 upgrade、数据写读及 downgrade；确认迁移不改原知识 scopes 与业务账本。
- [ ] 复跑测试，通过后审查迁移 SQL 和文件差异，提交此任务。

## Task 2 — 从业务对象归并 Episode 与 Outcome（P0）

**Files**
- Create: `backend/app/learning/{collector,episodes,outcomes,projections}.py`
- Modify: `backend/app/agent_bridge/jobs.py`、`backend/app/operations_cases/repository.py`、`backend/app/execution/events.py`、`backend/app/operations/repository.py`、`backend/app/work_items/repository.py`
- Test: `backend/tests/integration/test_learning_episodes.py`、`backend/tests/unit/test_learning_outcomes.py`

**Interfaces**
- `episodes.resolve(session, *, scope, intent_key, business_refs) -> OperationEpisode`：一次用户目标对应稳定 intent_key；同一目标的 Run/修订继续绑定。
- `collector.consume(session, *, event_id: str) -> str`：幂等投影，返回 episode_id。
- `outcomes.observe(session, *, episode_id: str, source_refs: list[SourceRef], as_of) -> OutcomeRevision`。
- `projections.tool_trace(tool: str, args: dict, result: dict) -> dict`：只允许预定义字段，剔除 credentials，保留参数化所需的业务值与来源。

- [ ] 测试：同 Episode 3 次预算修订+2 次 HTTP 重试计数为 1；10 个不同有效 Episode 计数为 10；取消不计；纯聊天不计；来源域分开。
- [ ] 测试：Run SUCCEEDED 但无采购回执的 business_status 不为 matured；受理不等于收齐；部分到货不等于完成；迟到证据新增 outcome revision，不改旧版；available_at 不早于实际可获得时间。
- [ ] 先覆盖所有修改点的 outbox 同事务写入，再实现独立 collector；模型调用不可出现在业务事务中。
- [ ] 为历史回填提供 `backfill(..., cutoff, dry_run=True)`：只有确实存在的业务引用可关联，缺参数标记 partial；默认不触发历史个性化提炼。
- [ ] 运行上述测试与已有 execution/operations_cases 相关集成回归；验证密钥样例不会进入投影，提交。

## Task 3 — 分类、首十次检查点、学习 worker（P1）

**Files**
- Create: `agent/src/shopsteward_agent/learning/{__init__,taxonomy,triggers}.py`
- Create: `backend/app/learning/{jobs,policy,dispatch}.py`
- Modify: `backend/app/worker.py`、`backend/app/core/config.py`
- Test: `agent/tests/test_learning_triggers.py`、`backend/tests/integration/test_learning_jobs.py`

**Interfaces**
- `classify_episode(episode: dict) -> Classification(family, confidence, reasons)`；确定性业务类型主类，不确定时 unclassified。
- `evaluate_triggers(stats: CategoryStats, event: dict, policy: LearningPolicy) -> list[LearningTrigger]`。
- `dispatch.enqueue_due(session, *, scope, as_of) -> list[str]`；唯一键绑定 trigger_type/category/evidence_digest。
- `jobs.make_handlers(settings) -> dict` 对接现有 Runner；新增 `--profile learning`，模型依赖延迟加载。

- [ ] 测试 9→10 首次触发、10→11 不重复首次触发；同类三例但只一天不生成程序候选；跨两天满足提案门槛；1 次明确纠错生成教训候选。
- [ ] 测试并发重放只入队一次、租约丢失不提交、关掉学习不入队、off→suggest 不未经设置回填旧历史；每批/每天预算耗尽可解释地延后。
- [ ] 实现 triggers 与 token/次数账本，注册 learning worker，不影响 business/agent 现有 profile。
- [ ] 用假提炼器跑重启恢复及幂等验证；运行上述测试，提交。

## Task 4 — 跨轨迹提炼与结构化候选（P1）

**Files**
- Create: `agent/src/shopsteward_agent/learning/{contracts,extractor,curator,prompts}.py`
- Create: `backend/app/learning/generation.py`
- Test: `agent/tests/test_learning_extraction.py`、`backend/tests/unit/test_learning_generation.py`

**Interfaces**
- `contracts.py` 定义 `EvidenceBundle`、`LearningDelta(op, target_asset_id, expected_revision, spec, evidence_refs)`、`SkillSpec`、`ExtractionBudget`；op=add/revise/merge/propose_archive。
- `async extract_candidates(bundle: EvidenceBundle, existing: list[AssetRevision], model, budget: ExtractionBudget) -> list[LearningDelta]`。
- `validate_delta(delta, *, bundle, capabilities, policy) -> GateResult`：拒绝不存在证据、越权工具、遗漏前置条件和扩大作用域。
- `generation.apply_candidates(session, *, scope, deltas, evidence_digest, lease_token) -> list[AssetRevision]`：只写 DRAFT，不覆盖 ACTIVE。

- [ ] 固定三成功一失败轨迹，断言输出含前置条件、反例和现有 source IDs；原 SKU/供应商 ID 被输入参数替代，不能复制历史现金为当前事实。
- [ ] 恶意文档“忽略审批”、用户“本次”、反例指向缺证据、输出伪造 tool、模型 JSON 错误分别有拒绝/降级断言；最多一次修复。
- [ ] 实现 Reflector/Curator 两逻辑调用及增量合并，候选重复则追加证据/生成 revision；用 deterministic merge，禁止整库模型重写。
- [ ] 运行纯策略和 gateway 测试；真实模型 smoke 只作额外质量观察，不能替代确定性回归；提交。

## Task 5 — 版本生命周期、发布、回滚与遗忘（P1/P2）

**Files**
- Create: `backend/app/learning/{lifecycle,lineage,permissions,router}.py`
- Modify: `backend/app/api/router.py`、`backend/app/agent_bridge/knowledge.py`（发显式偏好更新事件）
- Test: `backend/tests/integration/test_learning_lifecycle.py`、`backend/tests/integration/test_learning_forgetting.py`

**Interfaces**
- `transition(session, *, scope, asset_id, revision, action, expected_version, evaluation_id, key) -> AssetRevision`；action=validate/shadow/activate/suspend/rollback/archive/revoke，验证合法状态转换。
- `invalidate_descendants(session, *, source_ref: SourceRef, reason: str) -> list[str]`。
- `revoke_concept(session, *, scope, concept_key, expected_policy_version, key) -> LearningPolicy`；tombstone 阻止回填复活。
- Routes: `GET/PATCH /api/v1/stores/{store_id}/learning/policy`、`GET .../learning/assets`、`GET .../learning/assets/{id}`、`POST .../learning/assets/{id}/transitions`、`POST .../learning/forget`、`GET .../learning/progress`。prefix 实施时与现有 router 风格统一；操作语义不变。

- [ ] 测试没有独立 evaluation 不可 activate；suggest 必须经用户启用；assist 也不能自动激活采购写能力；wrong expected_version 返回冲突，同幂等 key 重放结果相同。
- [ ] 测试 H3 fail 即使所有软分满分也拒绝；S5 unknown 不能激活；revision/content/rubric/工具或业务规则绑定过期必须重评；发布事务再次检查来源撤销，防止检验后与激活前的竞态。
- [ ] 测试删除一个 source 让所有受影响候选/索引/后代 surface 不再被使用；依然满足其他证据的资产也要先复审；回填不绕 tombstone。
- [ ] 测试当前用户拒绝推断覆盖旧学习；撤权阻止读写；回滚恢复旧内容版本但不恢复已撤销的权限或证据。
- [ ] 实现状态机、lineage 遍历（避免环）、审计与接口，接明确偏好修改的失效事件。
- [ ] 运行回归与 OpenAPI 契约检查，通过后提交。

## Task 6 — 在线检索、上下文接线和用户可见学习页（P1）

**Files**
- Create: `backend/app/learning/{retrieval,provider}.py`、`agent/src/shopsteward_agent/learning/ranking.py`
- Modify: `backend/app/agent_bridge/composition.py`、`agent/src/shopsteward_agent/context/builder.py`、`backend/app/agent_bridge/context_repository.py`
- Create: `frontend/app/components/LearningWorkspace.vue`、`frontend/app/composables/useLearning.ts`
- Create: `frontend/app/components/SkillQualityCard.vue`
- Modify: `frontend/app/pages/index.vue`、`frontend/server/utils/backend-routes.ts`、生成的 OpenAPI/前端类型
- Test: `backend/tests/integration/test_learning_context.py`、`frontend/tests/learning.spec.ts`

**Interfaces**
- `retrieve(session, *, scope, task_frame, capabilities, as_of, token_budget=1800, limit=3) -> RetrievalPacket`，包含 selected revisions、rejected reasons、source hashes。
- `provider.load(task_type: str, scope: dict) -> list[dict]` 实现已有 SkillProvider 协议；composition 明确调用 provider，不留下无接线接口。
- `record_application(session, *, run_id, episode_id, asset_revision, stage, reason) -> str`；stage=retrieved/selected/executed。
- Context manifest 新增 `learning_assets` 和省略原因；学习内容是可选来源，必需输入预算规则不变。

- [ ] 测试跨店、simulation→observed、旧版本、撤销来源、缺 required capability 全部被过滤；不适用时返回空集。
- [ ] 测试最多三条/1800 token；任何 Skill 不能挤掉当前用户必需信息；显式偏好与推断冲突采用显式偏好。
- [ ] 实现标签排序基线及 provider；替换新资产的 replenishment 固定筛选，旧 legacy SKILL 兼容加载不变。
- [ ] UI 显示首十次进度、类别不足、候选来源、启用/停用/删除/不再推断；无候选时不伪装已学会。
- [ ] 质量卡分开显示硬门槛、S1–S6 画像、样本数量、离线/线上状态和 unknown 原因；缺合格报告禁用激活，后端独立拒绝。
- [ ] 浏览器验证启用后再发请求能看到命中来源，删除后刷新也不恢复；同步 API 类型/代理白名单，跑 typecheck 和测试，提交。

## Task 7 — 回放、结果 oracle 和候选评估器（7a 前移 P1；7b 留在 P2）

**7a 范围（首个新 Skill 生效前必须完成）**：版本化 rubric、人工/故障种子、绑定校验、静态检查、独立隔离回放、基线对照和 fail-closed 发布 gate。没有校准条件时要求人工复核，不以未校准 judge 自动准入。

**7b 范围（P2）**：扩大场景池、延迟经营结果 oracle、批量评估、漂移复评；完整系统消融仍在 Task 12。7a/7b 分别记录验收，不能把 7b 待做作为提前激活的理由。

**Files**
- Create: `backend/app/learning/{evaluation,replay}.py`
- Create: `posttraining/src/shopsteward_pt/evolution_eval/{__init__,models,dataset,gates,reporting}.py`
- Create: `posttraining/src/shopsteward_pt/evolution_eval/{skill_rubric,skill_scoring}.py`
- Create: `posttraining/rubrics/skill_quality_v1/{rubric.json,README.md,anchors.json,calibration.md}`
- Create: `simulation/tools/evolution_scenarios.py`
- Test: `backend/tests/unit/test_learning_evaluation.py`、`posttraining/tests/evolution_eval/test_gates.py`、`posttraining/tests/evolution_eval/test_dataset.py`
- Test: `posttraining/tests/evolution_eval/test_skill_scoring.py`

**Interfaces**
- `replay.evaluate_revision(revision, scenarios, baseline, runner, seed) -> EvaluationReport`：runner 为隔离只读/模拟 adapter，无真实采购凭证。
- `gates.decide(report: EvaluationReport, policy: GatePolicy) -> GateResult`，结果 pass/fail/insufficient_evidence。
- `skill_scoring.score_skill(spec, *, binding: EvaluationBinding, checks: list[HardCheck], observations: list[Observation], reviews: list[SkillReview], rubric: SkillRubric) -> SkillQualityReport`：纯函数；未知、评审分歧、证据不匹配不可乐观评分。
- `dataset.split_sequences(sequences, *, scenario_family, seed) -> DatasetManifest`；manifest 绑定 hash、时序、来源可用时间和完整序列。
- 复用 `planning/recovery/solver.py` 计算，新增观察 oracle 时明确模拟真值与真实证据边界。

- [ ] 测试 19 个适用场景返回 insufficient_evidence；1 次硬约束违反直接 fail；unknown 不进成功分子；可读不到的未来事件禁止进入输入。
- [ ] 7a：将专项规范 H/S 定义和分档固化到 rubric.json，使用至少 30 个含缺陷/unknown 的候选进行双人校准；样本不足保留人工 review gate，报告分歧与误放/误拒。
- [ ] 7a：测试伪造证据 refs、评分套用其他 revision、judge 分歧都无法发 pass；来源案例不能充当独立泛化成绩；同一模型自评不能单独放行；S5 的目标和对照在运行前冻结。
- [ ] 测试相同 scenario family 不能跨 split，训练与测试共享来源报错；小样本置信区间不足不发 pass。
- [ ] 构建六类最小 fixture：资金底线、延期、不同报价、MOQ、部分到货/UNKNOWN、用户改口；相同外生随机流给 baseline/challenger。
- [ ] 实现独立评估与报告，不拿提炼模型自评替代硬 gate；模型质量评价作为额外列。
- [ ] 7a：Task 6 启用端到端前执行正常/不适用/边界/恢复/与现有 Skill 组合五类测试，证明低质候选被 gate 阻止、合格候选正确启用，绑定变化后立即失效。
- [ ] 跑 oracle 金标准和新评估测试，确认报告注明 model/simulator/solver/数据集版本；提交。

## Task 8 — 持续学习、效用修订和漂移暂停（P2）

**Files**
- Create: `backend/app/learning/{consolidation,drift,metrics}.py`
- Modify: `backend/app/learning/{jobs,dispatch,lifecycle}.py`
- Test: `backend/tests/integration/test_learning_continuous.py`、`backend/tests/unit/test_learning_drift.py`

**Interfaces**
- `consolidate(session, *, scope, since_watermark, budget) -> ConsolidationResult`，只消耗新增证据。
- `assess_drift(applications, *, window=10, failure_threshold=3) -> DriftDecision`；只纳入成熟、适用且实际执行的记录。
- `update_utility(session, *, application_id, outcome_revision) -> None`，同 outcome 版本幂等；retrieved≠executed。

- [ ] 测试每周无新证据不调模型；证据 digest 相同不重复学习；工具 schema 变化立刻暂停依赖资产。
- [ ] 测试十次成熟应用三失败触发复审，pending 不当失败；Skill 未实际执行不归功；同类场景漂移不误删低频应急技能。
- [ ] 每次执行前做便宜的有效性检查，执行后记轨迹；严重违规立刻暂停，新版/异常必检；初值为前三次语义全检、后续 20% 抽样。完整 rubric 按修订/漂移/有新证据复审，不在每次调用后全量跑。
- [ ] 区分 skill_defect/retrieval_mismatch/executor_noncompliance/tool_failure/changed_environment/unresolved；成熟结果指标同时显示总体数、pending/unknown 和覆盖率，禁止把未执行或结果未到的样本算作成功。
- [ ] 测试关闭学习后在线补货继续可用；删除后 consolidator 不能重新产生同推断偏好；同一条迟到回执不重复记 reward。
- [ ] 实现增量维护和暂停，先用可解释的成功/失败/未知统计，不宣称有因果收益；UI 展示变更与来源。
- [ ] 运行 P0–P2 端到端故事及相关回归，产出首版 Skill MVP 验收记录，提交。

## Task 9 — 受限 Workflow DSL 与可恢复执行器（P3）

**Files**
- Create: `backend/app/workflows/{__init__,schemas,models,validator,capabilities,repository,runner,jobs}.py`
- Create: `backend/migrations/versions/0017_workflow_runs.py`（实施时查 head）
- Test: `backend/tests/unit/test_workflow_validator.py`、`backend/tests/integration/test_workflow_recovery.py`

**Interfaces**
- `WorkflowSpec(inputs, outputs, nodes, edges, max_steps=12)`；节点类型严格取自设计 §10。
- `validate_workflow(spec: WorkflowSpec, registry: CapabilityRegistry) -> GateResult`。
- `async advance(session_factory, *, workflow_run_id, lease_token) -> StepResult`；一个调用推进一个可提交步骤。
- `CapabilityAdapter.read/compute/propose(...)` 映射既有业务服务，不能注册 approve_purchase；确认节点仅产生暂停状态与既有确认链接。
- `start(..., asset_revision, context_versions, idempotency_key) -> WorkflowRun` 固定资产版本；每次推进重新检查撤销/权限。

- [ ] 测试环/孤立节点、超过 12 节点、未知 capability、输入类型不匹配和绕过确认路径全部拒绝。
- [ ] 测试 worker 在提交结果前/后崩溃均正确恢复，重复 step 不新建第二方案/采购；UNKNOWN 分支只能核实；等待用户不占 lease。
- [ ] 测试发布新 revision 不改变在途流程；撤销当前 revision 阻止后续动作；已受理 Action 保留核实路径。
- [ ] 实现 DAG validator、持久步骤、幂等 adapter、超时和最多两次节点重试，继续使用现有 Runner。
- [ ] 跑流程恢复集成测试及原采购审批/幂等回归，提交。

## Task 10 — 新路线候选、离线选优与 WorkItem 路由（P3）

**Files**
- Create: `agent/src/shopsteward_agent/learning/workflow_induction.py`
- Create: `backend/app/workflows/{search,routing}.py`
- Create: `posttraining/src/shopsteward_pt/evolution_eval/process_baseline.py`
- Modify: `backend/app/work_items/` 的领取/上下文/回传接入点，复用既有协议和租约
- Test: `agent/tests/test_workflow_induction.py`、`backend/tests/integration/test_workflow_routing.py`

**Interfaces**
- `propose_workflow_deltas(evidence, registry, existing, *, max_candidates=3) -> list[WorkflowSpec]`。
- `search.compare(candidates, dataset, budget) -> list[EvaluationReport]` 使用 Task 7，不共享真实经营凭证。
- `routing.route(work_item, capabilities, active_assets) -> RouteDecision(handler_id|ask_user|unsupported, reasons)`。
- `process_baseline.mine_sequences(episodes, *, min_support=3) -> list[dict]`：以独立 Episode 为支持度单位，输出重复序列及耗时，供非 LLM 对照；PM4Py 接入作为后续离线可选实验。

- [ ] 测试只可补检查/去冗余/分支/替换已验证子技能；插入自定义代码、虚构能力、改采购规则被拒绝。
- [ ] 测试没有合格候选继续原固定流程；超预算搜索停止且可恢复；UNKNOWN 订单不会被新路线当失败重发。
- [ ] 测试用户在处理期间补充约束使旧 WorkItem lease 失效，新路由只能使用最新输入；未知任务问清或输出能力缺口。
- [ ] 实现单批最多三候选的搜索和影子模式，路由先覆盖补货/恢复两类；更多类别按已注册 handler 能力启用。
- [ ] 增加 `posttraining/tests/evolution_eval/test_process_baseline.py`：同 Episode 的重试不增加支持度；不同用户/来源域不混合；只从训练 split 发现序列，测试集不得参与发现。
- [ ] 使用保留集验证质量和步骤开销，对证据不足的候选维持 SHADOW；提交。

## Task 11 — A2UI 业务 surface 与持久快捷入口（P4）

**Files**
- Create: `backend/app/adaptive_ui/{__init__,schemas,catalog,compiler,actions,router}.py`
- Create: `frontend/app/components/adaptive/{AdaptiveSurface,PlanComparisonSurface,RecoveryQuickForm}.vue`
- Create: `frontend/app/utils/a2ui/{catalog,processor,actions}.ts`
- Modify: `frontend/app/components/TaskWorkspace.vue`、`frontend/package.json`、`pnpm-lock.yaml`、API/类型/代理白名单
- Test: `backend/tests/unit/test_adaptive_ui_contract.py`、`backend/tests/integration/test_adaptive_ui_actions.py`、`frontend/tests/adaptive-ui.spec.ts`

**Interfaces**
- `UIIntent(fields, layout, allowed_actions, workflow_revision)` 是内部契约，不冒充 A2UI wire schema。
- `compile_surface(intent, *, catalog_version, authorized_dto, context_version) -> SurfaceEnvelope`；包含 protocol_version/catalog_hash/revision/messages。
- `execute_ui_action(session, *, scope, surface_id, surface_revision, context_version, action_id, params, key) -> ActionResult`；只解析白名单动作，服务端取实体和金额。
- Vue `AdaptiveSurface` props 为已验证 envelope；unsupported/error/revoked 时调用现有固定组件 fallback。

- [ ] 做包/协议兼容性验证：以官方 v0.9.1 schema 为目标，确认 web_core 的实际发布版本、导出路径和 Nuxt SSR/client 边界；锁定依赖与 schema hash，保存协议 fixture。失败时保留固定 UI，报告阻塞，不临时拼另一套同名协议。
- [ ] 测试未知组件、恶意 HTML/资源地址、深度 9、节点 51、超 64 KB 拒绝；不完整流不替换已提交 surface。
- [ ] 测试过期 context_version 返回 stale 提示；伪造 action ID/他店 plan ID/撤权均拒绝；重复提交遵循原幂等。
- [ ] 实现受信 catalog 到既有组件的映射，client-only 消息处理必要时隔离 SSR；持久快捷入口保存为 UI 类型资产 revision。
- [ ] 浏览器覆盖预算输入→试算→比较→打开既有确认页，以及断网恢复、协议不兼容回退、移动端、键盘操作与失权清屏。
- [ ] 运行新 API、typecheck、Playwright 与 build；确认生成器不能直接发起审批采购，提交。

## Task 12 — 联合研究评测、发布开关与交付文档（P5）

**Files**
- Create: `posttraining/src/shopsteward_pt/evolution_eval/{__main__,runner,cli}.py`
- Create: `posttraining/tests/evolution_eval/test_temporal_runner.py`
- Create: `docs/evaluation/evolution/README.md`、`docs/runbooks/learning-evolution.md`
- Modify: `README.md`、`docs/architecture.md`；新增实际验证报告 `docs/reports/memory-evolution-delivery.md`

**Interfaces**
- `run_experiment(manifest, variants, *, update_mode: Literal['frozen','prequential'], seeds, budget) -> ExperimentReport`。
- CLI 交付 `validate`、`run`、`report` 子命令：`python -m shopsteward_pt.evolution_eval report --input <report.json>`。
- settings 提供 learning collection/generation/assist/workflow/adaptive_ui 独立开关，默认兼容旧系统；模型调用使用现有 profile 并冻结 hash。

- [ ] 实现 6 类×20 序列×15 Episode 数据 manifest，按设计分组；先跑小规模 smoke 排错，再锁定正式测试，不能以 smoke 宣称效果。
- [ ] 测试 prequential 在第 t 次不能读 t+1 及尚未 available 的结果；frozen 评测不修改 asset revision；任务顺序变化产生独立实验 run。
- [ ] B0–B4 及 B-process 用相同模型/预算/seed 做消融；完整记录提炼与验证成本，unknown usage 不按零计。B5 另做 UI 用户任务测试。
- [ ] 输出配对质量差异及按序列聚类的区间、纠错次数、流程步骤、token/延迟、资产增长/淘汰与失败率；不过门槛就维持关闭或 SHADOW。
- [ ] 顺序执行 backend/agent/posttraining 相关全量套件，前端类型、build、Playwright；仅当无新变更/失败后不重复无意义全量测试。
- [ ] 演练关停学习、撤销资产、rollback、数据库迁移恢复与服务重启；既有备货和已提交采购回执照常工作。
- [ ] 交付报告明确代码完成、真实模型验证、模拟结果、用户测试各自状态，不把任何一类等同真实门店收益；提交文档和最终相关改动。

## API 与迁移兼容检查清单

- [ ] 新路由接入同一认证、同源代理和 OpenAPI 导出机制；生成前端 backend.d.ts，不手改类型掩盖契约错位。
- [ ] 老客户端不认识新字段仍可使用固定工作区；新客户端在 learning flag 关闭时不展示假进度。
- [ ] 原 SKILL 仅以 `legacy_explicit` 来源读取，不自动转成通过评估的新资产；删除/更新事件使派生资产失效。
- [ ] 所有公开查询校验实体归属，所有后台 handler 重新核实用户现有权限；按候选ID和版本定位，不按名称猜测。
- [ ] 当前基线文件仍有大量未提交改动，执行时先重新 diff 并确认交接点；不要 reset、覆盖或将本任务文档与其他开发一起提交。

## 阶段验收与估算

P0 对应 Task 1–2（4–6 人日）；P1 对应 Task 3–6（5–7 人日）；P2 对应 Task 7–8（5–8 人日）；P3 对应 Task 9–10（6–9 人日）；P4 对应 Task 11（5–8 人日）；P5 对应 Task 12（4–6 人日）。共 29–44 人日，模型额度、用户招募和真实结果等待另外安排。

上述是初版粗略估算；质量细化将 Task 7a 前移 P1，P2 只含 7b/8。人工校准、独立用例准备和组合回归的实际工作量需在 P0 盘点后更新，不把原数字作为细化后已确认的承诺。

首个实施目标建议锁定 **P0–P2**，先证明“数据可信、能提炼、能复用、能纠错、能遗忘”。完整路线保留 P3/P4，但每阶段依赖其前置验收，避免基础反馈不足时继续堆生成能力。

本轮仅交付研究、设计和完整计划；没有修改产品代码、运行模型实验或迁移数据库。
